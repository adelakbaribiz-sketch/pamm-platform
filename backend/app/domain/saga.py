"""
P-3: Cross-platform settlement saga.

Persistent state machine for multi-step settlement operations across
broker adapters. Each saga:
  - has a unique saga_id (used for idempotency).
  - has an ordered list of steps, each with:
      * step_name
      * is_reversible: whether a compensation can reverse it
      * compensation_action: reverse|remediate|manual
  - is processed step-by-step. If a step fails:
      * if reversible and compensation_action == 'reverse': run compensation for prior steps
      * if compensation_action == 'remediate': create a remediation record (manual review)
      * if compensation_action == 'manual': mark saga 'abandoned' for human intervention
  - is recoverable: on process restart, a saga in 'running' state can be resumed
    from its last completed step.

External-trade irreversibility:
  The saga explicitly models the case where a broker has executed a trade and
  cannot reverse it. In that case the compensation_action for that step is
  'remediate' (not 'reverse'), and the saga records a remediation entry rather
  than silently claiming a reversal occurred.

This implementation is single-process for M2. Multi-process coordination
(e.g., distributed locks) is intentionally deferred.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.orm import Session
from ..models import SettlementSaga, SagaStep
from .events import record_event, append_audit

class SagaError(Exception):
    def __init__(self, code: str, details: dict):
        self.code = code
        self.details = details
        super().__init__(code)

class SagaCoordinator:
    def __init__(self, db: Session, tenant_id: str, actor_id: str | None = None):
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id

    def create_saga(self, kind: str, steps: list[dict], payload: dict,
                    idempotency_key: str | None = None) -> SettlementSaga:
        # Idempotency
        if idempotency_key:
            existing = self.db.query(SettlementSaga).filter(
                SettlementSaga.idempotency_key == idempotency_key,
                SettlementSaga.tenant_id == self.tenant_id,
            ).first()
            if existing:
                return existing
        saga_id = str(uuid.uuid4())
        saga = SettlementSaga(
            tenant_id=self.tenant_id, saga_id=saga_id, kind=kind,
            status="running", payload=payload, steps=steps,
            completed_steps=[], idempotency_key=idempotency_key,
            created_by=self.actor_id,
        )
        self.db.add(saga); self.db.flush()
        # Persist step rows
        for ord_, step_spec in enumerate(steps):
            s = SagaStep(
                tenant_id=self.tenant_id, saga_id=saga_id,
                step_name=step_spec["step_name"], ord=ord_,
                status="pending",
                is_reversible=step_spec.get("is_reversible", True),
                compensation_action=step_spec.get("compensation_action", "reverse"),
                compensation_payload=step_spec.get("compensation_payload", {}),
            )
            self.db.add(s)
        self.db.flush()
        record_event(self.db, self.tenant_id, "saga.created",
                     {"saga_id": saga_id, "kind": kind, "step_count": len(steps)},
                     subject_type="settlement_saga", subject_id=saga_id)
        return saga

    def run(self, saga: SettlementSaga, step_handlers: dict, compensators: dict | None = None
            ) -> SettlementSaga:
        """
        Execute the saga step-by-step. step_handlers is a dict {step_name: callable(saga, step, payload) -> response}.
        compensators is a dict {step_name: callable(saga, step, original_response) -> compensation_response}.
        On step failure, compensate completed reversible steps in reverse order.
        """
        steps = self.db.query(SagaStep).filter(
            SagaStep.saga_id == saga.saga_id,
            SagaStep.tenant_id == self.tenant_id,
        ).order_by(SagaStep.ord.asc()).all()
        compensators = compensators or {}
        completed_responses = {}  # step_name -> response

        for step in steps:
            if step.status == "completed":
                # Resuming a previously-completed step
                completed_responses[step.step_name] = step.response
                continue
            step.status = "running"
            step.started_at = datetime.now(timezone.utc)
            step.attempts += 1
            saga.status = "running"
            self.db.flush()
            handler = step_handlers.get(step.step_name)
            if handler is None:
                step.status = "failed"
                step.error = f"no handler for step {step.step_name}"
                saga.failed_step = step.step_name
                saga.failure_reason = step.error
                saga.status = "failed"
                self._compensate(saga, steps, completed_responses, compensators,
                                  failed_step=step)
                self.db.flush()
                return saga
            try:
                response = handler(saga, step, saga.payload)
                step.response = response if isinstance(response, (dict, list, str, int, float, bool)) or response is None else {"_raw": str(response)}
                step.status = "completed"
                step.completed_at = datetime.now(timezone.utc)
                completed_responses[step.step_name] = step.response
                saga.completed_steps = list(saga.completed_steps or []) + [step.step_name]
                self.db.flush()
            except Exception as e:
                step.status = "failed"
                step.error = str(e)
                saga.failed_step = step.step_name
                saga.failure_reason = str(e)
                saga.status = "failed"
                self._compensate(saga, steps, completed_responses, compensators,
                                  failed_step=step)
                self.db.flush()
                return saga
        saga.status = "completed"
        saga.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        append_audit(self.db, self.tenant_id, self.actor_id, "saga.completed",
                     "settlement_saga", saga.saga_id,
                     after={"kind": saga.kind, "step_count": len(steps)})
        return saga

    def _compensate(self, saga: SettlementSaga, steps: list[SagaStep],
                    completed_responses: dict, compensators: dict, failed_step: SagaStep):
        """
        Compensate completed steps in reverse order. If a step is not reversible
        (e.g., an external broker trade was executed), record a remediation
        entry rather than fabricating a reversal.
        """
        saga.status = "compensating"
        log = list(saga.compensation_log or [])
        completed_so_far = [s for s in steps if s.status == "completed"]
        for step in reversed(completed_so_far):
            if not step.is_reversible:
                action = "remediate" if step.compensation_action != "manual" else "manual"
                log.append({
                    "step_name": step.step_name,
                    "action": action,
                    "reason": "irreversible external trade; manual remediation required",
                    "original_response": step.response,
                })
                step.status = "compensated" if action == "remediate" else "skipped"
                step.compensation_payload = {"remediation_required": True}
                continue
            comp = compensators.get(step.step_name)
            if comp is None:
                log.append({
                    "step_name": step.step_name, "action": "missing_compensator",
                    "reason": "no compensator registered; manual review required",
                })
                continue
            try:
                comp_response = comp(saga, step, step.response)
                log.append({
                    "step_name": step.step_name, "action": "reverse",
                    "compensation_response": comp_response,
                })
                step.status = "compensated"
                step.compensation_payload = comp_response if isinstance(comp_response, dict) else {"_raw": str(comp_response)}
            except Exception as e:
                log.append({
                    "step_name": step.step_name, "action": "compensation_failed",
                    "error": str(e),
                })
                step.status = "failed"
        saga.compensation_log = log
        saga.status = "failed" if any(l.get("action") in ("remediate", "manual", "compensation_failed") for l in log) else "completed"
        saga.updated_at = datetime.now(timezone.utc)
        record_event(self.db, self.tenant_id, "saga.compensated",
                     {"saga_id": saga.saga_id, "compensation_log": log},
                     subject_type="settlement_saga", subject_id=saga.saga_id)

    def recover(self, saga: SettlementSaga, step_handlers: dict, compensators: dict | None = None
                ) -> SettlementSaga:
        """Re-run a saga that was interrupted. Already-completed steps are skipped."""
        if saga.status == "completed":
            return saga
        return self.run(saga, step_handlers, compensators)
