"""MAM router: master-order splitting into child tickets via settlement saga (P-3)."""
import uuid
from decimal import Decimal
from typing import Annotated
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..auth import get_principal, Principal, require_roles
from ..db import get_db
from ..models import (MasterAccount, Subscription, InvestorAccount, MamChildOrder,
                      SettlementSaga, SagaStep)
from ..schemas import MamSplitIn, MamSplitOut, MamChildOut
from ..domain import mam as mam_mod, risk, saga as saga_mod
from ..domain.events import record_event, append_audit
from ..adapters.simulated import SimulatedAdapter

router = APIRouter()

@router.post("/mam/split", response_model=MamSplitOut)
def split_master_order(body: MamSplitIn,
                       p: Annotated[Principal, Depends(require_roles("broker_admin", "money_manager"))],
                       db: Session = Depends(get_db)):
    # Idempotency: reuse prior split if same idempotency_key + tenant + master
    existing_saga = db.query(SettlementSaga).filter(
        SettlementSaga.idempotency_key == body.idempotency_key,
        SettlementSaga.tenant_id == p.tenant_id,
    ).first()
    if existing_saga:
        children = db.query(MamChildOrder).filter(
            MamChildOrder.master_order_id == existing_saga.payload.get("master_order_id"),
            MamChildOrder.tenant_id == p.tenant_id,
        ).all()
        return _serialize_split(existing_saga, children, db)

    m = db.query(MasterAccount).filter(MasterAccount.id == body.master_account_id,
                                       MasterAccount.tenant_id == p.tenant_id).first()
    if not m: raise HTTPException(404, "Master account not found")
    if body.side not in ("buy", "sell"): raise HTTPException(422, "Invalid side")
    if body.method not in ("equity_ratio", "balance_ratio", "fixed_lot_mult", "percentage"):
        raise HTTPException(422, "Invalid method")

    # Validate investors
    investors = []
    for inv_in in body.investors:
        sub = db.query(Subscription).filter(Subscription.id == inv_in.subscription_id,
                                            Subscription.master_account_id == m.id,
                                            Subscription.tenant_id == p.tenant_id,
                                            Subscription.status == "active").first()
        if not sub: raise HTTPException(404, f"Subscription {inv_in.subscription_id} not found under master")
        inv_acc = db.query(InvestorAccount).filter(InvestorAccount.id == inv_in.investor_account_id,
                                                    InvestorAccount.tenant_id == p.tenant_id).first()
        if not inv_acc: raise HTTPException(404, f"Investor account {inv_in.investor_account_id} not found")
        investors.append(mam_mod.MamInvestor(
            subscription_id=inv_in.subscription_id, investor_account_id=inv_in.investor_account_id,
            equity=inv_in.equity, balance=inv_in.balance,
            percentage=inv_in.percentage, lot_multiplier=inv_in.lot_multiplier,
        ))

    # Risk check on master order
    try:
        risk.check_order(db, p.tenant_id, m.id, body.symbol, body.master_lots, body.price)
    except risk.RiskError as e:
        db.commit()
        raise HTTPException(422, detail={"code": e.code, "details": e.details})

    # Run allocation
    allocations = mam_mod.split_order(body.master_lots, investors, body.method, body.lot_step)
    reconciled = mam_mod.reconcile(allocations, body.master_lots, body.lot_step)

    master_order_id = str(uuid.uuid4())

    # Build settlement saga
    steps_spec = [
        {"step_name": "split_master_order", "is_reversible": True, "compensation_action": "reverse",
         "compensation_payload": {"master_order_id": master_order_id}},
    ]
    for alloc in allocations:
        steps_spec.append({
            "step_name": f"submit_child:{alloc.subscription_id}",
            "is_reversible": True, "compensation_action": "reverse",
            "compensation_payload": {"subscription_id": alloc.subscription_id,
                                     "lots": str(alloc.allocated_lots)},
        })

    coord = saga_mod.SagaCoordinator(db, p.tenant_id, p.user_id)
    saga = coord.create_saga(
        kind="mam_batch",
        steps=steps_spec,
        payload={"master_account_id": m.id, "master_order_id": master_order_id,
                 "symbol": body.symbol, "side": body.side, "master_lots": str(body.master_lots),
                 "method": body.method, "lot_step": str(body.lot_step)},
        idempotency_key=body.idempotency_key,
    )

    # Step 1 handler: persist child orders
    def step_split(saga_obj, step, payload):
        for alloc in allocations:
            sim = SimulatedAdapter({"starting_equity": "0"})
            order_resp = sim.submit_order(login="master", symbol=body.symbol,
                                          side=body.side, lots=alloc.allocated_lots, price=body.price)
            child = MamChildOrder(
                tenant_id=p.tenant_id, master_order_id=master_order_id,
                master_account_id=m.id, subscription_id=alloc.subscription_id,
                investor_account_id=alloc.investor_account_id,
                symbol=body.symbol, side=body.side,
                requested_lots=alloc.requested_lots, allocated_lots=alloc.allocated_lots,
                residual_lots=alloc.residual_lots,
                price=body.price, status="filled",
                filled_lots=alloc.allocated_lots, fill_price=body.price,
            )
            db.add(child); db.flush()
        record_event(db, p.tenant_id, "mam.split.completed",
                     {"master_order_id": master_order_id, "child_count": len(allocations)},
                     subject_type="master_order", subject_id=master_order_id)
        return {"master_order_id": master_order_id, "child_count": len(allocations)}

    # Step N handler: confirm child fill (simulated)
    def make_step_child(sid):
        def h(saga_obj, step, payload):
            return {"subscription_id": sid, "confirmed": True, "adapter": "simulated"}
        return h

    step_handlers = {"split_master_order": step_split}
    for alloc in allocations:
        step_handlers[f"submit_child:{alloc.subscription_id}"] = make_step_child(alloc.subscription_id)

    def comp_split(saga_obj, step, original_response):
        # Mark all children as rejected (simulated reversal)
        for child in db.query(MamChildOrder).filter(MamChildOrder.master_order_id == master_order_id).all():
            child.status = "rejected"
            child.reject_reason = "saga_compensation"
        record_event(db, p.tenant_id, "mam.split.compensated",
                     {"master_order_id": master_order_id},
                     subject_type="master_order", subject_id=master_order_id)
        return {"reversed_children": len(allocations)}

    compensators = {"split_master_order": comp_split}

    saga = coord.run(saga, step_handlers, compensators)
    append_audit(db, p.tenant_id, p.user_id, "mam.split.execute", "master_order", master_order_id,
                 after={"saga_id": saga.saga_id, "saga_status": saga.status,
                        "child_count": len(allocations), "reconciled": reconciled})
    db.commit()

    children = db.query(MamChildOrder).filter(
        MamChildOrder.master_order_id == master_order_id,
        MamChildOrder.tenant_id == p.tenant_id,
    ).all()
    return _serialize_split(saga, children, db)

