"""Settlement saga router (P-3)."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..auth import get_principal, Principal, require_roles
from ..db import get_db
from ..models import SettlementSaga, SagaStep
from ..domain import saga as saga_mod

router = APIRouter()

@router.get("/sagas")
def list_sagas(p: Annotated[Principal, Depends(get_principal)], db: Session = Depends(get_db),
               kind: str | None = None, status: str | None = None):
    q = db.query(SettlementSaga)
    if not p.is_super_admin: q = q.filter(SettlementSaga.tenant_id == p.tenant_id)
    if kind: q = q.filter(SettlementSaga.kind == kind)
    if status: q = q.filter(SettlementSaga.status == status)
    return [{
        "saga_id": s.saga_id, "kind": s.kind, "status": s.status,
        "failed_step": s.failed_step, "failure_reason": s.failure_reason,
        "completed_steps": s.completed_steps or [],
        "compensation_log": s.compensation_log or [],
        "idempotency_key": s.idempotency_key,
        "created_at": s.created_at.isoformat(), "updated_at": s.updated_at.isoformat(),
    } for s in q.order_by(SettlementSaga.created_at.desc()).limit(100).all()]

@router.get("/sagas/{saga_id}")
def get_saga(saga_id: str, p: Annotated[Principal, Depends(get_principal)],
             db: Session = Depends(get_db)):
    s = db.query(SettlementSaga).filter(SettlementSaga.saga_id == saga_id).first()
    if not s: raise HTTPException(404, "Saga not found")
    if not p.is_super_admin and s.tenant_id != p.tenant_id:
        raise HTTPException(403, "Cross-tenant access denied")
    steps = db.query(SagaStep).filter(SagaStep.saga_id == saga_id).order_by(SagaStep.ord.asc()).all()
    return {
        "saga_id": s.saga_id, "kind": s.kind, "status": s.status,
        "payload": s.payload, "steps_spec": s.steps,
        "completed_steps": s.completed_steps or [],
        "failed_step": s.failed_step, "failure_reason": s.failure_reason,
        "compensation_log": s.compensation_log or [],
        "idempotency_key": s.idempotency_key,
        "step_records": [{
            "step_name": st.step_name, "ord": st.ord, "status": st.status,
            "request": st.request, "response": st.response, "error": st.error,
            "attempts": st.attempts, "is_reversible": st.is_reversible,
            "compensation_action": st.compensation_action,
            "compensation_payload": st.compensation_payload,
            "started_at": st.started_at.isoformat() if st.started_at else None,
            "completed_at": st.completed_at.isoformat() if st.completed_at else None,
        } for st in steps],
        "created_at": s.created_at.isoformat(), "updated_at": s.updated_at.isoformat(),
    }

@router.post("/sagas/{saga_id}/recover")
def recover_saga(saga_id: str,
                p: Annotated[Principal, Depends(require_roles("broker_admin", "money_manager"))],
                db: Session = Depends(get_db)):
    """Recover a saga that was interrupted. Step handlers must be re-registered externally
    (this endpoint just re-flags it for running and skips already-completed steps).
    """
    s = db.query(SettlementSaga).filter(SettlementSaga.saga_id == saga_id).first()
    if not s: raise HTTPException(404, "Saga not found")
    if not p.is_super_admin and s.tenant_id != p.tenant_id:
        raise HTTPException(403, "Cross-tenant access denied")
    if s.status == "completed":
        return {"saga_id": saga_id, "status": "completed", "message": "already completed"}
    # Mark running so the next handler invocation can pick up from the last completed step.
    s.status = "running"
    s.failed_step = None
    s.failure_reason = None
    db.commit()
    return {
        "saga_id": saga_id, "status": "running",
        "completed_steps": s.completed_steps,
        "note": "Saga re-flagged for running; rerun the same step handlers via the original endpoint.",
    }
