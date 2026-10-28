"""Idempotency: unique event_id + audit chain integrity + tamper detection."""
from decimal import Decimal
from app.domain import events
from app.models import Event, AuditLog

def test_event_id_unique(db_session, seeded_tenant):
    ev1 = events.record_event(db_session, seeded_tenant["tenant"].id, "test.event", {"x": 1})
    db_session.flush()
    e2 = Event(tenant_id=seeded_tenant["tenant"].id, event_id=ev1.event_id,
               type="test.event", payload={"x": 2})
    db_session.add(e2)
    try:
        db_session.flush()
        assert False, "should have raised"
    except Exception:
        db_session.rollback()

def test_audit_chain_intact(db_session, seeded_tenant):
    events.append_audit(db_session, seeded_tenant["tenant"].id, None, "a", "t", "1", after={"v": 1})
    events.append_audit(db_session, seeded_tenant["tenant"].id, None, "b", "t", "2", after={"v": 2})
    events.append_audit(db_session, seeded_tenant["tenant"].id, None, "c", "t", "3", after={"v": 3})
    db_session.flush()
    assert events.verify_audit_chain(db_session, seeded_tenant["tenant"].id)

def test_audit_chain_tamper_detected(db_session, seeded_tenant):
    events.append_audit(db_session, seeded_tenant["tenant"].id, None, "a", "t", "1", after={"v": 1})
    events.append_audit(db_session, seeded_tenant["tenant"].id, None, "b", "t", "2", after={"v": 2})
    db_session.flush()
    first = db_session.query(AuditLog).filter(AuditLog.tenant_id == seeded_tenant["tenant"].id).first()
    first.hash = "tampered"
    db_session.flush()
    assert not events.verify_audit_chain(db_session, seeded_tenant["tenant"].id)
