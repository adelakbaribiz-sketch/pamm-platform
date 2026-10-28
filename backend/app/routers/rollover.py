from typing import Annotated
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..auth import get_principal, Principal, require_roles
from ..db import get_db
from ..models import (MasterAccount, Subscription, Rollover, RolloverEntry,
                      InvestorAccount, SettlementLeaf, SettlementRoot)
from ..schemas import RolloverIn, RolloverOut, RolloverEntryOut
from ..domain import pamm, merkle, saga as saga_mod
from ..domain.events import record_event, append_audit

router = APIRouter()

@router.post("/rollovers", response_model=RolloverOut)
def execute_rollover(body: RolloverIn,
                    p: Annotated[Principal, Depends(require_roles("broker_admin", "money_manager"))],
                    db: Session = Depends(get_db)):
    # IDEMPOTENCY
    existing = db.query(Rollover).filter(Rollover.idempotency_key == body.idempotency_key).first()
    if existing:
        if existing.tenant_id != p.tenant_id or existing.master_account_id != body.master_account_id:
            raise HTTPException(409, "idempotency_key collision across tenants/masters")
        return _serialize_rollover(existing, db)
    m = db.query(MasterAccount).filter(MasterAccount.id == body.master_account_id,
                                       MasterAccount.tenant_id == p.tenant_id).first()
    if not m: raise HTTPException(404, "Master account not found")
    method = body.method or m.allocation_method
    if method not in ("euro_days", "start_capital", "end_capital"):
        raise HTTPException(422, "Invalid method")
    subs = db.query(Subscription).filter(
        Subscription.master_account_id == m.id,
        Subscription.tenant_id == p.tenant_id,
        Subscription.status == "active",
    ).all()
    if not subs:
        raise HTTPException(409, "No active subscriptions to roll over")
    nav_before = m.nav_at_period_start if getattr(m, "nav_at_period_start", None) is not None \
                 else pamm.compute_nav(m.equity, m.total_units, m.base_nav)
    nav_after_gross = pamm.compute_nav(m.equity, m.total_units, m.base_nav)
    period_days = max(1, body.period_days)
    now = datetime.now(timezone.utc)
    period_start = now - timedelta(days=period_days)
    for s in subs:
        s.euro_days = pamm.q_units(s.end_capital * Decimal(period_days))
    snapshots = [pamm.InvestorSnapshot(s.id, s.units, s.start_capital, s.end_capital,
                                       s.euro_days, s.hwm) for s in subs]
    results, total_fee = pamm.apply_rollover(nav_before, nav_after_gross, snapshots,
                                             m.performance_fee_rate, method)
    rollover = Rollover(
        tenant_id=p.tenant_id, master_account_id=m.id,
        period_start=period_start, period_end=now, method=method,
        master_equity_before=pamm.q2(m.equity), master_equity_after=pamm.q2(m.equity),
        master_pnl=pamm.q2(Decimal("0")), total_units=pamm.q_units(m.total_units),
        nav_before=pamm.q2(nav_before), nav_after=pamm.q2(nav_after_gross),
        total_performance_fee=pamm.q2(total_fee),
        status="completed", idempotency_key=body.idempotency_key, created_by=p.user_id,
    )
    db.add(rollover); db.flush()
    for r in results:
        e = RolloverEntry(
            rollover_id=rollover.id, subscription_id=r.subscription_id, tenant_id=p.tenant_id,
            units=r.units, start_capital=r.start_capital, end_capital=r.end_capital,
            euro_days=r.euro_days, pnl_share=r.pnl_share, performance_fee=r.performance_fee,
            nav_before=r.nav_before, nav_after=r.nav_after, units_after=r.units_after,
        )
        db.add(e); db.flush()
        s = next(x for x in subs if x.id == r.subscription_id)
        s.units = r.units_after
        s.hwm = r.new_hwm
        s.end_capital = pamm.q2(r.units_after * r.nav_after)
        s.start_capital = s.end_capital
    if total_fee > 0 and nav_after_gross > 0:
        units_redeemed_for_fees = pamm.q_units(total_fee / nav_after_gross)
        m.equity = pamm.q2(m.equity - total_fee)
        m.total_units = pamm.q_units(m.total_units - units_redeemed_for_fees)
        m.hwm = pamm.q2(m.equity)
    m.nav_at_period_start = pamm.q2(nav_after_gross)
    investor_total = pamm.q2(sum((r.gav_end for r in results), Decimal("0")))
    # Record the period P&L and post-fee equity (previously stored as 0 / unchanged).
    rollover.master_pnl = pamm.q2(sum((r.pnl_share for r in results), Decimal("0")))
    rollover.master_equity_after = pamm.q2(m.equity)
    reconciled = pamm.reconcile(m.equity, results, total_fee)
    # Merkle settlement
    leaves = []
    for r in results:
        s = next(x for x in subs if x.id == r.subscription_id)
        inv = db.query(InvestorAccount).filter(InvestorAccount.id == s.investor_account_id).first()
        pairs = {
            "rollover_id": rollover.id, "subscription_id": r.subscription_id,
            "investor_login": inv.login if inv else "",
            "units": str(r.units), "nav_before": str(r.nav_before), "nav_after": str(r.nav_after),
            "pnl_share": str(r.pnl_share), "performance_fee": str(r.performance_fee),
            "units_after": str(r.units_after), "hwm_after": str(r.new_hwm),
        }
        blob, lh = merkle.leaf_hash(pairs)
        leaves.append((lh, blob, r.subscription_id))
    leaves.sort(key=lambda x: x[2])
    root, levels = merkle.build_tree([l[0] for l in leaves])
    db.add(SettlementRoot(tenant_id=p.tenant_id, rollover_id=rollover.id,
                          root_hash=root, leaf_count=len(leaves)))
    db.flush()
    for idx, (lh, blob, sub_id) in enumerate(leaves):
        db.add(SettlementLeaf(tenant_id=p.tenant_id, rollover_id=rollover.id,
                              subscription_id=sub_id, canonical_blob=blob, hash=lh))
    record_event(db, p.tenant_id, "rollover.completed",
                 {"rollover_id": rollover.id, "master_account_id": m.id, "method": method,
                  "total_fee": str(total_fee), "investor_total": str(investor_total),
                  "reconciled": reconciled, "merkle_root": root},
                 subject_type="rollover", subject_id=rollover.id)
    append_audit(db, p.tenant_id, p.user_id, "rollover.execute", "rollover", rollover.id,
                 after={"method": method, "total_fee": str(total_fee),
                        "reconciled": reconciled, "merkle_root": root})
    db.commit()
    return _serialize_rollover(rollover, db)

