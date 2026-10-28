"""Copy trading engine: dedup, ordering, follower controls, slippage measurement."""
import uuid
from decimal import Decimal
from app.domain.copy import CopyEngine
from app.models import (Tenant, User, Broker, TradingServer, MasterAccount, Strategy,
                        InvestorAccount, CopySubscription, CopyTrade)

def _seed(db_session):
    from app.auth import hash_password
    t = Tenant(name="T", slug=f"ct-{uuid.uuid4().hex[:8]}"); db_session.add(t); db_session.flush()
    u = User(tenant_id=t.id, email=f"ct-{uuid.uuid4().hex[:8]}@test.com",
             role="broker_admin", password_hash=hash_password("pw"))
    db_session.add(u); db_session.flush()
    b = Broker(tenant_id=t.id, name="B"); db_session.add(b); db_session.flush()
    srv = TradingServer(tenant_id=t.id, broker_id=b.id, name="S", adapter_type="simulated",
                        connection_config={})
    db_session.add(srv); db_session.flush()
    m = MasterAccount(tenant_id=t.id, broker_id=b.id, server_id=srv.id,
                      login=f"M-{uuid.uuid4().hex[:6]}",
                      allocation_method="euro_days", nav_at_period_start=Decimal("100"))
    db_session.add(m); db_session.flush()
    strat = Strategy(tenant_id=t.id, master_account_id=m.id, name="S", kind="copy")
    db_session.add(strat); db_session.flush()
    return {"tenant": t, "user": u, "broker": b, "server": srv, "master": m, "strategy": strat}

def test_copy_trade_idempotent(db_session):
    ctx = _seed(db_session)
    eng = CopyEngine(db_session)
    idem = uuid.uuid4().hex
    ct1 = eng.open_master_trade(ctx["tenant"].id, ctx["strategy"].id, ctx["master"].id,
                                 "EURUSD", "buy", Decimal("1"), Decimal("1.10"),
                                 idempotency_key=idem)
    ct2 = eng.open_master_trade(ctx["tenant"].id, ctx["strategy"].id, ctx["master"].id,
                                 "EURUSD", "buy", Decimal("1"), Decimal("1.10"),
                                 idempotency_key=idem)
    assert ct1.id == ct2.id, "duplicate idempotency_key must return same copy_trade"

def test_replicate_to_followers_with_active_sub(db_session):
    ctx = _seed(db_session)
    db_session.add(InvestorAccount(tenant_id=ctx["tenant"].id, broker_id=ctx["broker"].id,
                                    login="F1", owner_user_id=ctx["user"].id))
    db_session.flush()
    fa = db_session.query(InvestorAccount).filter(InvestorAccount.login == "F1").first()
    db_session.add(CopySubscription(
        tenant_id=ctx["tenant"].id, strategy_id=ctx["strategy"].id,
        master_account_id=ctx["master"].id, follower_account_id=fa.id,
        follower_user_id=ctx["user"].id, status="active", lot_multiplier=Decimal("2"),
    )); db_session.flush()
    eng = CopyEngine(db_session)
    ct = eng.open_master_trade(ctx["tenant"].id, ctx["strategy"].id, ctx["master"].id,
                                "EURUSD", "buy", Decimal("1"), Decimal("1.10"),
                                idempotency_key=uuid.uuid4().hex)
    fts = eng.replicate_to_followers(ct, Decimal("1.11"))
    assert len(fts) == 1
    ft = fts[0]
    assert ft.status == "filled"
    assert ft.requested_lots == Decimal("2.00"), "lot_multiplier applied"
    assert ft.fill_price == Decimal("1.11")
    assert ft.server_side_latency_ms is not None and ft.server_side_latency_ms > 0
    assert ft.broker_latency_ms is not None and ft.broker_latency_ms > 0
    assert ft.slippage_bps is not None
    # Slippage = (1.11 - 1.10)/1.10 * 10000 = ~90.91 bps
    assert Decimal("90") <= ft.slippage_bps <= Decimal("92")

