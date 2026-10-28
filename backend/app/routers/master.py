from typing import Annotated
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..auth import get_principal, Principal, require_roles
from ..db import get_db
from ..models import (Broker, TradingServer, MasterAccount, Strategy, RiskRule)
from ..schemas import BrokerCreate, MasterCreate, StrategyCreate
from ..domain import pamm, risk
from ..domain.events import record_event, append_audit
from ..adapters.simulated import SimulatedAdapter

router = APIRouter()

@router.get("/brokers")
def list_brokers(p: Annotated[Principal, Depends(get_principal)], db: Session = Depends(get_db)):
    q = db.query(Broker)
    if not p.is_super_admin: q = q.filter(Broker.tenant_id == p.tenant_id)
    return [{"id": b.id, "name": b.name, "legal_entity": b.legal_entity, "status": b.status} for b in q.all()]

@router.post("/brokers")
def create_broker(body: BrokerCreate,
                  p: Annotated[Principal, Depends(require_roles("broker_admin"))],
                  db: Session = Depends(get_db)):
    b = Broker(tenant_id=p.tenant_id, name=body.name, legal_entity=body.legal_entity)
    db.add(b); db.flush()
    s = TradingServer(tenant_id=p.tenant_id, broker_id=b.id, name="Simulated",
                      adapter_type="simulated", connection_config={})
    db.add(s); db.flush()
    record_event(db, p.tenant_id, "broker.created", {"broker_id": b.id, "name": b.name},
                 subject_type="broker", subject_id=b.id)
    append_audit(db, p.tenant_id, p.user_id, "broker.create", "broker", b.id, after={"name": b.name})
    db.commit()
    return {"id": b.id, "server_id": s.id, "adapter": s.adapter_type}

@router.get("/servers")
def list_servers(p: Annotated[Principal, Depends(get_principal)], db: Session = Depends(get_db)):
    q = db.query(TradingServer)
    if not p.is_super_admin: q = q.filter(TradingServer.tenant_id == p.tenant_id)
    return [{"id": s.id, "broker_id": s.broker_id, "name": s.name,
             "adapter_type": s.adapter_type, "status": s.status} for s in q.all()]

@router.post("/masters")
def create_master(body: MasterCreate,
                  p: Annotated[Principal, Depends(require_roles("broker_admin", "money_manager"))],
                  db: Session = Depends(get_db)):
    broker = db.query(Broker).filter(Broker.id == body.broker_id, Broker.tenant_id == p.tenant_id).first()
    if not broker: raise HTTPException(404, "Broker not found")
    if body.server_id:
        server = db.query(TradingServer).filter(TradingServer.id == body.server_id,
                                                TradingServer.broker_id == body.broker_id).first()
    else:
        server = db.query(TradingServer).filter(TradingServer.broker_id == body.broker_id).first()
    if not server: raise HTTPException(404, "Server not found")
    if body.allocation_method not in ("euro_days", "start_capital", "end_capital"):
        raise HTTPException(422, "Invalid allocation_method")
    m = MasterAccount(
        tenant_id=p.tenant_id, broker_id=body.broker_id, server_id=server.id,
        login=body.login, currency=body.currency, base_nav=body.base_nav,
        total_units=Decimal("0"), equity=Decimal("0"), hwm=Decimal("0"),
        performance_fee_rate=body.performance_fee_rate,
        management_fee_rate=body.management_fee_rate,
        allocation_method=body.allocation_method, manager_user_id=p.user_id,
        nav_at_period_start=body.base_nav,
    )
    db.add(m); db.flush()
    db.add(RiskRule(tenant_id=p.tenant_id, master_account_id=m.id, name="default_max_exposure",
                   kind="max_total_exposure", params={"limit": "10000000"}, active=True, created_by=p.user_id))
    db.add(RiskRule(tenant_id=p.tenant_id, master_account_id=m.id, name="default_max_drawdown",
                   kind="max_drawdown", params={"limit_pct": "0.5", "peak": "0"}, active=True, created_by=p.user_id))
    record_event(db, p.tenant_id, "master.created",
                 {"master_account_id": m.id, "allocation_method": m.allocation_method},
                 subject_type="master_account", subject_id=m.id)
    append_audit(db, p.tenant_id, p.user_id, "master.create", "master_account", m.id,
                 after={"login": m.login, "method": m.allocation_method})
    db.commit()
    return {"id": m.id, "login": m.login, "allocation_method": m.allocation_method}

