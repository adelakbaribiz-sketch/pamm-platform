#!/usr/bin/env python3
"""M5 live acceptance: Redis Streams publish/consume + adapters + backup."""
import os, json, urllib.request, urllib.error, subprocess, sys
os.environ["USE_FAKEREDIS"] = "1"

BASE = "http://127.0.0.1:8000"

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
    print("=== STEP 1: Sign in ===")
    st, t = req("POST", "/api/auth/login", body={"email": "broker@demo.com", "password": "Demo1234!"})
    assert st == 200, t
    token = t["access_token"]
    print(f"  role={t['role']}")

    print("=== STEP 2: List adapters (4 registered) ===")
    st, adapters = req("GET", "/api/adapters", token=token)
    assert st == 200, adapters
    for a in adapters:
        blocked_tag = " (BLOCKED)" if a["blocked"] else ""
        print(f"  {a['type']:10} live={a['is_live']} blocked={a['blocked']}{blocked_tag}")

    print("=== STEP 3: Inspect simulated adapter capabilities ===")
    st, sim = req("GET", "/api/adapters/simulated", token=token)
    assert st == 200, sim
    caps = sim["capabilities"]
    print(f"  supports_market_orders={caps['supports_market_orders']}")
    print(f"  supports_modify={caps['supports_modify']}")
    print(f"  supports_partial_fills={caps['supports_partial_fills']}")
    print(f"  supports_reconciliation={caps['supports_reconciliation']}")
    print(f"  lot_step={sim['limits']['lot_step']}")
    print(f"  supported_symbols={sim['limits']['supported_symbols']}")

    print("=== STEP 4: Test-connect each adapter ===")
    for atype in ["simulated", "mt5", "ctrader", "crypto"]:
        st, r = req("POST", f"/api/adapters/{atype}/test-connect", token=token, body={})
        if atype == "simulated":
            print(f"  {atype}: connected={r['connected']} live={r['is_live']} warning={r.get('warning','')[:60]}")
        else:
            print(f"  {atype}: connected={r['connected']} blocked={r.get('blocked')} code={r.get('code')}")

    print("=== STEP 5: Generate events + drain via Outbox worker (Redis Streams via fakeredis) ===")
    # Create a broker (generates an event)
    st, b = req("POST", "/api/brokers", token=token, body={"name": f"M5Broker-{os.getpid()}"})
    assert st == 200, b
    print(f"  broker created: {b['id'][:8]}")

    # Check outbox stats — should have pending events
    st, stats_before = req("GET", "/api/outbox/stats", token=token)
    print(f"  outbox before drain: pending={stats_before['pending']} delivered={stats_before['delivered']}")

    # Drain
    st, drained = req("POST", "/api/outbox/drain?limit=200", token=token)
    print(f"  drained: processed={drained['processed']} delivered={drained['delivered']} redis_used={drained['redis_used']} backend={drained.get('redis_backend')}")

    st, stats_after = req("GET", "/api/outbox/stats", token=token)
    print(f"  outbox after drain: pending={stats_after['pending']} delivered={stats_after['delivered']}")

    print("=== STEP 6: Verify audit chain intact ===")
    st, audit = req("GET", "/api/audit/verify", token=token)
    print(f"  audit_verified={audit['verified']}")

    print("=== STEP 7: Backup → restore cycle ===")
    # Backup pamm to a temp file
    import tempfile
    backup_dir = tempfile.mkdtemp()
    env = {**os.environ, "DATABASE_URL": "postgresql+psycopg://pamm:pamm_dev_pw@/pamm?host=/home/z/my-project/pgdata"}
    r = subprocess.run([sys.executable, "/home/z/my-project/pamm-platform/deploy/backup/backup.py", backup_dir],
                       env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"backup failed: {r.stderr}"
    backups = list(__import__("pathlib").Path(backup_dir).glob("pamm-*.sql.gz"))
    print(f"  backup created: {backups[0].name} ({backups[0].stat().st_size} bytes)")

    # Count source tenants
    import psycopg
    with psycopg.connect(host="/home/z/my-project/pgdata", user="pamm", password="pamm_dev_pw", dbname="pamm") as c:
        with c.cursor() as cur:
            cur.execute("SELECT count(*) FROM tenants")
            source_tenants = cur.fetchone()[0]

    # Truncate pamm_restore_test (target)
    with psycopg.connect(host="/home/z/my-project/pgdata", user="pamm", password="pamm_dev_pw", dbname="pamm_restore_test") as c:
        c.autocommit = True
        with c.cursor() as cur:
            cur.execute("SET session_replication_role = replica;")
            cur.execute("TRUNCATE tenants CASCADE;")
            cur.execute("SET session_replication_role = DEFAULT;")
    print(f"  source tenants: {source_tenants}")

    # Restore
    env_restore = {**os.environ, "DATABASE_URL": "postgresql+psycopg://pamm:pamm_dev_pw@/pamm_restore_test?host=/home/z/my-project/pgdata"}
    r = subprocess.run([sys.executable, "/home/z/my-project/pamm-platform/deploy/backup/restore.py",
                       str(backups[0]), "--confirm"],
                      env=env_restore, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"restore failed: {r.stderr}"
    print(f"  restore: {r.stdout.strip().split(chr(10))[-1]}")

    # Verify
    with psycopg.connect(host="/home/z/my-project/pgdata", user="pamm", password="pamm_dev_pw", dbname="pamm_restore_test") as c:
        with c.cursor() as cur:
            cur.execute("SELECT count(*) FROM tenants")
            restored_tenants = cur.fetchone()[0]
    print(f"  restored tenants: {restored_tenants}")
    assert restored_tenants == source_tenants, f"tenant count mismatch: source={source_tenants} restored={restored_tenants}"
    print(f"  ✓ backup/restore cycle verified")

    print("\n=== ALL M5 ACCEPTANCE STEPS COMPLETED ===")

if __name__ == "__main__":
    main()
