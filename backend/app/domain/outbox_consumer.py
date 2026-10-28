"""
Outbox consumer — reads events from Redis Streams and processes them.

Production deployment:
  - Separate consumer process runs `OutboxConsumer.run_forever()`.
  - Joins consumer group "pamm-cg" with a unique consumer name.
  - Reads via XREADGROUP with `>` (only new messages).
  - On processing success, XACK is called.
  - On failure (handler raises), the message is NOT ack'd — it stays in the
    Pending Entries List (PEL). The next XREADGROUP call with `>` will
    deliver new messages, NOT the pending one. To re-process pending
    messages, use `XREADGROUP ... 0` (PEL inspection).
  - After MAX_PROCESS_ATTEMPTS failed attempts, the message is moved to
    the dead-letter stream (pamm.events.dead_letter) and XACK'd.

Idempotency:
  - The consumer tracks processed event_ids in a Redis SET with TTL.
  - Before processing, SISMEMBER checks if we've seen this event_id.
  - If yes, XACK without processing (idempotent no-op).
  - If no, process; on success, SADD the event_id and EXPIRE the set.

Handler registry:
  - Each event type maps to a handler function.
  - Unknown event types log a warning but XACK (avoid blocking the stream).
"""
from __future__ import annotations
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Callable
from .outbox_worker import _make_redis, STREAM_PREFIX, CONSUMER_GROUP, DEAD_LETTER_STREAM, DEDUP_SET_KEY, DEDUP_TTL_S, MAX_ATTEMPTS

logger = logging.getLogger(__name__)

MAX_PROCESS_ATTEMPTS = 5
CONSUMER_BLOCK_MS = 1000  # block for 1s when reading


