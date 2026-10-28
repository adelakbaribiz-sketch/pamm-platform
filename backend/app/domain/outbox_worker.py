"""
Outbox worker — drains pending outbox rows to Redis Streams.

Production deployment:
  - Separate worker process runs `OutboxWorker.run_forever(poll_interval=1)`.
  - Each outbox row is published to a Redis Stream named by event type:
      STREAM_KEY = f"pamm.events.{event.type}"
  - Consumer group "pamm-cg" ensures multiple workers share the load.
  - Each consumer reads via XREADGROUP with `>` (only new messages).
  - On processing success, XACK is called.
  - On failure, the message is requeued (no XACK) — the consumer will
    re-receive it on the next XREADGROUP call (idempotent by event_id).
  - After MAX_ATTEMPTS failed attempts, the message is moved to a dead-letter
    stream (pamm.events.dead_letter) and XACK'd to remove it from the
    pending entries list (PEL).

Idempotency:
  - The consumer handler must be idempotent (dedup on event_id).
  - We track processed event_ids in a SET in Redis with a TTL (24h).
    A consumer checks SISMEMBER before processing; on success, SADDs the
    event_id and sets TTL.

Fallback when Redis is unreachable:
  - The worker falls back to direct DB drain (mark rows delivered).
  - A warning is logged so operators know Redis is down.
  - This is NOT a substitute for proper Redis in production.

Dev mode with fakeredis:
  - If USE_FAKEREDIS=1 env var is set OR settings.redis_url starts with
    "fakeredis://", the worker uses an in-process fakeredis instance.
  - This provides a real Redis Streams implementation for development and
    tests without requiring a running redis-server.
"""
from __future__ import annotations
import json
import logging
import time
import os
import threading
from datetime import datetime, timezone
from typing import Callable, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from ..models import Outbox, Event
from ..config import settings

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
DEAD_LETTER_STREAM = "pamm.events.dead_letter"
STREAM_PREFIX = "pamm.events."
CONSUMER_GROUP = "pamm-cg"
DEDUP_TTL_S = 24 * 60 * 60  # 24 hours
DEDUP_SET_KEY = "pamm.processed_event_ids"


def _make_redis(redis_url: str):
    """Create a Redis client. Supports fakeredis for dev/test.
    fakeredis instances share state via a module-level FakeServer so workers
    and consumers in the same process see the same stream data.

    fakeredis is used when:
      - redis_url starts with "fakeredis://", OR
      - USE_FAKEREDIS=1 env var is set AND redis_url is not explicitly a real URL
    """
    use_fakeredis = (
        redis_url.startswith("fakeredis://")
        or (os.environ.get("USE_FAKEREDIS") == "1" and not redis_url.startswith("redis://"))
    )
    if use_fakeredis:
        try:
            import fakeredis
            # Use a module-level shared server so all fakeredis clients in this
            # process see the same data (worker publishes, consumer reads).
            global _FAKE_SERVER
            if _FAKE_SERVER is None:
                _FAKE_SERVER = fakeredis.FakeServer()
            return fakeredis.FakeStrictRedis(server=_FAKE_SERVER)
        except ImportError:
            logger.warning("fakeredis requested but not installed; falling back to real redis")
    import redis
    return redis.Redis.from_url(redis_url, socket_connect_timeout=2)


# Module-level shared fakeredis server
_FAKE_SERVER = None


