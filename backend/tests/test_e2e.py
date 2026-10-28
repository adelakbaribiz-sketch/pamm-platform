"""End-to-end PAMM acceptance workflow."""
import uuid
from decimal import Decimal
from app.auth import create_access_token
from app.models import (Tenant, User, Broker, TradingServer, MasterAccount, Strategy,
                        InvestorAccount)

def _seed_demo_tenant(db_session):
    t = Tenant(name="E2E Tenant", slug=f"e2e-{uuid.uuid4().hex[:8]}")
    db_session.add(t); db_session.flush()
    u = User(tenant_id=t.id, email=f"e2e-{uuid.uuid4().hex[:8]}@test.com",
             role="broker_admin", password_hash="$2b$12$dummy")
    db_session.add(u); db_session.flush()
    b = Broker(tenant_id=t.id, name="E2E Broker")
    db_session.add(b); db_session.flush()
    srv = TradingServer(tenant_id=t.id, broker_id=b.id, name="Sim",
                        adapter_type="simulated", connection_config={})
    db_session.add(srv); db_session.flush()
    m = MasterAccount(tenant_id=t.id, broker_id=b.id, server_id=srv.id,
                      login=f"M-{uuid.uuid4().hex[:6]}",
                      performance_fee_rate=Decimal("0.2"),
                      allocation_method="euro_days", manager_user_id=u.id,
                      nav_at_period_start=Decimal("100"))
    db_session.add(m); db_session.flush()
    strat = Strategy(tenant_id=t.id, master_account_id=m.id, name="E2E Strategy", kind="pamm")
    db_session.add(strat); db_session.flush()
    inv1 = InvestorAccount(tenant_id=t.id, broker_id=b.id, login=f"I1-{uuid.uuid4().hex[:6]}",
                            owner_user_id=u.id)
    inv2 = InvestorAccount(tenant_id=t.id, broker_id=b.id, login=f"I2-{uuid.uuid4().hex[:6]}",
                            owner_user_id=u.id)
    db_session.add_all([inv1, inv2]); db_session.flush()
    return {"tenant": t, "user": u, "broker": b, "server": srv, "master": m,
            "strategy": strat, "inv1": inv1, "inv2": inv2}

def test_full_pamm_workflow(client, db_session):
    ctx = _seed_demo_tenant(db_session)
    token = create_access_token(ctx["user"].id, ctx["user"].role, ctx["user"].tenant_id)
    H = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/subscriptions", headers=H, json={
        "strategy_id": ctx["strategy"].id, "investor_account_id": ctx["inv1"].id, "capital": "10000"})
    assert r.status_code == 200, r.text
    sub1_id = r.json()["subscription_id"]
    r = client.post("/api/subscriptions", headers=H, json={
        "strategy_id": ctx["strategy"].id, "investor_account_id": ctx["inv2"].id, "capital": "5000"})
    assert r.status_code == 200, r.text
    sub2_id = r.json()["subscription_id"]
    r = client.post(f"/api/simulate-pnl?master_id={ctx['master'].id}&pnl=3000", headers=H)
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["equity"]) == Decimal("18000.00")
    idem = uuid.uuid4().hex
    r = client.post("/api/rollovers", headers=H, json={
        "master_account_id": ctx["master"].id, "idempotency_key": idem, "period_days": 1})
    assert r.status_code == 200, r.text
    rollover = r.json()
    assert rollover["status"] == "completed"
    assert len(rollover["entries"]) == 2
    e1 = next(e for e in rollover["entries"] if e["subscription_id"] == sub1_id)
    e2 = next(e for e in rollover["entries"] if e["subscription_id"] == sub2_id)
    assert Decimal(e1["pnl_share"]) == Decimal("2000.00")
    assert Decimal(e2["pnl_share"]) == Decimal("1000.00")
    assert Decimal(e1["performance_fee"]) == Decimal("400.00")
    assert Decimal(rollover["total_performance_fee"]) == Decimal("600.00")
    # Idempotent re-run returns same record
    r2 = client.post("/api/rollovers", headers=H, json={
        "master_account_id": ctx["master"].id, "idempotency_key": idem, "period_days": 1})
    assert r2.json()["id"] == rollover["id"]
    # Merkle root + proofs
    r = client.get(f"/api/rollovers/{rollover['id']}/merkle-root", headers=H)
    assert r.status_code == 200
    root = r.json()["root_hash"]
    for sub_id in (sub1_id, sub2_id):
        r = client.get(f"/api/rollovers/{rollover['id']}/proofs/{sub_id}", headers=H)
        assert r.status_code == 200
        assert r.json()["verified"] is True
        assert r.json()["root_hash"] == root
    r = client.get(f"/api/rollovers/{rollover['id']}/statement/{sub1_id}", headers=H)
    assert r.status_code == 200
    assert Decimal(r.json()["performance_fee"]) == Decimal("400.00")

def test_risk_blocks_excessive_pnl(client, db_session):
    ctx = _seed_demo_tenant(db_session)
    from app.models import RiskRule
    db_session.add(RiskRule(tenant_id=ctx["tenant"].id, master_account_id=ctx["master"].id,
                           name="cap", kind="max_total_exposure",
                           params={"limit": "5000"}, active=True))
    db_session.flush()
    token = create_access_token(ctx["user"].id, ctx["user"].role, ctx["user"].tenant_id)
    H = {"Authorization": f"Bearer {token}"}
    r = client.post(f"/api/simulate-pnl?master_id={ctx['master'].id}&pnl=10000", headers=H)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "MAX_TOTAL_EXPOSURE"
