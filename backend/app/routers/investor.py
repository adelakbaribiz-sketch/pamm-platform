from typing import Annotated
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..auth import get_principal, Principal, require_roles
from ..db import get_db
from ..models import InvestorAccount, Subscription, MasterAccount, Strategy, Broker, User
from ..schemas import InvestorCreate, SubscribeIn
from ..domain import pamm, risk
from ..domain.events import record_event, append_audit

router = APIRouter()

@router.post("/investors")
def create_investor(body: InvestorCreate,
                    p: Annotated[Principal, Depends(require_roles("broker_admin"))],
                    db: Session = Depends(get_db)):
    broker = db.query(Broker).filter(Broker.id == body.broker_id, Broker.tenant_id == p.tenant_id).first()
    if not broker: raise HTTPException(404, "Broker not found")
    owner_id = p.user_id
    if body.owner_user_id:
        owner = db.query(User).filter(User.id == body.owner_user_id, User.tenant_id == p.tenant_id,
                                      User.role == "investor").first()
        if not owner: raise HTTPException(404, "Investor user not found in this tenant")
        owner_id = owner.id
    inv = InvestorAccount(tenant_id=p.tenant_id, broker_id=body.broker_id,
                          login=body.login, currency=body.currency, owner_user_id=owner_id)
    db.add(inv); db.flush()
    record_event(db, p.tenant_id, "investor.created", {"investor_account_id": inv.id},
                 subject_type="investor_account", subject_id=inv.id)
    append_audit(db, p.tenant_id, p.user_id, "investor.create", "investor_account", inv.id,
                 after={"login": inv.login})
    db.commit()
    return {"id": inv.id, "login": inv.login}

@router.get("/investors")
def list_investors(p: Annotated[Principal, Depends(get_principal)], db: Session = Depends(get_db)):
    q = db.query(InvestorAccount)
    if not p.is_super_admin: q = q.filter(InvestorAccount.tenant_id == p.tenant_id)
    # Investors only see the accounts they own.
    if p.role == "investor": q = q.filter(InvestorAccount.owner_user_id == p.user_id)
    return [{"id": i.id, "broker_id": i.broker_id, "login": i.login,
             "currency": i.currency, "status": i.status} for i in q.all()]

@router.post("/subscriptions")
def subscribe(body: SubscribeIn,
              p: Annotated[Principal, Depends(require_roles("broker_admin", "investor"))],
              db: Session = Depends(get_db)):
    strat = db.query(Strategy).filter(Strategy.id == body.strategy_id,
                                       Strategy.tenant_id == p.tenant_id).first()
    if not strat: raise HTTPException(404, "Strategy not found")
    if strat.kind not in ("pamm", "mam"):
        raise HTTPException(422, "Use /api/copy/subscriptions for copy strategies")
    m = db.query(MasterAccount).filter(MasterAccount.id == strat.master_account_id,
                                        MasterAccount.tenant_id == p.tenant_id).first()
    if not m: raise HTTPException(404, "Master account not found")
    inv = db.query(InvestorAccount).filter(InvestorAccount.id == body.investor_account_id,
                                           InvestorAccount.tenant_id == p.tenant_id).first()
    if not inv: raise HTTPException(404, "Investor account not found")
    # Investors may only subscribe with an account they own.
    if p.role == "investor" and inv.owner_user_id != p.user_id:
        raise HTTPException(403, "Investor account does not belong to you")
    try:
        risk.check_subscription(db, p.tenant_id, m.id, body.capital)
    except risk.RiskError as e:
        db.commit()
        raise HTTPException(422, detail={"code": e.code, "details": e.details})
    nav = pamm.compute_nav(m.equity, m.total_units, m.base_nav)
    units = pamm.issue_units(body.capital, nav)
    before_master = {"equity": str(m.equity), "total_units": str(m.total_units)}
    m.equity = pamm.q2(m.equity + body.capital)
    m.total_units = pamm.q_units(m.total_units + units)
    if m.nav_at_period_start is None or m.nav_at_period_start == m.base_nav:
        m.nav_at_period_start = pamm.q2(nav)
    after_master = {"equity": str(m.equity), "total_units": str(m.total_units)}
    sub = Subscription(
        tenant_id=p.tenant_id, strategy_id=strat.id, master_account_id=m.id,
        investor_account_id=inv.id,
        investor_user_id=p.user_id if p.role == "investor" else inv.owner_user_id,
        units=units, contributed_capital=body.capital,
        start_capital=body.capital, end_capital=body.capital,
        euro_days=Decimal("0"), hwm=pamm.q2(units * nav),
    )
    db.add(sub); db.flush()
    record_event(db, p.tenant_id, "subscription.created",
                 {"subscription_id": sub.id, "master_account_id": m.id,
                  "investor_account_id": inv.id, "units": str(units), "capital": str(body.capital),
                  "nav_at_entry": str(nav)},
                 subject_type="subscription", subject_id=sub.id)
    append_audit(db, p.tenant_id, p.user_id, "subscription.create", "subscription", sub.id,
                 before=before_master, after=after_master)
    db.commit()
    return {"subscription_id": sub.id, "units": str(units), "nav_at_entry": str(nav)}

@router.get("/subscriptions")
def list_subscriptions(p: Annotated[Principal, Depends(get_principal)], db: Session = Depends(get_db)):
    q = db.query(Subscription)
    if not p.is_super_admin: q = q.filter(Subscription.tenant_id == p.tenant_id)
    if p.role == "investor": q = q.filter(Subscription.investor_user_id == p.user_id)
    out = []
    for s in q.all():
        inv = db.query(InvestorAccount).filter(InvestorAccount.id == s.investor_account_id).first()
        m = db.query(MasterAccount).filter(MasterAccount.id == s.master_account_id).first()
        nav = pamm.compute_nav(m.equity, m.total_units, m.base_nav) if m else Decimal("0")
        gav = pamm.q2(s.units * nav) if m else Decimal("0")
        out.append({
            "id": s.id, "strategy_id": s.strategy_id, "master_account_id": s.master_account_id,
            "investor_account_id": s.investor_account_id, "investor_login": inv.login if inv else None,
            "master_login": m.login if m else None,
            "units": str(s.units), "contributed_capital": str(s.contributed_capital),
            "start_capital": str(s.start_capital), "end_capital": str(s.end_capital),
            "hwm": str(s.hwm), "status": s.status,
            "current_nav": str(nav), "current_gav": str(gav),
            "unrealized_pnl": str(pamm.q2(gav - s.contributed_capital)),
            "subscribed_at": s.subscribed_at.isoformat() if s.subscribed_at else None,
        })
    return out
