"""Demo history generator — SIMULATED data for prototype demonstrations.

Builds a 26-week track record for the demo tenant by driving the real API
(subscriptions, simulated P&L, rollovers) through FastAPI's TestClient, so all
NAV, fee, HWM, Merkle and audit figures come from the production code paths.
Only the timestamps are back-dated afterwards so the charts span half a year.

Nothing here is a real result: every P&L figure is a seeded random walk.
Run via `python -m app.seed` (enabled unless SEED_DEMO_HISTORY=0).
"""
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fastapi.testclient import TestClient
from .db import SessionLocal
from .models import (Tenant, User, Broker, TradingServer, MasterAccount, Strategy, RiskRule,
                     InvestorAccount, Subscription, Rollover)
from .auth import hash_password

WEEKS = 26
DEMO_PASSWORD = "Demo1234!"

# login, strategy name, description, kind, manager email, perf fee, weekly mu, weekly sigma
EXTRA_MASTERS = [
    ("ATL-PAMM-01", "Atlas Systematic FX", "Trend-following G10 FX basket, volatility-targeted (simulated)",
     "pamm", "atlas.quant@demo.com", "0.25", 0.0055, 0.018),
    ("NWD-PAMM-02", "Northwind Macro Balanced", "Discretionary macro across indices, gold and rates (simulated)",
     "pamm", "northwind.fx@demo.com", "0.15", 0.0035, 0.011),
    ("ATL-PAMM-03", "Atlas Low-Vol Carry", "Low-volatility carry with tight drawdown limits (simulated)",
     "pamm", "atlas.quant@demo.com", "0.20", 0.0022, 0.006),
]
# Walk parameters for the masters created by seed.py
BASE_WALKS = {"MASTER-001": (0.0045, 0.021), "MAM-MASTER-001": (0.0030, 0.014)}

INVESTORS = ["investor1@demo.com", "investor2@demo.com", "investor3@demo.com",
             "investor4@demo.com", "investor5@demo.com", "investor6@demo.com"]

# (investor index, master login, capital, join week)
ALLOCATIONS = [
    (0, "MASTER-001", "25000", 0), (0, "ATL-PAMM-01", "40000", 0), (0, "NWD-PAMM-02", "15000", 6),
    (1, "MASTER-001", "60000", 0), (1, "ATL-PAMM-03", "35000", 3),
    (2, "ATL-PAMM-01", "120000", 0), (2, "MAM-MASTER-001", "50000", 2),
    (3, "NWD-PAMM-02", "80000", 0), (3, "ATL-PAMM-03", "45000", 10),
    (4, "MASTER-001", "18000", 8), (4, "ATL-PAMM-01", "22000", 14),
    (5, "MAM-MASTER-001", "90000", 0), (5, "NWD-PAMM-02", "30000", 18),
]


def _ensure_users_and_masters(db, t: Tenant):
    broker = db.query(Broker).filter(Broker.tenant_id == t.id).first()
    srv = db.query(TradingServer).filter(TradingServer.broker_id == broker.id).first()
    admin = db.query(User).filter(User.email == "broker@demo.com").first()
    for email in INVESTORS + sorted({m[4] for m in EXTRA_MASTERS}):
        if not db.query(User).filter(User.email == email).first():
            role = "investor" if email.startswith("investor") else "money_manager"
            db.add(User(tenant_id=t.id, email=email, role=role, password_hash=hash_password(DEMO_PASSWORD)))
    db.flush()
    for login, name, desc, kind, mgr_email, fee, _, _ in EXTRA_MASTERS:
        if db.query(MasterAccount).filter(MasterAccount.login == login).first():
            continue
        mgr = db.query(User).filter(User.email == mgr_email).first()
        m = MasterAccount(tenant_id=t.id, broker_id=broker.id, server_id=srv.id, login=login,
                          currency="USD", base_nav=Decimal("100"), performance_fee_rate=Decimal(fee),
                          allocation_method="euro_days", manager_user_id=mgr.id,
                          nav_at_period_start=Decimal("100"))
        db.add(m); db.flush()
        db.add(Strategy(tenant_id=t.id, master_account_id=m.id, name=name, description=desc, kind=kind))
        db.add(RiskRule(tenant_id=t.id, master_account_id=m.id, name="max_exposure",
                        kind="max_total_exposure", params={"limit": "10000000"}, active=True,
                        created_by=admin.id))
        db.add(RiskRule(tenant_id=t.id, master_account_id=m.id, name="max_drawdown",
                        kind="max_drawdown", params={"limit_pct": "0.5", "peak": "0"}, active=True,
                        created_by=admin.id))
    for i, email in enumerate(INVESTORS):
        u = db.query(User).filter(User.email == email).first()
        if not db.query(InvestorAccount).filter(InvestorAccount.owner_user_id == u.id).first():
            db.add(InvestorAccount(tenant_id=t.id, broker_id=broker.id, login=f"INV-{10001 + i}",
                                   currency="USD", owner_user_id=u.id))
    db.commit()


