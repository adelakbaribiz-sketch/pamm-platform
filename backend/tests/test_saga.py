"""Settlement saga (P-3): happy path, step failure with compensation, irreversible remediation."""
import uuid
from app.domain.saga import SagaCoordinator, SagaError
from app.models import SettlementSaga, SagaStep

def test_saga_happy_path(db_session, seeded_tenant):
    coord = SagaCoordinator(db_session, seeded_tenant["tenant"].id, seeded_tenant["user"].id)
    saga = coord.create_saga(
        kind="test",
        steps=[{"step_name": "step_a", "is_reversible": True},
               {"step_name": "step_b", "is_reversible": True}],
        payload={"x": 1}, idempotency_key=uuid.uuid4().hex,
    )
    def h_a(s, st, p): return {"a": "ok"}
    def h_b(s, st, p): return {"b": "ok"}
    saga = coord.run(saga, {"step_a": h_a, "step_b": h_b})
    assert saga.status == "completed"
    assert saga.completed_steps == ["step_a", "step_b"]
    # Step rows persisted correctly
    steps = db_session.query(SagaStep).filter(SagaStep.saga_id == saga.saga_id).all()
    assert all(s.status == "completed" for s in steps)

def test_saga_step_failure_triggers_compensation(db_session, seeded_tenant):
    coord = SagaCoordinator(db_session, seeded_tenant["tenant"].id, seeded_tenant["user"].id)
    saga = coord.create_saga(
        kind="test",
        steps=[{"step_name": "step_a", "is_reversible": True},
               {"step_name": "step_b_fails", "is_reversible": True}],
        payload={"x": 1}, idempotency_key=uuid.uuid4().hex,
    )
    compensated = {"called": False}
    def h_a(s, st, p): return {"a": "ok"}
    def h_b_fail(s, st, p): raise Exception("boom")
    def comp_a(s, st, orig): compensated["called"] = True; return {"reversed": True}
    saga = coord.run(saga, {"step_a": h_a, "step_b_fails": h_b_fail},
                     compensators={"step_a": comp_a})
    assert saga.status == "completed"  # compensation succeeded
    assert saga.failed_step == "step_b_fails"
    assert saga.failure_reason == "boom"
    assert len(saga.compensation_log) == 1
    assert saga.compensation_log[0]["action"] == "reverse"
    assert compensated["called"]
    # step_a should be marked compensated
    steps = db_session.query(SagaStep).filter(SagaStep.saga_id == saga.saga_id).all()
    step_a = next(s for s in steps if s.step_name == "step_a")
    assert step_a.status == "compensated"

def test_saga_irreversible_step_logs_remediation(db_session, seeded_tenant):
    """Irreversible external trades must NOT be claimed as reversed."""
    coord = SagaCoordinator(db_session, seeded_tenant["tenant"].id, seeded_tenant["user"].id)
    saga = coord.create_saga(
        kind="test",
        steps=[{"step_name": "external_trade", "is_reversible": False,
                "compensation_action": "remediate"},
               {"step_name": "step_b_fails", "is_reversible": True}],
        payload={}, idempotency_key=uuid.uuid4().hex,
    )
    def h_ext(s, st, p): return {"order_id": "ext-1", "status": "filled"}
    def h_b_fail(s, st, p): raise Exception("downstream error")
    saga = coord.run(saga, {"external_trade": h_ext, "step_b_fails": h_b_fail})
    assert saga.status == "failed"  # remediation leaves saga failed
    log = saga.compensation_log[0]
    assert log["step_name"] == "external_trade"
    assert log["action"] == "remediate"
    assert "irreversible" in log["reason"].lower() or "manual" in log["reason"].lower()
    # step status should reflect remediation, NOT reversal
    steps = db_session.query(SagaStep).filter(SagaStep.saga_id == saga.saga_id).all()
    step_ext = next(s for s in steps if s.step_name == "external_trade")
    assert step_ext.status == "compensated"
    assert step_ext.compensation_payload == {"remediation_required": True}

def test_saga_idempotency(db_session, seeded_tenant):
    """Same idempotency_key returns the same saga."""
    coord = SagaCoordinator(db_session, seeded_tenant["tenant"].id, seeded_tenant["user"].id)
    idem = uuid.uuid4().hex
    s1 = coord.create_saga(kind="test", steps=[], payload={}, idempotency_key=idem)
    s2 = coord.create_saga(kind="test", steps=[], payload={}, idempotency_key=idem)
    assert s1.saga_id == s2.saga_id

def test_saga_resume_after_recovery(db_session, seeded_tenant):
    """A completed-step-preserved saga can resume after interruption."""
    coord = SagaCoordinator(db_session, seeded_tenant["tenant"].id, seeded_tenant["user"].id)
    saga = coord.create_saga(
        kind="test",
        steps=[{"step_name": "step_a"}, {"step_name": "step_b"}],
        payload={}, idempotency_key=uuid.uuid4().hex,
    )
    # Simulate partial completion: step_a done, step_b pending, saga interrupted
    step_a = db_session.query(SagaStep).filter(SagaStep.saga_id == saga.saga_id,
                                                 SagaStep.step_name == "step_a").first()
    step_a.status = "completed"
    step_a.response = {"a": "ok"}
    saga.completed_steps = ["step_a"]
    saga.status = "running"
    db_session.flush()
    # Resume: only step_b should run
    def h_a(s, st, p): raise Exception("should not be called again")
    def h_b(s, st, p): return {"b": "ok"}
    saga = coord.recover(saga, {"step_a": h_a, "step_b": h_b})
    assert saga.status == "completed"
    assert "step_b" in saga.completed_steps
