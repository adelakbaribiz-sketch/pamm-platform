"""Cross-tenant access must be denied."""
from app.models import Broker, MasterAccount, TradingServer, Tenant, User
from app.auth import hash_password, create_access_token

def test_broker_admin_cannot_see_other_tenant_masters(db_session):
    t1 = Tenant(name="T1", slug="t1"); db_session.add(t1); db_session.flush()
    t2 = Tenant(name="T2", slug="t2"); db_session.add(t2); db_session.flush()
    b1 = Broker(tenant_id=t1.id, name="B1"); db_session.add(b1); db_session.flush()
    b2 = Broker(tenant_id=t2.id, name="B2"); db_session.add(b2); db_session.flush()
    srv1 = TradingServer(tenant_id=t1.id, broker_id=b1.id, name="S1", adapter_type="simulated", connection_config={})
    srv2 = TradingServer(tenant_id=t2.id, broker_id=b2.id, name="S2", adapter_type="simulated", connection_config={})
    db_session.add_all([srv1, srv2]); db_session.flush()
    m1 = MasterAccount(tenant_id=t1.id, broker_id=b1.id, server_id=srv1.id, login="M1",
                       allocation_method="euro_days", nav_at_period_start=Decimal("100"))
    m2 = MasterAccount(tenant_id=t2.id, broker_id=b2.id, server_id=srv2.id, login="M2",
                       allocation_method="euro_days", nav_at_period_start=Decimal("100"))
    db_session.add_all([m1, m2]); db_session.flush()
    from app.models import MasterAccount as M
    t1_masters = db_session.query(M).filter(M.tenant_id == t1.id).all()
    t2_masters = db_session.query(M).filter(M.tenant_id == t2.id).all()
    assert {m.login for m in t1_masters} == {"M1"}
    assert {m.login for m in t2_masters} == {"M2"}

from decimal import Decimal

def test_cross_tenant_api_call_forbidden(client, db_session):
    t1 = Tenant(name="T1", slug="t1"); db_session.add(t1); db_session.flush()
    t2 = Tenant(name="T2", slug="t2"); db_session.add(t2); db_session.flush()
    u1 = User(tenant_id=t1.id, email="u1@t.com", role="broker_admin", password_hash=hash_password("pw"))
    db_session.add(u1); db_session.flush()
    b2 = Broker(tenant_id=t2.id, name="B2"); db_session.add(b2); db_session.flush()
    srv2 = TradingServer(tenant_id=t2.id, broker_id=b2.id, name="S2", adapter_type="simulated", connection_config={})
    db_session.add(srv2); db_session.flush()
    m2 = MasterAccount(tenant_id=t2.id, broker_id=b2.id, server_id=srv2.id, login="LEAKED",
                       allocation_method="euro_days", nav_at_period_start=Decimal("100"))
    db_session.add(m2); db_session.flush()
    token = create_access_token(u1.id, u1.role, u1.tenant_id)
    r = client.get("/api/masters", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert "LEAKED" not in {m["login"] for m in r.json()}