@router.get("/mam/orders/{master_order_id}")
def get_master_order(master_order_id: str,
                     p: Annotated[Principal, Depends(get_principal)],
                     db: Session = Depends(get_db)):
    children = db.query(MamChildOrder).filter(
        MamChildOrder.master_order_id == master_order_id,
        MamChildOrder.tenant_id == p.tenant_id,
    ).all()
    if not children: raise HTTPException(404, "Order not found")
    return [_serialize_child(c) for c in children]

def _serialize_split(saga: SettlementSaga, children, db) -> MamSplitOut:
    out_children = [_serialize_child(c) for c in children]
    return MamSplitOut(
        master_order_id=saga.payload.get("master_order_id"),
        children=out_children,
        reconciled=mam_mod.reconcile(
            [mam_mod.MamChildAllocation(c.subscription_id, c.investor_account_id,
                                        c.requested_lots, c.allocated_lots, c.residual_lots)
             for c in children],
            Decimal(saga.payload.get("master_lots", "0")),
            Decimal(saga.payload.get("lot_step", "0.01")),
        ) if children else False,
        saga_id=saga.saga_id,
    )

def _serialize_child(c: MamChildOrder) -> MamChildOut:
    return MamChildOut(
        subscription_id=c.subscription_id, investor_account_id=c.investor_account_id,
        requested_lots=c.requested_lots, allocated_lots=c.allocated_lots,
        residual_lots=c.residual_lots, status=c.status,
        fill_price=c.fill_price, reject_reason=c.reject_reason,
    )
