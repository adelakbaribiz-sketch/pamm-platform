"""Copy trading router."""
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..auth import get_principal, Principal, require_roles
from ..db import get_db
from ..models import (Strategy, MasterAccount, InvestorAccount, CopySubscription,
                      CopyTrade, CopyFollowerTrade, Subscription)
from ..schemas import CopySubscribeIn, CopyTradeIn, CopyControlIn
from ..domain.copy import CopyEngine
from ..domain.events import record_event, append_audit

router = APIRouter()

@router.post("/copy/subscriptions")
def create_copy_subscription(body: CopySubscribeIn,
                             p: Annotated[Principal, Depends(require_roles("broker_admin", "investor"))],
                             db: Session = Depends(get_db)):
    strat = db.query(Strategy).filter(Strategy.id == body.strategy_id,
                                       Strategy.tenant_id == p.tenant_id).first()
    if not strat: raise HTTPException(404, "Strategy not found")
    if strat.kind != "copy":
        raise HTTPException(422, "Strategy must be of kind=copy; use /api/subscriptions for PAMM")
    m = db.query(MasterAccount).filter(MasterAccount.id == strat.master_account_id,
                                       MasterAccount.tenant_id == p.tenant_id).first()
    if not m: raise HTTPException(404, "Master account not found")
    fa = db.query(InvestorAccount).filter(InvestorAccount.id == body.follower_account_id,
                                          InvestorAccount.tenant_id == p.tenant_id).first()
    if not fa: raise HTTPException(404, "Follower account not found")
    existing = db.query(CopySubscription).filter(
        CopySubscription.strategy_id == body.strategy_id,
        CopySubscription.follower_account_id == body.follower_account_id,
        CopySubscription.status != "detached",
    ).first()
    if existing:
        return {"copy_subscription_id": existing.id, "status": existing.status}
    cs = CopySubscription(
        tenant_id=p.tenant_id, strategy_id=body.strategy_id, master_account_id=m.id,
        follower_account_id=body.follower_account_id,
        follower_user_id=p.user_id if p.role == "investor" else fa.owner_user_id,
        status="active", max_lots_per_trade=body.max_lots_per_trade,
        max_drawdown_pct=body.max_drawdown_pct, excluded_symbols=body.excluded_symbols,
        lot_multiplier=body.lot_multiplier,
    )
    db.add(cs); db.flush()
    record_event(db, p.tenant_id, "copy.subscription.created",
                 {"copy_subscription_id": cs.id, "strategy_id": body.strategy_id,
                  "follower_account_id": body.follower_account_id},
                 subject_type="copy_subscription", subject_id=cs.id)
    append_audit(db, p.tenant_id, p.user_id, "copy.subscription.create",
                 "copy_subscription", cs.id,
                 after={"strategy_id": body.strategy_id, "follower": body.follower_account_id})
    db.commit()
    return {"copy_subscription_id": cs.id, "status": cs.status}

@router.get("/copy/subscriptions")
def list_copy_subscriptions(p: Annotated[Principal, Depends(get_principal)],
                            db: Session = Depends(get_db)):
    q = db.query(CopySubscription)
    if not p.is_super_admin: q = q.filter(CopySubscription.tenant_id == p.tenant_id)
    if p.role == "investor": q = q.filter(CopySubscription.follower_user_id == p.user_id)
    out = []
    for cs in q.all():
        m = db.query(MasterAccount).filter(MasterAccount.id == cs.master_account_id).first()
        fa = db.query(InvestorAccount).filter(InvestorAccount.id == cs.follower_account_id).first()
        out.append({
            "id": cs.id, "strategy_id": cs.strategy_id, "master_account_id": cs.master_account_id,
            "master_login": m.login if m else None,
            "follower_account_id": cs.follower_account_id, "follower_login": fa.login if fa else None,
            "status": cs.status, "max_lots_per_trade": str(cs.max_lots_per_trade) if cs.max_lots_per_trade else None,
            "excluded_symbols": cs.excluded_symbols, "lot_multiplier": str(cs.lot_multiplier),
            "subscribed_at": cs.subscribed_at.isoformat() if cs.subscribed_at else None,
        })
    return out

@router.post("/copy/control")
def control_subscription(body: CopyControlIn,
                          p: Annotated[Principal, Depends(require_roles("broker_admin", "investor"))],
                          db: Session = Depends(get_db)):
    cs = db.query(CopySubscription).filter(CopySubscription.id == body.copy_subscription_id,
                                            CopySubscription.tenant_id == p.tenant_id).first()
    if not cs: raise HTTPException(404, "Copy subscription not found")
    if p.role == "investor" and cs.follower_user_id != p.user_id:
        raise HTTPException(403, "Not your subscription")
    engine = CopyEngine(db)
    try:
        if body.action == "pause": engine.pause(cs.id, p.tenant_id)
        elif body.action == "resume": engine.resume(cs.id, p.tenant_id)
        elif body.action == "detach": engine.detach(cs.id, p.tenant_id, body.close_positions)
        else: raise HTTPException(422, "Invalid action")
    except ValueError as e:
        raise HTTPException(409, str(e))
    append_audit(db, p.tenant_id, p.user_id, f"copy.{body.action}", "copy_subscription", cs.id,
                 after={"status": cs.status, "close_positions": body.close_positions})
    db.commit()
    return {"copy_subscription_id": cs.id, "status": cs.status}