class OutboxConsumer:
    """Reads events from Redis Streams and processes them via registered handlers."""

    def __init__(self, redis_url: str | None = None,
                 consumer_name: str | None = None):
        from ..config import settings
        self.redis_url = redis_url or settings.redis_url
        self.consumer_name = consumer_name or f"consumer-{os.getpid()}"
        self._redis = None
        self._stop = threading.Event()
        self._handlers: dict[str, Callable[[dict], None]] = {}
        self._connect()

    def _connect(self):
        self._redis = _make_redis(self.redis_url)
        try:
            self._redis.ping()
        except Exception as e:
            raise RuntimeError(f"Cannot connect to Redis: {e}")

    def register_handler(self, event_type: str, handler: Callable[[dict], None]):
        """Register a handler for an event type. Handler is idempotent."""
        self._handlers[event_type] = handler
        # Ensure consumer group exists for this stream
        stream_key = f"{STREAM_PREFIX}{event_type}"
        try:
            self._redis.xgroup_create(stream_key, CONSUMER_GROUP, id="0", mkstream=True)
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                raise

    def _is_processed(self, event_id: str) -> bool:
        return bool(self._redis.sismember(DEDUP_SET_KEY, event_id))

    def _mark_processed(self, event_id: str):
        self._redis.sadd(DEDUP_SET_KEY, event_id)
        self._redis.expire(DEDUP_SET_KEY, DEDUP_TTL_S)

    def process_one(self, event_type: str, timeout_ms: int = CONSUMER_BLOCK_MS) -> dict:
        """Read one message from the stream and process it. Returns stats dict."""
        stream_key = f"{STREAM_PREFIX}{event_type}"
        # Read one message from the consumer group
        messages = self._redis.xreadgroup(
            CONSUMER_GROUP, self.consumer_name,
            {stream_key: ">"}, count=1, block=timeout_ms
        )
        if not messages:
            return {"processed": 0, "acked": 0, "errors": 0, "dead_lettered": 0}

        stream_name, msg_list = messages[0]
        msg_id, fields = msg_list[0]
        event_id = fields.get(b"event_id", b"").decode() if isinstance(fields.get(b"event_id"), bytes) else fields.get("event_id", "")

        # Idempotency check
        if self._is_processed(event_id):
            self._redis.xack(stream_key, CONSUMER_GROUP, msg_id)
            return {"processed": 0, "acked": 1, "errors": 0, "dead_lettered": 0,
                    "skipped": "already_processed"}

        # Dispatch to handler
        handler = self._handlers.get(event_type)
        if handler is None:
            logger.warning(f"No handler for event type '{event_type}' (msg {msg_id}); acking")
            self._redis.xack(stream_key, CONSUMER_GROUP, msg_id)
            self._mark_processed(event_id)
            return {"processed": 0, "acked": 1, "errors": 0, "dead_lettered": 0,
                    "skipped": "no_handler"}

        try:
            handler(fields)
            self._redis.xack(stream_key, CONSUMER_GROUP, msg_id)
            self._mark_processed(event_id)
            return {"processed": 1, "acked": 1, "errors": 0, "dead_lettered": 0}
        except Exception as e:
            logger.error(f"Consumer handler failed for {event_type} (msg {msg_id}): {e}")
            # Check pending attempts count
            pel_info = self._redis.xpending_range(stream_key, CONSUMER_GROUP, min="-", max="+", count=10)
            attempts = 0
            for entry in pel_info:
                eid = entry.get(b"message_id", entry.get("message_id"))
                if str(eid) == str(msg_id):
                    attempts = entry.get(b"times_delivered", entry.get("times_delivered", 1))
                    break
            if attempts >= MAX_PROCESS_ATTEMPTS:
                # Move to dead-letter and ack
                self._redis.xadd(DEAD_LETTER_STREAM, {**fields,
                    "dead_letter_reason": str(e), "dead_lettered_at": datetime.now(timezone.utc).isoformat()})
                self._redis.xack(stream_key, CONSUMER_GROUP, msg_id)
                logger.error(f"Message {msg_id} moved to dead-letter after {attempts} attempts")
                return {"processed": 0, "acked": 1, "errors": 1, "dead_lettered": 1}
            return {"processed": 0, "acked": 0, "errors": 1, "dead_lettered": 0}

    def process_batch(self, event_type: str, batch_size: int = 100) -> dict:
        """Process up to batch_size messages. Returns aggregate stats."""
        stats = {"processed": 0, "acked": 0, "errors": 0, "dead_lettered": 0}
        for _ in range(batch_size):
            r = self.process_one(event_type, timeout_ms=100)
            if r["processed"] == 0 and r["acked"] == 0 and r["errors"] == 0:
                break  # no more messages
            stats["processed"] += r["processed"]
            stats["acked"] += r["acked"]
            stats["errors"] += r["errors"]
            stats["dead_lettered"] += r["dead_lettered"]
            if r["processed"] == 0 and r["acked"] == 0:
                break
        return stats

    def stop(self):
        self._stop.set()

    def run_forever(self, event_types: list[str], poll_interval: float = 0.5):
        """Blocking loop. Listens to multiple event types and dispatches."""
        logger.info(f"OutboxConsumer {self.consumer_name} starting for types: {event_types}")
        while not self._stop.is_set():
            for event_type in event_types:
                try:
                    r = self.process_one(event_type, timeout_ms=int(poll_interval * 1000))
                    if r["processed"] > 0 or r["errors"] > 0:
                        logger.info(f"Consumer {event_type}: {r}")
                except Exception as e:
                    logger.error(f"Consumer error on {event_type}: {e}")
        logger.info(f"OutboxConsumer {self.consumer_name} stopped")


def run_consumer_blocking(event_types: list[str], redis_url: str | None = None):
    """CLI entry point. Run as: python -m app.domain.outbox_consumer"""
    consumer = OutboxConsumer(redis_url=redis_url)
    # Register default no-op handlers (real handlers wired up by the application)
    for t in event_types:
        consumer.register_handler(t, lambda fields: logger.info(f"consumed: {fields.get(b'event_id', fields.get('event_id'))}"))
    try:
        consumer.run_forever(event_types)
    except KeyboardInterrupt:
        consumer.stop()


if __name__ == "__main__":
    import sys
    types = sys.argv[1:] or ["test.event"]
    run_consumer_blocking(types)
