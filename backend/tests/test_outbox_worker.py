"""Outbox worker tests: drain via DB fallback, idempotency, dead-letter, tenant isolation.

NOTE: These tests use SessionLocal directly (bypassing conftest's transactional
fixture) because the worker needs to commit changes for cross-session visibility.
Each test creates its own tenant + events and cleans up at the end.
"""
import os, threading, time, uuid
from sqlalchemy import text
from app.db import SessionLocal, Base, engine
from app.domain import events
from app.domain.outbox_worker import OutboxWorker, MAX_ATTEMPTS
from app.models import Outbox, Tenant, User, Broker, TradingServer, MasterAccount
from app.auth import hash_password
from decimal import Decimal

# Ensure these tests use an UNREACHABLE redis (DB fallback path), even if
# USE_FAKEREDIS=1 is set globally by other test files.
os.environ.pop("USE_FAKEREDIS", None)


def _make_worker():
    return OutboxWorker(SessionLocal, redis_url="redis://invalid:6379/0")


def _setup_tenant():
    """Create a fresh tenant directly in the DB (committed)."""
    db = SessionLocal()
    try:
        t = Tenant(name=f"OW-{uuid.uuid4().hex[:6]}",
                   slug=f"ow-{uuid.uuid4().hex[:8]}")
        db.add(t); db.commit()
        return t.id
    finally:
        db.close()


def test_worker_drain_via_db_fallback():
    """When Redis is unavailable, worker drains via DB fallback."""
    tenant_id = _setup_tenant()
    try:
        db = SessionLocal()
        try:
            events.record_event(db, tenant_id, "test.event", {"x": 1})
            db.commit()
        finally:
            db.close()
        worker = _make_worker()
        result = worker.drain_pending(limit=10, tenant_id=tenant_id)
        assert result["processed"] == 1
        assert result["delivered"] == 1
        assert result["redis_used"] is False
    finally:
        _cleanup_tenant(tenant_id)


def test_worker_drain_idempotent():
    """Re-draining the same row returns 0 processed (already delivered)."""
    tenant_id = _setup_tenant()
    try:
        db = SessionLocal()
        try:
            events.record_event(db, tenant_id, "test.event", {"x": 1})
            db.commit()
        finally:
            db.close()
        worker = _make_worker()
        r1 = worker.drain_pending(limit=10, tenant_id=tenant_id)
        assert r1["delivered"] == 1
        r2 = worker.drain_pending(limit=10, tenant_id=tenant_id)
        assert r2["processed"] == 0
        assert r2["delivered"] == 0
    finally:
        _cleanup_tenant(tenant_id)


def test_worker_dead_letter_on_missing_event():
    """Orphaned outbox rows (event deleted) eventually move to dead_letter."""
    tenant_id = _setup_tenant()
    try:
        orphan_id = str(uuid.uuid4())
        orphan_eid = str(uuid.uuid4())
        db = SessionLocal()
        try:
            db.execute(text(
                "INSERT INTO outbox (id, tenant_id, event_id, status, attempts, created_at) "
                "VALUES (:id, :tid, :eid, 'pending', 0, NOW())"
            ), {"id": orphan_id, "tid": tenant_id, "eid": orphan_eid})
            db.commit()
        finally:
            db.close()
        worker = _make_worker()
        for _ in range(MAX_ATTEMPTS):
            worker.drain_pending(limit=10, tenant_id=tenant_id)
        with SessionLocal() as s:
            db_rows = s.query(Outbox).filter(
                Outbox.tenant_id == tenant_id,
                Outbox.status == "dead_letter"
            ).count()
        assert db_rows >= 1
    finally:
        _cleanup_tenant(tenant_id)


def test_worker_tenant_isolation():
    """Drain for tenant A must not touch tenant B's rows."""
    tenant_a = _setup_tenant()
    tenant_b = _setup_tenant()
    try:
        # Create an event in tenant B
        db = SessionLocal()
        try:
            events.record_event(db, tenant_b, "test.event", {"y": 2})
            db.commit()
        finally:
            db.close()
        # Drain for tenant A — should not touch tenant B's row
        worker = _make_worker()
        worker.drain_pending(limit=10, tenant_id=tenant_a)
        with SessionLocal() as s:
            t2_pending = s.query(Outbox).filter(
                Outbox.tenant_id == tenant_b, Outbox.status == "pending"
            ).count()
        assert t2_pending == 1
    finally:
        _cleanup_tenant(tenant_a)
        _cleanup_tenant(tenant_b)


def test_worker_run_forever_can_be_stopped():
    """run_forever blocks but stops cleanly when stop() is called."""
    worker = _make_worker()
    def stop_after_delay():
        time.sleep(0.5)
        worker.stop()
    threading.Thread(target=stop_after_delay, daemon=True).start()
    start = time.monotonic()
    worker.run_forever(poll_interval=0.1, batch_size=10)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0


def _cleanup_tenant(tenant_id: str):
    """Delete test data for a tenant (cascades to outbox/events)."""
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM outbox WHERE tenant_id = :tid"), {"tid": tenant_id})
        db.execute(text("DELETE FROM events WHERE tenant_id = :tid"), {"tid": tenant_id})
        db.execute(text("DELETE FROM tenants WHERE id = :tid"), {"tid": tenant_id})
        db.commit()
    finally:
        db.close()