@router.get("/rollovers/{rollover_id}", response_model=RolloverOut)
def get_rollover(rollover_id: str, p: Annotated[Principal, Depends(get_principal)],
                db: Session = Depends(get_db)):
    r = db.query(Rollover).filter(Rollover.id == rollover_id).first()
    if not r: raise HTTPException(404, "Rollover not found")
    if not p.is_super_admin and r.tenant_id != p.tenant_id:
        raise HTTPException(403, "Cross-tenant access denied")
    # Investors only see their own entries, not other investors' allocations.
    return _serialize_rollover(r, db, only_user=p.user_id if p.role == "investor" else None)

@router.get("/masters/{master_id}/rollovers")
def list_rollovers(master_id: str, p: Annotated[Principal, Depends(get_principal)],
                  db: Session = Depends(get_db)):
    q = db.query(Rollover).filter(Rollover.master_account_id == master_id)
    if not p.is_super_admin: q = q.filter(Rollover.tenant_id == p.tenant_id)
    return [{"id": r.id, "method": r.method, "period_end": r.period_end.isoformat(),
             "nav_before": str(r.nav_before) if r.nav_before is not None else None,
             "nav_after": str(r.nav_after) if r.nav_after is not None else None,
             "total_performance_fee": str(r.total_performance_fee),
             "status": r.status, "idempotency_key": r.idempotency_key} for r in q.all()]

def _serialize_rollover(r: Rollover, db: Session, only_user: str | None = None) -> RolloverOut:
    entries = []
    for e in r.entries:
        s = db.query(Subscription).filter(Subscription.id == e.subscription_id).first()
        if only_user and (not s or s.investor_user_id != only_user):
            continue
        inv = db.query(InvestorAccount).filter(InvestorAccount.id == s.investor_account_id).first() if s else None
        entries.append(RolloverEntryOut(
            subscription_id=e.subscription_id, investor_login=inv.login if inv else None,
            units=e.units, start_capital=e.start_capital, end_capital=e.end_capital,
            euro_days=e.euro_days, pnl_share=e.pnl_share, performance_fee=e.performance_fee,
            nav_before=e.nav_before, nav_after=e.nav_after, units_after=e.units_after,
        ))
    return RolloverOut(
        id=r.id, master_account_id=r.master_account_id, method=r.method,
        period_start=r.period_start, period_end=r.period_end,
        master_equity_before=r.master_equity_before, master_equity_after=r.master_equity_after,
        master_pnl=r.master_pnl, nav_before=r.nav_before, nav_after=r.nav_after,
        total_units=r.total_units, total_performance_fee=r.total_performance_fee,
        status=r.status, idempotency_key=r.idempotency_key, entries=entries,
    )