def test_paused_subscriber_skipped(db_session):
    ctx = _seed(db_session)
    db_session.add(InvestorAccount(tenant_id=ctx["tenant"].id, broker_id=ctx["broker"].id,
                                    login="F1", owner_user_id=ctx["user"].id))
    db_session.flush()
    fa = db_session.query(InvestorAccount).filter(InvestorAccount.login == "F1").first()
    cs = CopySubscription(tenant_id=ctx["tenant"].id, strategy_id=ctx["strategy"].id,
                          master_account_id=ctx["master"].id, follower_account_id=fa.id,
                          status="active", lot_multiplier=Decimal("1"))
    db_session.add(cs); db_session.flush()
    eng = CopyEngine(db_session)
    eng.pause(cs.id, ctx["tenant"].id)
    ct = eng.open_master_trade(ctx["tenant"].id, ctx["strategy"].id, ctx["master"].id,
                                "EURUSD", "buy", Decimal("1"), Decimal("1.10"),
                                idempotency_key=uuid.uuid4().hex)
    fts = eng.replicate_to_followers(ct, Decimal("1.10"))
    # paused subscribers are filtered out by the query in replicate_to_followers
    assert len(fts) == 0

def test_symbol_exclusion_skipped(db_session):
    ctx = _seed(db_session)
    db_session.add(InvestorAccount(tenant_id=ctx["tenant"].id, broker_id=ctx["broker"].id,
                                    login="F1", owner_user_id=ctx["user"].id))
    db_session.flush()
    fa = db_session.query(InvestorAccount).filter(InvestorAccount.login == "F1").first()
    db_session.add(CopySubscription(
        tenant_id=ctx["tenant"].id, strategy_id=ctx["strategy"].id,
        master_account_id=ctx["master"].id, follower_account_id=fa.id,
        status="active", excluded_symbols=["EURUSD"],
    )); db_session.flush()
    eng = CopyEngine(db_session)
    ct = eng.open_master_trade(ctx["tenant"].id, ctx["strategy"].id, ctx["master"].id,
                                "EURUSD", "buy", Decimal("1"), Decimal("1.10"),
                                idempotency_key=uuid.uuid4().hex)
    fts = eng.replicate_to_followers(ct, Decimal("1.10"))
    assert fts[0].status == "skipped"
    assert fts[0].reject_reason == "SYMBOL_EXCLUDED"

def test_max_lots_cap(db_session):
    ctx = _seed(db_session)
    db_session.add(InvestorAccount(tenant_id=ctx["tenant"].id, broker_id=ctx["broker"].id,
                                    login="F1", owner_user_id=ctx["user"].id))
    db_session.flush()
    fa = db_session.query(InvestorAccount).filter(InvestorAccount.login == "F1").first()
    db_session.add(CopySubscription(
        tenant_id=ctx["tenant"].id, strategy_id=ctx["strategy"].id,
        master_account_id=ctx["master"].id, follower_account_id=fa.id,
        status="active", lot_multiplier=Decimal("5"), max_lots_per_trade=Decimal("2"),
    )); db_session.flush()
    eng = CopyEngine(db_session)
    ct = eng.open_master_trade(ctx["tenant"].id, ctx["strategy"].id, ctx["master"].id,
                                "EURUSD", "buy", Decimal("1"), Decimal("1.10"),
                                idempotency_key=uuid.uuid4().hex)
    fts = eng.replicate_to_followers(ct, Decimal("1.10"))
    assert fts[0].requested_lots == Decimal("2")
    assert fts[0].status == "filled"

def test_detach_permanent(db_session):
    ctx = _seed(db_session)
    db_session.add(InvestorAccount(tenant_id=ctx["tenant"].id, broker_id=ctx["broker"].id,
                                    login="F1", owner_user_id=ctx["user"].id))
    db_session.flush()
    fa = db_session.query(InvestorAccount).filter(InvestorAccount.login == "F1").first()
    cs = CopySubscription(tenant_id=ctx["tenant"].id, strategy_id=ctx["strategy"].id,
                          master_account_id=ctx["master"].id, follower_account_id=fa.id,
                          status="active", lot_multiplier=Decimal("1"))
    db_session.add(cs); db_session.flush()
    eng = CopyEngine(db_session)
    eng.detach(cs.id, ctx["tenant"].id, close_positions=False)
    assert cs.status == "detached"
    assert cs.detached_at is not None
    # Try to resume — should fail
    try:
        eng.resume(cs.id, ctx["tenant"].id)
        assert False
    except ValueError as e:
        assert "detached" in str(e).lower()