@router.post("/copy/trades")
def open_copy_trade(body: CopyTradeIn,
                   p: Annotated[Principal, Depends(require_roles("broker_admin", "money_manager"))],
                   db: Session = Depends(get_db)):
    strat = db.query(Strategy).filter(Strategy.id == body.strategy_id,
                                       Strategy.tenant_id == p.tenant_id).first()
    if not strat: raise HTTPException(404, "Strategy not found")
    if strat.kind != "copy":
        raise HTTPException(422, "Strategy must be of kind=copy")
    m = db.query(MasterAccount).filter(MasterAccount.id == body.master_account_id,
                                       MasterAccount.tenant_id == p.tenant_id).first()
    if not m: raise HTTPException(404, "Master account not found")
    if body.side not in ("buy", "sell", "close"):
        raise HTTPException(422, "Invalid side")
    engine = CopyEngine(db)
    ct = engine.open_master_trade(
        tenant_id=p.tenant_id, strategy_id=body.strategy_id, master_account_id=body.master_account_id,
        symbol=body.symbol, side=body.side, master_lots=body.master_lots,
        master_price=body.master_price, idempotency_key=body.idempotency_key,
    )
    follower_trades = engine.replicate_to_followers(ct, body.master_price)
    ct.status = "filled"
    db.commit()
    return {
        "copy_trade_id": ct.id, "status": ct.status, "symbol": ct.symbol, "side": ct.side,
        "master_lots": str(ct.master_lots), "master_price": str(ct.master_price) if ct.master_price else None,
        "follower_trades": [{
            "id": ft.id, "subscription_id": ft.copy_subscription_id,
            "follower_account_id": ft.follower_account_id,
            "requested_lots": str(ft.requested_lots), "allocated_lots": str(ft.allocated_lots),
            "fill_price": str(ft.fill_price) if ft.fill_price else None,
            "status": ft.status, "reject_reason": ft.reject_reason,
            "server_side_latency_ms": ft.server_side_latency_ms,
            "broker_latency_ms": ft.broker_latency_ms,
            "slippage_bps": str(ft.slippage_bps) if ft.slippage_bps is not None else None,
        } for ft in follower_trades],
    }

@router.get("/copy/trades")
def list_copy_trades(p: Annotated[Principal, Depends(get_principal)], db: Session = Depends(get_db)):
    q = db.query(CopyTrade)
    if not p.is_super_admin: q = q.filter(CopyTrade.tenant_id == p.tenant_id)
    out = []
    for ct in q.order_by(CopyTrade.created_at.desc()).limit(100).all():
        fts = db.query(CopyFollowerTrade).filter(CopyFollowerTrade.copy_trade_id == ct.id).all()
        out.append({
            "id": ct.id, "symbol": ct.symbol, "side": ct.side,
            "master_lots": str(ct.master_lots), "master_price": str(ct.master_price) if ct.master_price else None,
            "status": ct.status, "created_at": ct.created_at.isoformat(),
            "follower_count": len(fts), "filled": sum(1 for f in fts if f.status == "filled"),
            "rejected": sum(1 for f in fts if f.status == "rejected"),
            "skipped": sum(1 for f in fts if f.status == "skipped"),
        })
    return out

@router.get("/copy/trades/{copy_trade_id}/followers")
def list_follower_trades(copy_trade_id: str, p: Annotated[Principal, Depends(get_principal)],
                         db: Session = Depends(get_db)):
    ct = db.query(CopyTrade).filter(CopyTrade.id == copy_trade_id).first()
    if not ct: raise HTTPException(404, "Copy trade not found")
    if not p.is_super_admin and ct.tenant_id != p.tenant_id:
        raise HTTPException(403, "Cross-tenant access denied")
    fts = db.query(CopyFollowerTrade).filter(CopyFollowerTrade.copy_trade_id == copy_trade_id).all()
    return [{
        "id": ft.id, "subscription_id": ft.copy_subscription_id,
        "follower_account_id": ft.follower_account_id,
        "requested_lots": str(ft.requested_lots), "allocated_lots": str(ft.allocated_lots),
        "fill_price": str(ft.fill_price) if ft.fill_price else None,
        "status": ft.status, "reject_reason": ft.reject_reason,
        "server_side_latency_ms": ft.server_side_latency_ms,
        "broker_latency_ms": ft.broker_latency_ms,
        "slippage_bps": str(ft.slippage_bps) if ft.slippage_bps is not None else None,
        "executed_at": ft.executed_at.isoformat() if ft.executed_at else None,
    } for ft in fts]