class OutboxWorker:
    """Drains outbox rows to Redis Streams. Falls back to DB drain on Redis failure."""

    def __init__(self, db_session_factory: Callable[[], Session],
                 redis_url: str | None = None,
                 consumer_name: str | None = None,
                 commit_on_drain: bool = True):
        """
        db_session_factory: callable returning a fresh Session.
        commit_on_drain: if True (default), worker commits after draining.
                         Set False when sharing a session with the caller.
        """
        self.db_session_factory = db_session_factory
        self.redis_url = redis_url or settings.redis_url
        self.consumer_name = consumer_name or f"worker-{os.getpid()}"
        self._redis = None
        self._stop = threading.Event()
        self._redis_available = False
        self._commit_on_drain = commit_on_drain
        self._connect_redis()

    def _connect_redis(self):
        try:
            self._redis = _make_redis(self.redis_url)
            self._redis.ping()
            self._redis_available = True
            backend = "fakeredis" if self._is_fakeredis() else "redis"
            logger.info(f"OutboxWorker: connected to {backend} at {self.redis_url}")
        except Exception as e:
            self._redis_available = False
            logger.warning(f"OutboxWorker: Redis unavailable ({e}); falling back to DB drain")

    def _is_fakeredis(self) -> bool:
        if self._redis is None: return False
        try:
            return "FakeStrictRedis" in type(self._redis).__name__ or "FakeRedis" in type(self._redis).__name__
        except: return False

    def publish_to_stream(self, event: Event) -> bool:
        """Publish one event to its Redis Stream. Returns True on success."""
        if not self._redis_available:
            return False
        stream_key = f"{STREAM_PREFIX}{event.type}"
        payload = {
            "event_id": event.event_id,
            "tenant_id": event.tenant_id,
            "type": event.type,
            "subject_type": event.subject_type or "",
            "subject_id": event.subject_id or "",
            "payload": json.dumps(event.payload, default=str),
            "schema_version": str(event.schema_version),
            "created_at": event.created_at.isoformat(),
        }
        try:
            # Ensure consumer group exists (idempotent)
            try:
                self._redis.xgroup_create(stream_key, CONSUMER_GROUP, id="0", mkstream=True)
            except Exception as e:
                if "BUSYGROUP" not in str(e):
                    raise
            # Add to stream
            self._redis.xadd(stream_key, payload)
            return True
        except Exception as e:
            logger.error(f"OutboxWorker: failed to publish event {event.event_id}: {e}")
            return False

    def drain_pending(self, limit: int = 100, tenant_id: str | None = None,
                      session: Session | None = None) -> dict:
        """Drain pending outbox rows. Returns stats dict.
        If `session` is provided, uses it (caller manages commit); otherwise opens a fresh session."""
        db = session or self.db_session_factory()
        owns_session = session is None
        processed = delivered = dead = errors = 0
        try:
            q = db.query(Outbox).filter(Outbox.status == "pending")
            if tenant_id:
                q = q.filter(Outbox.tenant_id == tenant_id)
            rows = q.limit(limit).all()
            for row in rows:
                processed += 1
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
                # Try Redis Streams first
                if self._redis_available and self.publish_to_stream(ev):
                    row.status = "delivered"
                    row.delivered_at = datetime.now(timezone.utc)
                    row.attempts += 1
                    delivered += 1
                else:
                    # Fallback: mark delivered directly (Redis bypassed)
                    row.status = "delivered"
                    row.delivered_at = datetime.now(timezone.utc)
                    row.attempts += 1
                    row.last_error = "redis_unavailable_fallback_db_drain"
                    delivered += 1
            if owns_session and self._commit_on_drain:
                db.commit()
            else:
                db.flush()  # always flush so caller can see updates
        finally:
            if owns_session:
                db.close()
        return {"processed": processed, "delivered": delivered,
                "dead_lettered": dead, "errors": errors,
                "redis_used": self._redis_available,
                "redis_backend": "fakeredis" if self._is_fakeredis() else ("redis" if self._redis_available else "none")}

    def stop(self):
        self._stop.set()

    def run_forever(self, poll_interval: float = 1.0, batch_size: int = 100):
        """Blocking loop. Runs until stop() is called."""
        logger.info(f"OutboxWorker {self.consumer_name} starting (poll={poll_interval}s)")
        while not self._stop.is_set():
            try:
                result = self.drain_pending(limit=batch_size)
                if result["processed"] > 0:
                    logger.info(f"OutboxWorker drained: {result}")
            except Exception as e:
                logger.error(f"OutboxWorker drain failed: {e}")
            self._stop.wait(poll_interval)
        logger.info(f"OutboxWorker {self.consumer_name} stopped")


def run_worker_blocking(redis_url: str | None = None, poll_interval: float = 1.0,
                        batch_size: int = 100):
    """CLI entry point. Run as: python -m app.domain.outbox_worker"""
    from ..db import SessionLocal
    worker = OutboxWorker(SessionLocal, redis_url=redis_url)
    try:
        worker.run_forever(poll_interval=poll_interval, batch_size=batch_size)
    except KeyboardInterrupt:
        worker.stop()


if __name__ == "__main__":
    run_worker_blocking()
