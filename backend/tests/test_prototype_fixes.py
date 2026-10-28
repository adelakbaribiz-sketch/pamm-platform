"""Regression tests for the 2026-10 prototype audit fixes (authz, tenant scoping, rollover P&L)."""
import uuid
from decimal import Decimal
from app.auth import create_access_token
from app.config import settings
from app.models import (Tenant, User, Broker, TradingServer, MasterAccount, Strategy,
                        InvestorAccount, Rollover)


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(u.id, u.role, u.tenant_id)}"}


def _tenant(db, slug=None):
    t = Tenant(name="Fix Tenant", slug=slug or f"fix-{uuid.uuid4().hex[:8]}")
    db.add(t); db.flush()
    mk = lambda role: User(tenant_id=t.id, email=f"{role}-{uuid.uuid4().hex[:8]}@test.com",
                           role=role, password_hash="$2b$12$dummy")
    admin, inv_a, inv_b = mk("broker_admin"), mk("investor"), mk("investor")
    db.add_all([admin, inv_a, inv_b]); db.flush()
    b = Broker(tenant_id=t.id, name="Fix Broker"); db.add(b); db.flush()
    srv = TradingServer(tenant_id=t.id, broker_id=b.id, name="Sim", adapter_type="simulated", connection_config={})
    db.add(srv); db.flush()
    m = MasterAccount(tenant_id=t.id, broker_id=b.id, server_id=srv.id, login=f"M-{uuid.uuid4().hex[:6]}",
                      performance_fee_rate=Decimal("0.2"), allocation_method="euro_days",
                      manager_user_id=admin.id, nav_at_period_start=Decimal("100"))
    db.add(m); db.flush()
    s = Strategy(tenant_id=t.id, master_account_id=m.id, name="Fix Strategy", kind="pamm")
    acc_a = InvestorAccount(tenant_id=t.id, broker_id=b.id, login=f"A-{uuid.uuid4().hex[:6]}", owner_user_id=inv_a.id)
    acc_b = InvestorAccount(tenant_id=t.id, broker_id=b.id, login=f"B-{uuid.uuid4().hex[:6]}", owner_user_id=inv_b.id)
    db.add_all([s, acc_a, acc_b]); db.flush()
    return dict(tenant=t, admin=admin, inv_a=inv_a, inv_b=inv_b, master=m, strategy=s, acc_a=acc_a, acc_b=acc_b)


def test_investor_lists_only_own_accounts(client, db_session):
    c = _tenant(db_session)
    r = client.get("/api/investors", headers=_h(c["inv_a"]))
    assert r.status_code == 200
    assert [a["id"] for a in r.json()] == [c["acc_a"].id]


def test_investor_cannot_subscribe_with_someone_elses_account(client, db_session):
    c = _tenant(db_session)
    r = client.post("/api/subscriptions", headers=_h(c["inv_a"]), json={
        "strategy_id": c["strategy"].id, "investor_account_id": c["acc_b"].id, "capital": "1000"})
    assert r.status_code == 403
    r = client.post("/api/subscriptions", headers=_h(c["inv_a"]), json={
        "strategy_id": c["strategy"].id, "investor_account_id": c["acc_a"].id, "capital": "1000"})
    assert r.status_code == 200, r.text


def test_rollover_records_pnl_and_investor_sees_only_own_entry(client, db_session):
    c = _tenant(db_session)
    for inv, acc, cap in ((c["inv_a"], c["acc_a"], "10000"), (c["inv_b"], c["acc_b"], "5000")):
        assert client.post("/api/subscriptions", headers=_h(inv), json={
            "strategy_id": c["strategy"].id, "investor_account_id": acc.id, "capital": cap}).status_code == 200
    admin = _h(c["admin"])
    assert client.post(f"/api/simulate-pnl?master_id={c['master'].id}&pnl=1500", headers=admin).status_code == 200
    r = client.post("/api/rollovers", headers=admin, json={
        "master_account_id": c["master"].id, "idempotency_key": uuid.uuid4().hex, "period_days": 7})
    assert r.status_code == 200, r.text
    ro = r.json()
    assert Decimal(ro["master_pnl"]) == Decimal("1500.00")
    db_ro = db_session.get(Rollover, ro["id"])
    assert Decimal(db_ro.master_equity_after) == Decimal("16500.00") - Decimal(ro["total_performance_fee"])

    full = client.get(f"/api/rollovers/{ro['id']}", headers=admin).json()
    assert len(full["entries"]) == 2
    mine = client.get(f"/api/rollovers/{ro['id']}", headers=_h(c["inv_a"])).json()
    assert [e["investor_login"] for e in mine["entries"]] == [c["acc_a"].login]


def test_public_endpoints_scoped_to_showcase_tenant(client, db_session):
    showcase = db_session.query(Tenant).filter(Tenant.slug == settings.default_tenant).first()
    c = _tenant(db_session, slug=None if showcase else settings.default_tenant)
    other = _tenant(db_session)
    logins = {a["login"] for a in client.get("/api/public/top-accounts?limit=50").json()}
    assert other["master"].login not in logins
    if not showcase:
        assert c["master"].login in logins