def _login(c: TestClient, email: str) -> dict:
    r = c.post("/api/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def populate():
    from .main import app  # imported lazily to avoid a circular import at module load
    db = SessionLocal()
    try:
        t = db.query(Tenant).filter(Tenant.slug == "demo-broker").first()
        if not t or db.query(Rollover).filter(Rollover.tenant_id == t.id).count() > 0:
            return False
        _ensure_users_and_masters(db, t)
        masters = {m.login: m.id for m in db.query(MasterAccount).filter(MasterAccount.tenant_id == t.id)}
        strat_by_master = {s.master_account_id: s.id for s in db.query(Strategy).filter(Strategy.tenant_id == t.id)}
        accounts = {}
        for email in INVESTORS:
            u = db.query(User).filter(User.email == email).first()
            accounts[email] = db.query(InvestorAccount).filter(InvestorAccount.owner_user_id == u.id).first().id
    finally:
        db.close()

    walks = dict(BASE_WALKS)
    walks.update({m[0]: (m[6], m[7]) for m in EXTRA_MASTERS})
    rng = random.Random(20261028)
    start = datetime.now(timezone.utc) - timedelta(weeks=WEEKS)
    rollover_dates: dict[str, datetime] = {}
    sub_dates: dict[str, datetime] = {}

    with TestClient(app) as c:
        admin = _login(c, "broker@demo.com")
        inv_headers = {e: _login(c, e) for e in INVESTORS}
        for week in range(WEEKS):
            for inv_idx, login, capital, join in ALLOCATIONS:
                if join != week:
                    continue
                email = INVESTORS[inv_idx]
                r = c.post("/api/subscriptions", headers=inv_headers[email], json={
                    "strategy_id": strat_by_master[masters[login]],
                    "investor_account_id": accounts[email], "capital": capital})
                r.raise_for_status()
                sub_dates[r.json()["subscription_id"]] = start + timedelta(weeks=week)
            for login, (mu, sigma) in walks.items():
                mid = masters[login]
                equity = Decimal(next(m for m in c.get("/api/masters", headers=admin).json()
                                      if m["id"] == mid)["equity"])
                if equity <= 0:
                    continue
                ret = rng.gauss(mu, sigma)
                pnl = (equity * Decimal(str(ret))).quantize(Decimal("0.01"))
                c.post(f"/api/simulate-pnl?master_id={mid}&pnl={pnl}", headers=admin).raise_for_status()
                r = c.post("/api/rollovers", headers=admin, json={
                    "master_account_id": mid, "method": "euro_days", "period_days": 7,
                    "idempotency_key": f"demo-{login}-w{week:02d}"})
                r.raise_for_status()
                rollover_dates[r.json()["id"]] = start + timedelta(weeks=week + 1)

    # Back-date timestamps so the simulated history spans the last 26 weeks.
    db = SessionLocal()
    try:
        for rid, end in rollover_dates.items():
            ro = db.get(Rollover, rid)
            ro.period_start, ro.period_end, ro.created_at = end - timedelta(days=7), end, end
        for sid, at in sub_dates.items():
            db.get(Subscription, sid).subscribed_at = at
        db.commit()
    finally:
        db.close()
    print(f"Demo history: {len(rollover_dates)} simulated weekly rollovers, {len(sub_dates)} subscriptions.")
    return True
