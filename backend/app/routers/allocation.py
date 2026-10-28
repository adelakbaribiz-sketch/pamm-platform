"""P-1 router: risk-constrained adaptive allocation."""
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..auth import get_principal, Principal, require_roles
from ..db import get_db
from ..models import (MasterAccount, AllocationProblem, AllocationAlert, Subscription,
                       InvestorAccount, RiskRule)
from ..domain import allocation as alloc_mod
from ..domain.events import record_event, append_audit

router = APIRouter()

class AllocationInvestorIn(BaseModel := __import__("pydantic").BaseModel):
    investor_id: str
    investor_account_id: str | None = None
    subscription_id: str | None = None
    expected_return: Decimal = Decimal("0")
    volatility: Decimal = Decimal("0.01")
    min_allocation: Decimal = Decimal("0")
    max_allocation: Decimal = Decimal("1000000")
    peak_capital: Decimal = Decimal("0")
    drawdown_limit_pct: Decimal = Decimal("1.0")

class AllocationSolveIn(BaseModel):
    master_account_id: str
    objective: str  # maximize_return|minimize_risk|balanced
    free_margin: Decimal
    investors: list[AllocationInvestorIn]
    pairwise_correlations: dict[str, dict[str, Decimal]] | None = None
    max_correlation_exposure: Decimal | None = None
    session_id: str | None = None

@router.post("/allocation/solve")
def solve_allocation(body: AllocationSolveIn,
                     p: Annotated[Principal, Depends(require_roles("broker_admin", "money_manager"))],
                     db: Session = Depends(get_db)):
    m = db.query(MasterAccount).filter(MasterAccount.id == body.master_account_id,
                                       MasterAccount.tenant_id == p.tenant_id).first()
    if not m: raise HTTPException(404, "Master account not found")

    # Validate objective
    if body.objective not in ("maximize_return", "minimize_risk", "balanced"):
        raise HTTPException(422, "Invalid objective")

    # Validate investors + load their peak_capital from active risk rules if not provided
    inv_objs = []
    for inv_in in body.investors:
        ai = alloc_mod.AllocationInvestor(
            investor_id=inv_in.investor_id,
            expected_return=inv_in.expected_return,
            volatility=inv_in.volatility,
            min_allocation=inv_in.min_allocation,
            max_allocation=inv_in.max_allocation,
            peak_capital=inv_in.peak_capital,
            drawdown_limit_pct=inv_in.drawdown_limit_pct,
        )
        # If peak_capital is 0, attempt to read from master_account equity as a fallback peak.
        if ai.peak_capital <= 0:
            ai.peak_capital = m.equity
        inv_objs.append(ai)

    # Build pairwise correlation flat dict
    corr: dict[tuple[str, str], Decimal] = {}
    if body.pairwise_correlations:
        for a, neighbors in body.pairwise_correlations.items():
            for b, c in neighbors.items():
                corr[(a, b)] = Decimal(str(c))

    constraints = alloc_mod.AllocationConstraints(
        free_margin=body.free_margin,
        pairwise_correlations=corr,
        max_correlation_exposure=body.max_correlation_exposure,
    )

    sol = alloc_mod.solve(body.objective, inv_objs, constraints)

    # Persist problem record
    session_id = body.session_id or uuid.uuid4().hex
    prob = AllocationProblem(
        tenant_id=p.tenant_id, master_account_id=m.id, session_id=session_id,
        objective=body.objective,
        investor_ids=[i.investor_id for i in inv_objs],
        constraints={"free_margin": str(body.free_margin),
                     "max_correlation_exposure": str(body.max_correlation_exposure) if body.max_correlation_exposure else None,
                     "investors": [{"id": i.investor_id, "min": str(i.min_allocation),
                                     "max": str(i.max_allocation), "peak": str(i.peak_capital),
                                     "dd_limit": str(i.drawdown_limit_pct)} for i in inv_objs]},
        solver_status=sol.status,
        solution={k: str(v) for k, v in sol.allocations.items()},
        objective_value=sol.objective_value,
        infeasibility_reason=sol.infeasibility_reason,
        frozen=(sol.status in ("infeasible", "suboptimal")),
        alert_emitted=False,
        created_by=p.user_id,
    )
    db.add(prob); db.flush()

    # Emit alert if infeasible or suboptimal
    if sol.status in ("infeasible", "suboptimal"):
        alert = AllocationAlert(
            tenant_id=p.tenant_id, allocation_problem_id=prob.id, master_account_id=m.id,
            kind="infeasible" if sol.status == "infeasible" else "suboptimal",
            details={"reason": sol.infeasibility_reason,
                     "solver_message": sol.solver_message,
                     "fallback_used": sol.fallback_used},
        )
        db.add(alert); db.flush()
        prob.alert_emitted = True
        record_event(db, p.tenant_id, "allocation.alert",
                     {"problem_id": prob.id, "kind": alert.kind, "master_account_id": m.id,
                      "reason": sol.infeasibility_reason},
                     subject_type="allocation_problem", subject_id=prob.id)

    record_event(db, p.tenant_id, "allocation.solved",
                 {"problem_id": prob.id, "status": sol.status,
                  "objective_value": str(sol.objective_value) if sol.objective_value else None,
                  "allocations": {k: str(v) for k, v in sol.allocations.items()}},
                 subject_type="allocation_problem", subject_id=prob.id)
    append_audit(db, p.tenant_id, p.user_id, "allocation.solve", "allocation_problem", prob.id,
                 after={"status": sol.status, "objective": body.objective,
                        "frozen": prob.frozen, "alert_emitted": prob.alert_emitted})
    db.commit()
    return {
        "problem_id": prob.id, "session_id": session_id,
        "status": sol.status,
        "allocations": {k: str(v) for k, v in sol.allocations.items()},
        "objective_value": str(sol.objective_value) if sol.objective_value else None,
        "infeasibility_reason": sol.infeasibility_reason,
        "solver_message": sol.solver_message,
        "fallback_used": sol.fallback_used,
        "frozen": prob.frozen,
        "alert_emitted": prob.alert_emitted,
    }

