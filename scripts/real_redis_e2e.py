#!/usr/bin/env python3
"""Live end-to-end test against REAL redis-server (not fakeredis).

Verifies: backend publishes events to real Redis Streams via OutboxWorker,
then a consumer reads them via XREADGROUP and processes them.

Prerequisites:
  - redis-server running on localhost:6379
  - postgres running
  - backend migrations applied + seeded
"""
import os, sys, json, time, threading, urllib.request, urllib.error
import uuid as uuid_mod

BASE = "http://127.0.0.1:8000"
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

def req(method, path, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{BASE}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

def main():
    print("=== Live End-to-End Test with REAL Redis ===")
    print(f"Redis URL: {REDIS_URL}")

    # Verify redis is reachable
    import redis
    r = redis.Redis.from_url(REDIS_URL)
    r.ping()
    print(f"  Redis PING: PONG")
    print(f"  Redis version: {r.info()['redis_version']}")

    # Flush all old data
    r.flushall()
    print(f"  Flushed all keys")

    # Sign in
    st, t = req("POST", "/api/auth/login", body={"email": "broker@demo.com", "password": "Demo1234!"})
    assert st == 200, t
    token = t["access_token"]
    print(f"  Logged in as broker_admin")

    # Generate events by creating brokers (each generates a broker.created event)
    print("\n=== STEP 1: Generate 5 events via API ===")
    for i in range(5):
        st, b = req("POST", "/api/brokers", token=token,
                    body={"name": f"RedisE2EBroker-{i}-{uuid_mod.uuid4().hex[:6]}"})
        assert st == 200, b
    print(f"  Created 5 brokers → 5 broker.created events")

    # Check outbox stats
    st, stats = req("GET", "/api/outbox/stats", token=token)
    print(f"  Outbox before drain: pending={stats['pending']} delivered={stats['delivered']}")

    # Drain via the API (which uses OutboxWorker with real Redis)
    print("\n=== STEP 2: Drain outbox to REAL Redis Streams ===")
    st, drained = req("POST", "/api/outbox/drain?limit=100", token=token)
    print(f"  Drain result: processed={drained['processed']} delivered={drained['delivered']}")
    print(f"  redis_used={drained.get('redis_used')} backend={drained.get('redis_backend')}")

    # Verify via redis-cli that the stream has messages
    stream_key = "pamm.events.broker.created"
    stream_len = r.xlen(stream_key)
    print(f"\n=== STEP 3: Verify Redis Stream contains messages ===")
    print(f"  Stream '{stream_key}' length: {stream_len}")
    assert stream_len >= 5, f"expected ≥5 messages, got {stream_len}"

    # Verify consumer group was created
    groups = r.xinfo_groups(stream_key)
    print(f"  Consumer groups: {len(groups)}")
    for g in groups:
        print(f"    group={g['name']} consumers={g['consumers']} pending={g['pending']}")

    # Start a consumer to read the messages
    print(f"\n=== STEP 4: Consumer reads messages via XREADGROUP ===")
    from app.domain.outbox_consumer import OutboxConsumer

    received = []
    def handler(fields):
        # Decode bytes keys/values
        decoded = {}
        for k, v in fields.items():
            if isinstance(k, bytes): k = k.decode()
            if isinstance(v, bytes): v = v.decode()
            decoded[k] = v
        received.append(decoded)

    consumer = OutboxConsumer(redis_url=REDIS_URL, consumer_name="e2e-consumer")
    consumer.register_handler("broker.created", handler)

    # Process up to 5 messages
    for i in range(5):
        result = consumer.process_one("broker.created", timeout_ms=2000)
        print(f"  process_one #{i+1}: {result}")
        if result["processed"] == 0 and result["acked"] == 0:
            break

    print(f"\n  Total messages consumed: {len(received)}")
    for msg in received[:3]:
        print(f"    event_id={msg.get('event_id','')[:8]} type={msg.get('type')} tenant_id={msg.get('tenant_id','')[:8]}")

    # Verify PEL is empty (all acked)
    pel = r.xpending_range(stream_key, "pamm-cg", min="-", max="+", count=10)
    print(f"\n=== STEP 5: Verify PEL (pending entries) is empty ===")
    print(f"  PEL length: {len(pel)} (should be 0 after all XACKs)")
    assert len(pel) == 0

    # Verify dedup set
    dedup_size = r.scard("pamm.processed_event_ids")
    print(f"\n=== STEP 6: Verify dedup set ===")
    print(f"  Dedup set size: {dedup_size} (should be ≥5)")
    assert dedup_size >= 5

    # Idempotency test: re-add one event and try to consume again
    print(f"\n=== STEP 7: Idempotency — re-deliver same event_id ===")
    if received:
        original_fields = received[0]
        # Re-add the same event_id to the stream
        r.xadd(stream_key, {k: v for k, v in original_fields.items()})
        print(f"  Re-added event_id={original_fields.get('event_id','')[:8]}")

        call_before = len(received)
        result = consumer.process_one("broker.created", timeout_ms=2000)
        print(f"  process_one result: {result}")
        print(f"  received count: before={call_before} after={len(received)}")
        assert len(received) == call_before, "handler was called again (idempotency violated)"

    # Outbox stats after drain
    st, stats2 = req("GET", "/api/outbox/stats", token=token)
    print(f"\n=== STEP 8: Final outbox stats ===")
    print(f"  pending={stats2['pending']} delivered={stats2['delivered']}")
    assert stats2["pending"] == 0

    print(f"\n=== ALL LIVE E2E TESTS WITH REAL REDIS PASSED ===")

if __name__ == "__main__":
    main()
