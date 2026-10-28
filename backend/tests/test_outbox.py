"""Outbox worker tests."""
from app.domain import events
from app.domain.outbox import drain, stats
from app.models import Outbox

def test_outbox_stats_empty(db_session, seeded_tenant):
    s = stats(db_session, seeded_tenant["tenant"].id)
    assert s == {"pending": 0, "delivered": 0, "dead_letter": 0}

def test_drain_marks_delivered(db_session, seeded_tenant):
    ev = events.record_event(db_session, seeded_tenant["tenant"].id, "test.outbox",
                              {"x": 1})
    db_session.flush()
    # One outbox row should be pending
    s_before = stats(db_session, seeded_tenant["tenant"].id)
    assert s_before["pending"] == 1
    result = drain(db_session, tenant_id=seeded_tenant["tenant"].id, limit=10)
    assert result["processed"] == 1
    assert result["delivered"] == 1
    s_after = stats(db_session, seeded_tenant["tenant"].id)
    assert s_after["pending"] == 0
    assert s_after["delivered"] == 1

def test_drain_idempotent(db_session, seeded_tenant):
    events.record_event(db_session, seeded_tenant["tenant"].id, "test.outbox", {"x": 1})
    db_session.flush()
    # Drain once
    drain(db_session, tenant_id=seeded_tenant["tenant"].id, limit=10)
    # Drain again — nothing pending
    result = drain(db_session, tenant_id=seeded_tenant["tenant"].id, limit=10)
    assert result["processed"] == 0

def test_dead_letter_on_missing_event(db_session, seeded_tenant):
    """If the referenced event is deleted (corrupted outbox), drain should eventually dead-letter."""
    # Create a real event + outbox row, then delete the event so the outbox reference is dangling.
    # Note: foreign keys would normally prevent this. We bypass via raw SQL delete.
    from uuid import uuid4
    ev = events.record_event(db_session, seeded_tenant["tenant"].id, "test.doomed",
                              {"x": 1})
    db_session.flush()
    outbox_row = db_session.query(Outbox).filter(Outbox.event_id == ev.event_id).first()
    # Delete the event row via raw SQL to simulate a corrupted state
    from sqlalchemy import text
    db_session.execute(text("DELETE FROM outbox WHERE event_id = :eid"), {"eid": ev.event_id})
    db_session.execute(text("DELETE FROM events WHERE event_id = :eid"), {"eid": ev.event_id})
    # Re-insert the orphaned outbox row, bypassing the FK (allowed since the table is empty)
    db_session.execute(text("INSERT INTO outbox (id, tenant_id, event_id, status, attempts, created_at) VALUES (:id, :tid, :eid, 'pending', 0, NOW())"),
                       {"id": str(uuid4()), "tid": seeded_tenant["tenant"].id, "eid": ev.event_id})
    db_session.flush()
    # Drain — should fail (event not found), attempts += 1
    r1 = drain(db_session, tenant_id=seeded_tenant["tenant"].id, limit=10)
    assert r1["errors"] == 1
    # Repeat MAX_ATTEMPTS-1 more times until dead_letter
    from app.domain.outbox import MAX_ATTEMPTS
    for _ in range(MAX_ATTEMPTS - 1):
        drain(db_session, tenant_id=seeded_tenant["tenant"].id, limit=10)
    s = stats(db_session, seeded_tenant["tenant"].id)
    assert s["dead_letter"] >= 1

def test_drain_tenant_isolation(db_session, seeded_tenant):
    """drain must not touch other tenant's outbox rows."""
    from app.models import Tenant
    t2 = Tenant(name="Other", slug="other-x"); db_session.add(t2); db_session.flush()
    # Create an outbox row in t2
    events.record_event(db_session, t2.id, "test.outbox", {"y": 2})
    db_session.flush()
    # Drain as seeded_tenant
    drain(db_session, tenant_id=seeded_tenant["tenant"].id, limit=10)
    # The t2 row should still be pending (untouched)
    from app.models import Outbox as O
    t2_pending = db_session.query(O).filter(O.tenant_id == t2.id, O.status == "pending").count()
    assert t2_pending == 1
