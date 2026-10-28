"""Seed demo data."""
import os
from decimal import Decimal
from .db import SessionLocal, engine, Base
from .models import (Tenant, User, Broker, TradingServer, MasterAccount, Strategy,
                     RiskRule)
from .auth import hash_password

def run():
    _seed_base()
    if os.environ.get("SEED_DEMO_HISTORY", "1") != "0":
        from .demo_history import populate
        populate()

def _seed_base():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Tenant).count() > 0:
            return
        t = Tenant(name="Demo Broker Ltd", slug="demo-broker", status="active")
        db.add(t); db.flush()
        def mk_user(email, role, pw):
            u = User(tenant_id=t.id, email=email, role=role, password_hash=hash_password(pw))
            db.add(u); db.flush(); return u
        broker_admin = mk_user("broker@demo.com", "broker_admin", "Demo1234!")
        mm = mk_user("manager@demo.com", "money_manager", "Demo1234!")
        mk_user("investor1@demo.com", "investor", "Demo1234!")
        mk_user("investor2@demo.com", "investor", "Demo1234!")
        mk_user("compliance@demo.com", "compliance", "Demo1234!")
        b = Broker(tenant_id=t.id, name="Demo Broker", legal_entity="Demo Broker Ltd")
        db.add(b); db.flush()
        srv = TradingServer(tenant_id=t.id, broker_id=b.id, name="Simulated",
                            adapter_type="simulated", connection_config={"starting_equity": "0"})
        db.add(srv); db.flush()
        # PAMM master
        m = MasterAccount(
            tenant_id=t.id, broker_id=b.id, server_id=srv.id,
            login="MASTER-001", currency="USD", base_nav=Decimal("100"),
            performance_fee_rate=Decimal("0.2"), management_fee_rate=Decimal("0"),
            allocation_method="euro_days", manager_user_id=mm.id,
            nav_at_period_start=Decimal("100"),
        )
        db.add(m); db.flush()
        db.add(Strategy(tenant_id=t.id, master_account_id=m.id, name="Alpha Equity Strategy",
                        description="Long-biased equity PAMM (simulated)", kind="pamm"))
        # MAM master
        m_mam = MasterAccount(
            tenant_id=t.id, broker_id=b.id, server_id=srv.id,
            login="MAM-MASTER-001", currency="USD", base_nav=Decimal("100"),
            performance_fee_rate=Decimal("0.2"), allocation_method="euro_days",
            manager_user_id=mm.id, nav_at_period_start=Decimal("100"),
        )
        db.add(m_mam); db.flush()
        db.add(Strategy(tenant_id=t.id, master_account_id=m_mam.id, name="MAM Aggregator Strategy",
                        description="MAM pooled execution", kind="mam"))
        # Copy master
        m_copy = MasterAccount(
            tenant_id=t.id, broker_id=b.id, server_id=srv.id,
            login="COPY-MASTER-001", currency="USD", base_nav=Decimal("100"),
            performance_fee_rate=Decimal("0"), allocation_method="euro_days",
            manager_user_id=mm.id, nav_at_period_start=Decimal("100"),
        )
        db.add(m_copy); db.flush()
        db.add(Strategy(tenant_id=t.id, master_account_id=m_copy.id, name="Copy Signal Strategy",
                        description="Copy-trading signal provider", kind="copy"))
        # Default risk rules for PAMM master
        db.add(RiskRule(tenant_id=t.id, master_account_id=m.id, name="max_exposure",
                       kind="max_total_exposure", params={"limit": "10000000"}, active=True,
                       created_by=broker_admin.id))
        db.add(RiskRule(tenant_id=t.id, master_account_id=m.id, name="max_drawdown",
                       kind="max_drawdown", params={"limit_pct": "0.5", "peak": "0"},
                       active=True, created_by=broker_admin.id))
        # Second tenant
        t2 = Tenant(name="Other Broker Ltd", slug="other-broker", status="active")
        db.add(t2); db.flush()
        db.add(User(tenant_id=t2.id, email="other@broker.com", role="broker_admin",
                    password_hash=hash_password("Demo1234!")))
        db.commit()
        print("Seed complete. Demo users: broker/manager/investor1/investor2/compliance@demo.com (password Demo1234!)")
    finally:
        db.close()

if __name__ == "__main__":
    run()
