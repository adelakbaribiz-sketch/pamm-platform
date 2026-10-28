#!/usr/bin/env python3
"""M3 live acceptance: P-1 allocation solver + P-2 latency prediction + outbox worker."""
import json, uuid, urllib.request, urllib.error

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

    print("=== STEP 2: P-1 — Solve a feasible allocation problem ===")
    st, masters = req("GET", "/api/masters", token=token)
    master_id = masters[0]["id"]
    st, sol = req("POST", "/api/allocation/solve", token=token, body={
        "master_account_id": master_id,
        "objective": "maximize_return",
        "free_margin": "10000",
        "investors": [
            {"investor_id": "iv-A", "expected_return": "0.15", "volatility": "0.08",
             "min_allocation": "0", "max_allocation": "10000", "peak_capital": "10000",
             "drawdown_limit_pct": "1.0"},
            {"investor_id": "iv-B", "expected_return": "0.10", "volatility": "0.05",
             "min_allocation": "0", "max_allocation": "10000", "peak_capital": "10000",
             "drawdown_limit_pct": "1.0"},
        ],
    })
    assert st == 200, sol
    print(f"  status={sol['status']} obj_value={sol['objective_value']}")
    for k, v in sol["allocations"].items():
        print(f"    {k}: ${v}")
    assert sol["status"] == "optimal"
    assert sol["frozen"] is False
    assert sol["alert_emitted"] is False

    print("=== STEP 3: P-1 — Infeasible problem (floors exceed budget) ===")
    st, sol2 = req("POST", "/api/allocation/solve", token=token, body={
        "master_account_id": master_id,
        "objective": "maximize_return",
        "free_margin": "1000",
        "investors": [
            {"investor_id": "iv-A", "min_allocation": "800", "max_allocation": "10000",
             "peak_capital": "10000", "drawdown_limit_pct": "1.0"},
            {"investor_id": "iv-B", "min_allocation": "800", "max_allocation": "10000",
             "peak_capital": "10000", "drawdown_limit_pct": "1.0"},
        ],
    })
    assert st == 200, sol2
    print(f"  status={sol2['status']} reason={sol2['infeasibility_reason']}")
    assert sol2["status"] == "infeasible"
    assert sol2["frozen"] is True
    assert sol2["alert_emitted"] is True
    assert sol2["allocations"] == {}

    print("=== STEP 4: P-1 — List alerts and acknowledge ===")
    st, alerts = req("GET", "/api/allocation/alerts", token=token)
    print(f"  alerts: {len(alerts)}")
    if alerts:
        a = alerts[0]
        print(f"  kind={a['kind']} acknowledged={a['acknowledged']}")
        # Acknowledge it
        st, ack = req("POST", f"/api/allocation/alerts/{a['id']}/acknowledge", token=token)
        assert st == 200, ack
        print(f"  acknowledged={ack['acknowledged']}")

    print("=== STEP 5: P-2 — Predict latency for a destination ===")
    st, pred = req("POST", "/api/latency/predict", token=token, body={
        "destination": "mt5-simulated", "symbol": "EURUSD",
        "order_size": "1.0", "recent_volatility": 0.1,
        "permitted_threshold_ms": 100.0,
    })
    assert st == 200, pred
    print(f"  prediction_id={pred['prediction_id'][:8]}")
    print(f"  predicted_latency_ms={pred['predicted_latency_ms']}")
    print(f"  interval=[{pred['predicted_lower_ms']}, {pred['predicted_upper_ms']}]")
    print(f"  throttle_applied={pred['throttle_applied']}")

    print("=== STEP 6: P-2 — Observe actual (close the loop) ===")
    st, obs = req("POST", "/api/latency/observe", token=token, body={
        "destination": "mt5-simulated", "symbol": "EURUSD",
        "order_size": "1.0", "latency_ms": 95, "slippage_bps": "2.0",
        "prediction_id": pred["prediction_id"],
    })
    assert st == 200, obs
    print(f"  observation_id={obs['observation_id'][:8]}")
    print(f"  residual_latency={obs['residual_latency']}")
    print(f"  residual_slippage={obs['residual_slippage']}")

    print("=== STEP 7: P-2 — Train with multiple observations ===")
    for i in range(10):
        p = req("POST", "/api/latency/predict", token=token, body={
            "destination": "mt5-simulated", "symbol": "EURUSD",
            "order_size": str(1.0 + i * 0.5), "recent_volatility": 0.1,
        })[1]
        req("POST", "/api/latency/observe", token=token, body={
            "destination": "mt5-simulated", "symbol": "EURUSD",
            "order_size": str(1.0 + i * 0.5), "latency_ms": 60 + i * 5,
            "slippage_bps": "1.5", "prediction_id": p["prediction_id"],
        })

    print("=== STEP 8: P-2 — Fetch execution profile ===")
    st, prof = req("GET", "/api/latency/profiles/mt5-simulated?symbol=EURUSD", token=token)
    assert st == 200, prof
    print(f"  total_observations={prof['total_observations']}")
    print(f"  mean={prof['latency_mean_ms']}ms p95={prof['latency_p95_ms']}ms p99={prof['latency_p99_ms']}ms")
    print(f"  slippage_mean={prof['slippage_mean_bps']}bps")

    print("=== STEP 9: P-2 — Calibration stats ===")
    st, cal = req("GET", "/api/latency/calibration?destination=mt5-simulated&symbol=EURUSD", token=token)
    assert st == 200, cal
    print(f"  n={cal['n']} mae_ms={cal['mae_ms']} bias_ms={cal['bias_ms']}")
    print(f"  within_95pct_interval_pct={cal['within_95pct_interval_pct']}%")

    print("=== STEP 10: Outbox — check pending rows ===")
    st, stats = req("GET", "/api/outbox/stats", token=token)
    print(f"  pending={stats['pending']} delivered={stats['delivered']} dead_letter={stats['dead_letter']}")

    print("=== STEP 11: Outbox — drain pending ===")
    st, drained = req("POST", "/api/outbox/drain?limit=200", token=token)
    print(f"  processed={drained['processed']} delivered={drained['delivered']} dead_letter={drained['dead_lettered']}")
    st, stats2 = req("GET", "/api/outbox/stats", token=token)
    print(f"  after: pending={stats2['pending']} delivered={stats2['delivered']} dead_letter={stats2['dead_letter']}")

    print("=== STEP 12: Verify audit chain still intact ===")
    st, audit = req("GET", "/api/audit/verify", token=token)
    print(f"  audit_verified={audit['verified']}")

    print("\n=== ALL M3 ACCEPTANCE STEPS COMPLETED ===")

if __name__ == "__main__":
    main()