@router.get("/masters")
def list_masters(p: Annotated[Principal, Depends(get_principal)], db: Session = Depends(get_db)):
    q = db.query(MasterAccount)
    if not p.is_super_admin: q = q.filter(MasterAccount.tenant_id == p.tenant_id)
    out = []
    for m in q.all():
        out.append({
            "id": m.id, "login": m.login, "currency": m.currency, "broker_id": m.broker_id,
            "equity": str(m.equity), "total_units": str(m.total_units),
            "nav": str(pamm.compute_nav(m.equity, m.total_units, m.base_nav)),
            "base_nav": str(m.base_nav), "hwm": str(m.hwm),
            "performance_fee_rate": str(m.performance_fee_rate),
            "allocation_method": m.allocation_method, "status": m.status,
        })
    return out

@router.post("/strategies")
def create_strategy(body: StrategyCreate,
                    p: Annotated[Principal, Depends(require_roles("broker_admin", "money_manager"))],
                    db: Session = Depends(get_db)):
    m = db.query(MasterAccount).filter(MasterAccount.id == body.master_account_id,
                                       MasterAccount.tenant_id == p.tenant_id).first()
    if not m: raise HTTPException(404, "Master account not found")
    if body.kind not in ("pamm", "mam", "copy"):
        raise HTTPException(422, "Invalid strategy kind")
    s = Strategy(tenant_id=p.tenant_id, master_account_id=body.master_account_id,
                 name=body.name, description=body.description, kind=body.kind)
    db.add(s); db.flush()
    record_event(db, p.tenant_id, "strategy.created",
                 {"strategy_id": s.id, "master_account_id": m.id, "kind": body.kind},
                 subject_type="strategy", subject_id=s.id)
    append_audit(db, p.tenant_id, p.user_id, "strategy.create", "strategy", s.id,
                 after={"name": s.name, "kind": s.kind})
    db.commit()
    return {"id": s.id, "kind": s.kind}

@router.get("/strategies")
def list_strategies(p: Annotated[Principal, Depends(get_principal)], db: Session = Depends(get_db)):
    q = db.query(Strategy)
    if not p.is_super_admin: q = q.filter(Strategy.tenant_id == p.tenant_id)
    return [{"id": s.id, "master_account_id": s.master_account_id, "name": s.name,
             "description": s.description, "kind": s.kind, "status": s.status} for s in q.all()]

@router.post("/simulate-pnl")
def simulate_pnl(master_id: str, pnl: Decimal,
                 p: Annotated[Principal, Depends(require_roles("broker_admin", "money_manager"))],
                 db: Session = Depends(get_db)):
    m = db.query(MasterAccount).filter(MasterAccount.id == master_id,
                                       MasterAccount.tenant_id == p.tenant_id).first()
    if not m: raise HTTPException(404, "Master account not found")
    try:
        risk.check_pnl_mutation(db, p.tenant_id, m.id, m.equity, pnl)
    except risk.RiskError as e:
        db.commit()
        raise HTTPException(422, detail={"code": e.code, "details": e.details})
    sim = SimulatedAdapter({"starting_equity": str(m.equity)})
    new_equity = sim.apply_pnl(pnl)
    before = {"equity": str(m.equity), "hwm": str(m.hwm)}
    m.equity = pamm.q2(new_equity)
    if m.equity > m.hwm: m.hwm = m.equity
    after = {"equity": str(m.equity), "hwm": str(m.hwm)}
    record_event(db, p.tenant_id, "master.pnl.simulated",
                 {"master_account_id": m.id, "pnl": str(pnl), "new_equity": str(m.equity),
                  "adapter": "simulated", "is_live": False},
                 subject_type="master_account", subject_id=m.id)
    append_audit(db, p.tenant_id, p.user_id, "master.simulate_pnl", "master_account", m.id,
                 before=before, after=after, reason="simulated_pnl")
    db.commit()
    return {"master_account_id": m.id, "equity": str(m.equity), "hwm": str(m.hwm),
            "adapter": "simulated", "is_live": False,
            "warning": "SIMULATED — no real orders were placed"}
