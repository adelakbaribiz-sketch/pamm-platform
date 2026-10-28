from decimal import Decimal
from app.domain import risk
from app.models import RiskRule

def test_max_exposure_rejection(db_session, seeded_tenant):
    m = seeded_tenant["master"]
    db_session.add(RiskRule(tenant_id=m.tenant_id, master_account_id=m.id, name="cap",
                           kind="max_total_exposure", params={"limit": "10000"}, active=True))
    db_session.flush()
    try:
        risk.check_pnl_mutation(db_session, m.tenant_id, m.id, Decimal("0"), Decimal("20000"))
        assert False
    except risk.RiskError as e:
        assert e.code == "MAX_TOTAL_EXPOSURE"

def test_invalid_subscription_capital(db_session, seeded_tenant):
    m = seeded_tenant["master"]
    try:
        risk.check_subscription(db_session, m.tenant_id, m.id, Decimal("-100"))
        assert False
    except risk.RiskError as e:
        assert e.code == "INVALID_CAPITAL"

def test_circuit_breaker_blocks_all(db_session, seeded_tenant):
    m = seeded_tenant["master"]
    db_session.add(RiskRule(tenant_id=m.tenant_id, master_account_id=m.id, name="cb",
                           kind="circuit_breaker", params={"tripped": True}, active=True))
    db_session.flush()
    try:
        risk.check_pnl_mutation(db_session, m.tenant_id, m.id, Decimal("0"), Decimal("1"))
        assert False
    except risk.RiskError as e:
        assert e.code == "CIRCUIT_BREAKER_TRIPPED"

def test_no_rule_allows_mutation(db_session, seeded_tenant):
    m = seeded_tenant["master"]
    risk.check_pnl_mutation(db_session, m.tenant_id, m.id, Decimal("1000"), Decimal("500"))

def test_max_lot_per_order_rejection(db_session, seeded_tenant):
    m = seeded_tenant["master"]
    db_session.add(RiskRule(tenant_id=m.tenant_id, master_account_id=m.id, name="lotcap",
                           kind="max_lot_per_order", params={"limit": "1.0"}, active=True))
    db_session.flush()
    try:
        risk.check_order(db_session, m.tenant_id, m.id, "EURUSD", Decimal("5"), Decimal("1.05"))
        assert False
    except risk.RiskError as e:
        assert e.code == "MAX_LOT_PER_ORDER"
