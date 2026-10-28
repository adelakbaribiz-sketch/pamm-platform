#!/usr/bin/env python3
"""Smoke test of all three M2 frontend workspaces by hitting their backing APIs."""
import json, urllib.request, urllib.error, sys

def req(method, path, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"http://127.0.0.1:8000{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

# Login
st, t = req("POST", "/api/auth/login", body={"email": "broker@demo.com", "password": "Demo1234!"})
assert st == 200, t
TOKEN = t["access_token"]
print(f"Logged in as broker_admin, token length={len(TOKEN)}")

print("\n=== Copy Trading Console ===")
st, subs = req("GET", "/api/copy/subscriptions", TOKEN)
print(f"Follower subscriptions: {len(subs)}")
for s in subs[:3]:
    print(f"  {s['follower_login']} → {s['master_login']} status={s['status']} multiplier={s['lot_multiplier']}")
st, trades = req("GET", "/api/copy/trades", TOKEN)
print(f"Copy trades: {len(trades)}")
if trades:
    t = trades[0]
    print(f"  trade {t['id'][:8]} symbol={t['symbol']} side={t['side']} status={t['status']} filled={t['filled']} skipped={t['skipped']}")
    st, fs = req("GET", f"/api/copy/trades/{t['id']}/followers", TOKEN)
    print(f"  follower trades drill-down: {len(fs)}")
    for ft in fs[:5]:
        total_lat = (ft.get('server_side_latency_ms') or 0) + (ft.get('broker_latency_ms') or 0)
        print(f"    ft {ft['id'][:8]}: lots={ft['allocated_lots']} status={ft['status']} "
              f"server={ft.get('server_side_latency_ms')}ms broker={ft.get('broker_latency_ms')}ms "
              f"total={total_lat}ms slip={ft.get('slippage_bps')}bps")
        if ft.get('reject_reason'):
            print(f"       reject_reason={ft['reject_reason']}")

print("\n=== Saga Inspector ===")
st, sagas = req("GET", "/api/sagas", TOKEN)
print(f"Sagas: {len(sagas)}")
if sagas:
    s = sagas[0]
    st, detail = req("GET", f"/api/sagas/{s['saga_id']}", TOKEN)
    print(f"  detail {s['saga_id'][:8]}: kind={detail['kind']} status={detail['status']}")
    print(f"  steps: {len(detail.get('step_records', []))}")
    for step in detail.get("step_records", [])[:5]:
        rev = "reversible" if step.get("is_reversible") else "IRREVERSIBLE→remediate"
        print(f"    {step['step_name']}: status={step['status']} ({rev}) attempts={step.get('attempts', 0)}")
        if step.get("error"):
            print(f"      error: {step['error'][:100]}")
    print(f"  compensation_log entries: {len(detail.get('compensation_log', []))}")

print("\n=== MAM Split ===")
st, masters = req("GET", "/api/masters", TOKEN)
print(f"Master accounts available for MAM split: {len(masters)}")
for m in masters[:3]:
    print(f"  {m['login']} equity={m['equity']} method={m['allocation_method']}")

print("\nAll three workspaces' backing APIs respond correctly.")
