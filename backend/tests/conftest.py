import os, pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from alembic.config import Config
from alembic import command
from app.db import Base, get_db
from app.models import Tenant, User, Broker, TradingServer, MasterAccount
from app.auth import hash_password
from fastapi.testclient import TestClient
from app.main import app

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL",
                             "postgresql+psycopg://pamm:pamm_dev_pw@localhost:5432/pamm_test")

@pytest.fixture(scope="session")
def db_engine():
    from urllib.parse import urlsplit
    parts = urlsplit(TEST_DB_URL)
    if parts.query and "host=" in parts.query:
        admin_url = f"postgresql+psycopg://{parts.username or 'postgres'}:{parts.password or ''}@/{parts.path.lstrip('/') or 'postgres'}?{parts.query}"
    else:
        host = parts.hostname or "/var/run/postgresql"
        admin_url = f"postgresql+psycopg://postgres:@{host}/postgres"
    eng = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with eng.connect() as conn:
        conn.execute(text("COMMIT"))
        try: conn.execute(text("DROP DATABASE IF EXISTS pamm_test"))
        except Exception: pass
        try: conn.execute(text("CREATE DATABASE pamm_test"))
        except Exception: pass
    eng.dispose()
    eng = create_engine(TEST_DB_URL)
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()

@pytest.fixture()
def db_session(db_engine):
    conn = db_engine.connect()
    trans = conn.begin()
    Session = sessionmaker(bind=conn)
    s = Session()
    s.begin_nested()
    try: yield s
    finally:
        s.close()
        trans.rollback()
        conn.close()

@pytest.fixture()
def client(db_session):
    def override_get_db():
        try: yield db_session
        finally: pass
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c: yield c
    app.dependency_overrides.clear()

@pytest.fixture()
def seeded_tenant(db_session):
    from decimal import Decimal
    t = Tenant(name="Test Tenant", slug=f"test-{os.urandom(4).hex()}", status="active")
    db_session.add(t); db_session.flush()
    u = User(tenant_id=t.id, email=f"admin-{os.urandom(4).hex()}@test.com",
             role="broker_admin", password_hash=hash_password("pw"))
    db_session.add(u); db_session.flush()
    b = Broker(tenant_id=t.id, name="Test Broker")
    db_session.add(b); db_session.flush()
    srv = TradingServer(tenant_id=t.id, broker_id=b.id, name="Sim",
                        adapter_type="simulated", connection_config={})
    db_session.add(srv); db_session.flush()
    m = MasterAccount(tenant_id=t.id, broker_id=b.id, server_id=srv.id,
                      login=f"M-{os.urandom(4).hex()}",
                      performance_fee_rate=Decimal("0.2"),
                      allocation_method="euro_days", manager_user_id=u.id,
                      nav_at_period_start=Decimal("100"))
    db_session.add(m); db_session.flush()
    return {"tenant": t, "user": u, "broker": b, "server": srv, "master": m}
