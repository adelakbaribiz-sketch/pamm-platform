"""
Transactional outbox worker — drains pending rows from `outbox` and marks
them 'delivered'. In M3 we provide an in-process poller that can be invoked
from the API or a CLI script. For production deployment, the same drain
function would be called by a separate worker process that publishes to
Redis Streams (consumer groups).

This implementation:
  - Polls `outbox` rows in status='pending'.
  - For each row: increments attempts, attempts to "deliver" (simulated by
    checking that the referenced event exists and is consistent).
  - On success: marks 'delivered', records delivered_at.
  - On failure: increments attempts; if attempts >= MAX_ATTEMPTS, marks
    'dead_letter'. Otherwise leaves pending for retry.
  - Idempotent: re-running on the same row is safe.

The worker is exposed via:
  - `POST /api/outbox/drain` (admin only) — drain pending rows now.
  - `GET /api/outbox/stats` — show pending/delivered/dead_letter counts.
"""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text
from ..models import Outbox, Event

MAX_ATTEMPTS = 5

def drain(db: Session, tenant_id: str | None = None, limit: int = 100) -> dict:
    """
    Drain pending outbox rows. Returns dict {processed, delivered, dead_lettered, errors}.
    """
    q = db.query(Outbox).filter(Outbox.status == "pending")
    if tenant_id:
        q = q.filter(Outbox.tenant_id == tenant_id)
    rows = q.limit(limit).all()
    processed = 0; delivered = 0; dead = 0; errors = 0
    for row in rows:
        processed += 1
        # Verify the referenced event exists
        ev = db.query(Event).filter(Event.event_id == row.event_id).first()
        if not ev:
            row.attempts += 1
            row.last_error = "event_not_found"
            if row.attempts >= MAX_ATTEMPTS:
                row.status = "dead_letter"
                dead += 1
            else:
                errors += 1
            continue
        # Simulate publish to Redis Streams. In production this would be:
        #   redis.xadd(stream_key, {"event_id": ev.event_id, "type": ev.type,
        #                            "tenant_id": ev.tenant_id, "payload": json.dumps(ev.payload)})
        # Here we just mark delivered.
        row.status = "delivered"
        row.delivered_at = datetime.now(timezone.utc)
        row.attempts += 1
        delivered += 1
    db.commit()
    return {"processed": processed, "delivered": delivered,
            "dead_lettered": dead, "errors": errors}

def stats(db: Session, tenant_id: str | None = None) -> dict:
    """Return counts of outbox rows by status."""
    if tenant_id is None:
        sql = text("""
            SELECT status, COUNT(*) as n
            FROM outbox
            GROUP BY status
        """)
        rows = db.execute(sql).fetchall()
    else:
        sql = text("""
            SELECT status, COUNT(*) as n
            FROM outbox
            WHERE tenant_id = :tid
            GROUP BY status
        """)
        rows = db.execute(sql, {"tid": tenant_id}).fetchall()
    out = {"pending": 0, "delivered": 0, "dead_letter": 0}
    for r in rows:
        out[r[0]] = r[1]
    return out
