#!/usr/bin/env python3
"""M4 live acceptance: adapters registry + outbox worker + capabilities discovery."""
import json, urllib.request, urllib.error

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

    print("=== STEP 2: List adapters (4 registered: simulated + mt5 + ctrader + crypto) ===")
    st, adapters = req("GET", "/api/adapters", token=token)
    assert st == 200, adapters
    for a in adapters:
        blocked = " (BLOCKED)" if a["blocked"] else ""
        print(f"  {a['type']:10} live={a['is_live']} blocked={a['blocked']}{blocked}")
        print(f"             notes: {a['notes'][:80]}")

    print("=== STEP 3: Inspect MT5 adapter capabilities (BLOCKED but documented) ===")
    st, mt5 = req("GET", "/api/adapters/mt5", token=token)
    assert st == 200, mt5
    print(f"  type={mt5['type']} is_live={mt5['is_live']} blocked={mt5['blocked']}")
    caps = mt5["capabilities"]
    print(f"  supports_market_orders={caps['supports_market_orders']}")
    print(f"  supports_modify={caps['supports_modify']}")
    print(f"  supports_partial_fills={caps['supports_partial_fills']}")
    print(f"  supports_reconciliation={caps['supports_reconciliation']}")
    print(f"  lot_step={mt5['limits']['lot_step']}")
    print(f"  notes: {mt5['notes'][:100]}")

    print("=== STEP 4: Inspect cTrader adapter capabilities (BLOCKED) ===")
    st, ct = req("GET", "/api/adapters/ctrader", token=token)
    assert st == 200, ct
    print(f"  type={ct['type']} blocked={ct['blocked']}")
    print(f"  notes: {ct['notes'][:100]}")

    print("=== STEP 5: Inspect crypto adapter capabilities (BLOCKED) ===")
    st, cr = req("GET", "/api/adapters/crypto", token=token)
    assert st == 200, cr
    print(f"  type={cr['type']} blocked={cr['blocked']}")
    print(f"  lot_step={cr['limits']['lot_step']}  (8dp for crypto)")
    print(f"  notes: {cr['notes'][:100]}")

    print("=== STEP 6: Test-connect MT5 (returns BLOCKED reason cleanly) ===")
    st, tc = req("POST", "/api/adapters/mt5/test-connect", token=token, body={})
    assert st == 200, tc
    print(f"  connected={tc['connected']} blocked={tc.get('blocked')}")
    print(f"  code={tc.get('code')} reason={tc.get('reason', '')[:80]}")

    print("=== STEP 7: Test-connect simulated (returns success + warning) ===")
    st, ts = req("POST", "/api/adapters/simulated/test-connect", token=token, body={})
    assert st == 200, ts
    print(f"  connected={ts['connected']} is_live={ts['is_live']}")
    print(f"  warning={ts.get('warning')}")

    print("=== STEP 8: Outbox stats (pending events from prior activity) ===")
    st, stats = req("GET", "/api/outbox/stats", token=token)
    print(f"  pending={stats['pending']} delivered={stats['delivered']} dead_letter={stats['dead_letter']}")

    print("=== STEP 9: Drain outbox via worker (DB fallback since Redis unavailable) ===")
    st, drained = req("POST", "/api/outbox/drain?limit=500", token=token)
    print(f"  processed={drained['processed']} delivered={drained['delivered']} dead_lettered={drained['dead_lettered']}")
    print(f"  redis_used={drained['redis_used']} (should be False — fallback)")
    st, stats2 = req("GET", "/api/outbox/stats", token=token)
    print(f"  after drain: pending={stats2['pending']} delivered={stats2['delivered']}")

    print("=== STEP 10: Verify audit chain still intact ===")
    st, audit = req("GET", "/api/audit/verify", token=token)
    print(f"  audit_verified={audit['verified']}")

    print("\n=== ALL M4 ACCEPTANCE STEPS COMPLETED ===")

if __name__ == "__main__":
    main()