@router.get("/allocation/problems")
def list_problems(p: Annotated[Principal, Depends(get_principal)],
                  db: Session = Depends(get_db)):
    q = db.query(AllocationProblem)
    if not p.is_super_admin: q = q.filter(AllocationProblem.tenant_id == p.tenant_id)
    return [{
        "id": pr.id, "master_account_id": pr.master_account_id,
        "session_id": pr.session_id, "objective": pr.objective,
        "status": pr.solver_status, "frozen": pr.frozen,
        "alert_emitted": pr.alert_emitted,
        "objective_value": str(pr.objective_value) if pr.objective_value else None,
        "created_at": pr.created_at.isoformat(),
    } for pr in q.order_by(AllocationProblem.created_at.desc()).limit(50).all()]

@router.get("/allocation/problems/{problem_id}")
def get_problem(problem_id: str, p: Annotated[Principal, Depends(get_principal)],
                db: Session = Depends(get_db)):
    pr = db.query(AllocationProblem).filter(AllocationProblem.id == problem_id).first()
    if not pr: raise HTTPException(404, "Not found")
    if not p.is_super_admin and pr.tenant_id != p.tenant_id:
        raise HTTPException(403, "Cross-tenant access denied")
    return {
        "id": pr.id, "master_account_id": pr.master_account_id, "session_id": pr.session_id,
        "objective": pr.objective, "investor_ids": pr.investor_ids,
        "constraints": pr.constraints, "status": pr.solver_status,
        "solution": pr.solution, "objective_value": str(pr.objective_value) if pr.objective_value else None,
        "infeasibility_reason": pr.infeasibility_reason,
        "frozen": pr.frozen, "alert_emitted": pr.alert_emitted,
        "created_at": pr.created_at.isoformat(),
    }

@router.post("/allocation/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str,
                      p: Annotated[Principal, Depends(require_roles("broker_admin", "compliance"))],
                      db: Session = Depends(get_db)):
    a = db.query(AllocationAlert).filter(AllocationAlert.id == alert_id).first()
    if not a: raise HTTPException(404, "Alert not found")
    if not p.is_super_admin and a.tenant_id != p.tenant_id:
        raise HTTPException(403, "Cross-tenant access denied")
    a.acknowledged = True
    a.acknowledged_by = p.user_id
    a.acknowledged_at = datetime.now(timezone.utc)
    append_audit(db, p.tenant_id, p.user_id, "allocation.alert.ack", "allocation_alert", a.id)
    db.commit()
    return {"alert_id": a.id, "acknowledged": a.acknowledged}

@router.get("/allocation/alerts")
def list_alerts(p: Annotated[Principal, Depends(get_principal)],
                db: Session = Depends(get_db)):
    q = db.query(AllocationAlert)
    if not p.is_super_admin: q = q.filter(AllocationAlert.tenant_id == p.tenant_id)
    return [{
        "id": a.id, "problem_id": a.allocation_problem_id,
        "master_account_id": a.master_account_id, "kind": a.kind,
        "details": a.details, "acknowledged": a.acknowledged,
        "acknowledged_by": a.acknowledged_by,
        "created_at": a.created_at.isoformat(),
    } for a in q.order_by(AllocationAlert.created_at.desc()).limit(50).all()]
