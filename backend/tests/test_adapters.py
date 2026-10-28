"""Adapter contract tests — verify both LIVE and BLOCKED modes.

These tests verify:
  1. Simulated adapter: full contract execution.
  2. MT5/cTrader/crypto adapters: graceful BLOCKED fallback when SDK/creds unavailable.
  3. When the SDK IS available (mocked), the adapter calls real SDK methods.
  4. Adapter registry: all 4 types registered with correct blocked status.

Because we cannot install the real MT5 SDK (Windows-only) or provide real
broker credentials in this environment, the blocked-mode tests verify the
graceful fallback. The live-mode tests use unittest.mock to simulate the
SDK and verify the call patterns are correct.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch, ANY
from app.adapters.base import (
    ExecutionAdapterError, NotImplementedError_, AccountSnapshot, ExecutionResult,
    OrderRejectedError,
)
from app.adapters.simulated import SimulatedAdapter
from app.adapters.mt5 import MT5Adapter, _MT5_AVAILABLE
from app.adapters.ctrader import CTraderAdapter, _CTRADER_AVAILABLE
from app.adapters.crypto import CryptoAdapter, _CCXT_AVAILABLE
from app.adapters.registry import get_adapter, list_adapters, REGISTRY


# ==================== Simulated: full contract ====================

def test_simulated_connect_disconnect_idempotent():
    a = SimulatedAdapter()
    a.connect({})
    assert a.discover_capabilities().is_live is False
    a.disconnect()
    a.disconnect()

def test_simulated_submit_order_returns_full_execution_result():
    a = SimulatedAdapter({"starting_equity": "100000"})
    a.connect({})
    r = a.submit_order(login="INV-001", symbol="EURUSD", side="buy", lots=Decimal("1.0"),
                       order_type="market", price=Decimal("1.10"), client_order_id="coid-1")
    assert isinstance(r, ExecutionResult)
    assert r.status == "filled"
    assert r.broker_order_id.startswith("SIM-")
    assert r.fill_price is not None
    assert r.filled_lots == Decimal("1.0")
    assert r.server_side_latency_ms > 0
    assert r.broker_latency_ms > 0
    assert r.slippage_bps is not None
    assert r.warning is not None and "SIMULATED" in r.warning
    assert r.is_reversible is True

def test_simulated_submit_order_rejects_invalid_side():
    a = SimulatedAdapter(); a.connect({})
    try:
        a.submit_order("INV", "EURUSD", "invalid_side", Decimal("1"))
        assert False
    except ExecutionAdapterError as e:
        assert e.code == "ORDER_REJECTED"

def test_simulated_submit_order_rejects_oversize_lots():
    a = SimulatedAdapter(); a.connect({})
    try:
        a.submit_order("INV", "EURUSD", "buy", Decimal("1000"))
        assert False
    except ExecutionAdapterError as e:
        assert e.code == "ORDER_REJECTED"

def test_simulated_get_account_snapshot():
    a = SimulatedAdapter({"starting_equity": "50000", "currency": "USD"})
    a.connect({})
    snap = a.get_account_snapshot("INV-001")
    assert isinstance(snap, AccountSnapshot)
    assert snap.balance == Decimal("50000")
    assert snap.equity == Decimal("50000")
    assert snap.currency == "USD"
    assert snap.warning is not None

def test_simulated_modify_cancel_close_lifecycle():
    a = SimulatedAdapter(); a.connect({})
    r = a.submit_order("INV", "EURUSD", "buy", Decimal("1.0"), price=Decimal("1.10"))
    m = a.modify_order(r.broker_order_id, new_lots=Decimal("2.0"), new_price=Decimal("1.11"))
    assert m.status == "modified"
    c1 = a.cancel_order(r.broker_order_id)
    assert c1.status == "cancelled"
    c2 = a.cancel_order(r.broker_order_id)
    assert c2.status == "cancelled_already"
    snap = a.get_account_snapshot("INV")
    assert len(snap.positions) == 1
    pos_id = snap.positions[0]["position_id"]
    cl = a.close_position("INV", pos_id)
    assert cl.status == "filled"
    assert cl.is_reversible is False

def test_simulated_reconcile_no_discrepancies():
    a = SimulatedAdapter(); a.connect({})
    r = a.reconcile("INV-001")
    assert r["discrepancies"] == []
    assert r["adapter"] == "simulated"
    assert r["is_live"] is False
    assert "last_reconciled_at" in r

def test_simulated_normalize_error_maps_codes():
    a = SimulatedAdapter(); a.connect({})
    assert a.normalize_error(Exception("auth failed")).code == "AUTH_FAILED"
    assert a.normalize_error(Exception("insufficient margin")).code == "INSUFFICIENT_MARGIN"
    assert a.normalize_error(Exception("rate limit exceeded")).code == "RATE_LIMITED"
    assert a.normalize_error(Exception("market closed")).code == "MARKET_CLOSED"
    assert a.normalize_error(Exception("connection refused")).code == "CONNECTION_LOST"
    assert a.normalize_error(Exception("random boom")).code == "UNKNOWN"

def test_simulated_not_connected_raises_connection_lost():
    a = SimulatedAdapter()
    try:
        a.get_account_snapshot("INV")
        assert False
    except ExecutionAdapterError as e:
        assert e.code == "CONNECTION_LOST"

def test_simulated_capabilities_complete():
    a = SimulatedAdapter()
    caps = a.discover_capabilities()
    assert caps.is_live is False
    assert caps.supports_market_orders
    assert caps.supports_limit_orders
    assert caps.supports_modify
    assert caps.supports_cancel
    assert caps.supports_partial_fills
    assert caps.supports_reconciliation
    assert "EURUSD" in caps.supported_symbols


# ==================== MT5: BLOCKED mode (current env, no SDK) ====================

def test_mt5_adapter_blocked_when_sdk_unavailable():
    """When MetaTrader5 package is not installed, adapter is BLOCKED."""
    a = MT5Adapter()
    if _MT5_AVAILABLE:
        pytest.skip("MT5 SDK is installed; this test verifies blocked mode")
    # Should raise NOT_IMPLEMENTED with the SDK blocker reason
    try:
        a.connect({})
        assert False, "should have raised NotImplementedError_"
    except NotImplementedError_ as e:
        assert e.code == "NOT_IMPLEMENTED"
        assert "MetaTrader5" in e.details.get("reason", "") or "not installed" in e.details.get("reason", "")

def test_mt5_adapter_blocked_when_no_credentials():
    """When SDK is available but credentials are missing, adapter is BLOCKED."""
    # Simulate SDK being available by patching the module flag
    with patch("app.adapters.mt5._MT5_AVAILABLE", True):
        with patch("app.adapters.mt5.mt5", MagicMock()):
            # Don't set credentials
            a = MT5Adapter()
            assert a._blocker is not None
            assert "credentials" in a._blocker.lower() or "CTRADER" in a._blocker or "MT5_LOGIN" in a._blocker
            try:
                a.connect({})
                assert False
            except NotImplementedError_ as e:
                assert e.code == "NOT_IMPLEMENTED"
                assert "credentials" in e.details.get("reason", "").lower()

def test_mt5_capabilities_documented_even_when_blocked():
    """The capability matrix is returned even when blocked, for routing decisions."""
    a = MT5Adapter()
    caps = a.discover_capabilities()
    assert caps.supports_market_orders is True
    assert caps.supports_modify is True
    assert caps.supports_partial_fills is True
    assert caps.supports_reconciliation is True
    assert caps.lot_step == Decimal("0.01")
    assert caps.is_live is False  # blocked
    assert caps.notes is not None  # contains blocker reason

def test_mt5_normalize_error_maps_mt5_codes():
    a = MT5Adapter()
    assert a.normalize_error(Exception("auth invalid_account")).code == "AUTH_FAILED"
    assert a.normalize_error(Exception("no_money insufficient")).code == "INSUFFICIENT_MARGIN"
    assert a.normalize_error(Exception("market_closed")).code == "MARKET_CLOSED"
    assert a.normalize_error(Exception("connection timeout")).code == "CONNECTION_LOST"
    assert a.normalize_error(Exception("retcode=10013")).code == "ORDER_REJECTED"


# ==================== MT5: LIVE mode (mocked SDK) ====================

def test_mt5_connect_with_mocked_sdk_succeeds():
    """When SDK IS available + credentials provided, connect() calls mt5.initialize()."""
    mock_mt5 = MagicMock()
    mock_mt5.initialize.return_value = True
    # account_info() returns a named-tuple-like object
    mock_account = MagicMock()
    mock_account.balance = 10000.0
    mock_account.equity = 10500.0
    mock_account.login = 12345
    mock_account.currency = "USD"
    mock_account.server_time = 1700000000
    mock_account.margin = 1000.0
    mock_account.margin_free = 9000.0
    mock_account.margin_level = 1050.0
    mock_mt5.account_info.return_value = mock_account

    with patch("app.adapters.mt5.mt5", mock_mt5):
        with patch("app.adapters.mt5._MT5_AVAILABLE", True):
            a = MT5Adapter({"login": "12345", "password": "secret", "server": "Demo-Broker"})
            a.connect()
            assert a.is_live is True
            assert a._connected is True
            mock_mt5.initialize.assert_called_once()
            mock_mt5.account_info.assert_called_once()

def test_mt5_submit_order_with_mocked_sdk():
    """Verifies the SDK call pattern for submit_order."""
    mock_mt5 = MagicMock()
    # Setup: initialize + account_info succeed
    mock_mt5.initialize.return_value = True
    mock_account = MagicMock(balance=10000, equity=10000, login=12345, currency="USD",
                              server_time=1700000000, margin=0, margin_free=10000, margin_level=None)
    mock_mt5.account_info.return_value = mock_account
    # symbol_select + symbol_info succeed
    mock_mt5.symbol_select.return_value = True
    mock_sym = MagicMock(volume_step=0.01, volume_min=0.01, volume_max=100.0, digits=5)
    mock_mt5.symbol_info.return_value = mock_sym
    mock_tick = MagicMock(ask=1.10, bid=1.09)
    mock_mt5.symbol_info_tick.return_value = mock_tick
    # order_send succeeds
    mock_result = MagicMock(retcode=10009, order=12345, deal=67890,
                            price=1.105, volume=1.0, comment="ok")
    mock_mt5.order_send.return_value = mock_result
    mock_mt5.TRADE_ACTION_DEAL = 1
    mock_mt5.ORDER_TYPE_BUY = 0
    mock_mt5.ORDER_TYPE_SELL = 1
    mock_mt5.ORDER_TIME_GTC = 0
    mock_mt5.ORDER_FILLING_IOC = 1

    with patch("app.adapters.mt5.mt5", mock_mt5):
        with patch("app.adapters.mt5._MT5_AVAILABLE", True):
            a = MT5Adapter({"login": "12345", "password": "secret", "server": "Demo"})
            a.connect()
            result = a.submit_order("INV", "EURUSD", "buy", Decimal("1.0"), "market", Decimal("1.10"))
            assert result.status == "filled"
            assert result.broker_order_id == "12345"
            assert result.fill_price == Decimal("1.105")
            assert result.filled_lots == Decimal("1.0")
            # Verify SDK was called with the right order request
            mock_mt5.order_send.assert_called_once()
            sent_request = mock_mt5.order_send.call_args[0][0]
            assert sent_request["symbol"] == "EURUSD"
            assert sent_request["volume"] == 1.0

def test_mt5_submit_order_rejects_insufficient_margin():
    """When MT5 returns retcode 10019 (NO_MONEY), raises InsufficientMarginError."""
    mock_mt5 = MagicMock()
    mock_mt5.initialize.return_value = True
    mock_account = MagicMock(balance=100, equity=100, login=12345, currency="USD",
                              server_time=1700000000, margin=0, margin_free=100, margin_level=None)
    mock_mt5.account_info.return_value = mock_account
    mock_mt5.symbol_select.return_value = True
    mock_sym = MagicMock(volume_step=0.01, volume_min=0.01, volume_max=100.0, digits=5)
    mock_mt5.symbol_info.return_value = mock_sym
    mock_tick = MagicMock(ask=1.10, bid=1.09)
    mock_mt5.symbol_info_tick.return_value = mock_tick
    # order_send returns retcode 10019 = NO_MONEY
    mock_result = MagicMock(retcode=10019, order=0, deal=0, price=0, volume=0, comment="no money")
    mock_mt5.order_send.return_value = mock_result
    mock_mt5.TRADE_ACTION_DEAL = 1
    mock_mt5.ORDER_TYPE_BUY = 0
    mock_mt5.ORDER_TIME_GTC = 0
    mock_mt5.ORDER_FILLING_IOC = 1

    with patch("app.adapters.mt5.mt5", mock_mt5):
        with patch("app.adapters.mt5._MT5_AVAILABLE", True):
            a = MT5Adapter({"login": "12345", "password": "secret", "server": "Demo"})
            a.connect()
            try:
                a.submit_order("INV", "EURUSD", "buy", Decimal("100.0"), "market", Decimal("1.10"))
                assert False
            except ExecutionAdapterError as e:
                assert e.code == "INSUFFICIENT_MARGIN"


# ==================== cTrader: BLOCKED mode ====================

def test_ctrader_adapter_blocked_when_sdk_unavailable():
    a = CTraderAdapter()
    if _CTRADER_AVAILABLE:
        pytest.skip("cTrader SDK is installed; this test verifies blocked mode")
    try:
        a.connect({})
        assert False
    except NotImplementedError_ as e:
        assert e.code == "NOT_IMPLEMENTED"

def test_ctrader_capabilities_documented_even_when_blocked():
    a = CTraderAdapter()
    caps = a.discover_capabilities()
    assert caps.supports_market_orders is True
    assert caps.supports_modify is True
    assert caps.is_live is False
    assert caps.notes is not None

def test_ctrader_normalize_error_maps_specific_codes():
    a = CTraderAdapter()
    assert a.normalize_error(Exception("cTrader WRONG_STOPS error")).code == "ORDER_REJECTED"
    assert a.normalize_error(Exception("MARKET_CLOSED on Sunday")).code == "MARKET_CLOSED"
    assert a.normalize_error(Exception("TRADING_BAD_VOLUME: too small")).code == "ORDER_REJECTED"
    assert a.normalize_error(Exception("auth unauthorized")).code == "AUTH_FAILED"


# ==================== Crypto: BLOCKED mode ====================

def test_crypto_adapter_blocked_when_sdk_unavailable():
    a = CryptoAdapter({"exchange": "binance"})
    if _CCXT_AVAILABLE:
        pytest.skip("ccxt SDK is installed; this test verifies blocked mode")
    try:
        a.connect({})
        assert False
    except NotImplementedError_ as e:
        assert e.code == "NOT_IMPLEMENTED"

def test_crypto_capabilities_documented_even_when_blocked():
    a = CryptoAdapter({"exchange": "kraken"})
    caps = a.discover_capabilities()
    assert caps.is_live is False
    assert caps.lot_step == Decimal("0.00000001")  # 8dp for crypto
    assert caps.notes is not None
    assert "kraken" in caps.notes or "binance" in caps.notes or "ccxt" in caps.notes

def test_crypto_normalize_maps_insufficient_balance():
    a = CryptoAdapter({"exchange": "binance"})
    assert a.normalize_error(Exception("insufficient balance for order")).code == "INSUFFICIENT_MARGIN"
    assert a.normalize_error(Exception("429 Too Many Requests")).code == "RATE_LIMITED"
    assert a.normalize_error(Exception("InvalidApiKey")).code == "AUTH_FAILED"
    assert a.normalize_error(Exception("network timeout")).code == "CONNECTION_LOST"


# ==================== Crypto: LIVE mode (mocked ccxt) ====================

def test_crypto_connect_with_mocked_ccxt():
    """When ccxt IS available + credentials provided, connect() constructs the exchange."""
    mock_ccxt = MagicMock()
    mock_exchange = MagicMock()
    mock_exchange.fetch_balance.return_value = {"free": {"USDT": 10000}, "used": {}, "total": {"USDT": 10000}}
    mock_ccxt.binance.return_value = mock_exchange

    with patch("app.adapters.crypto.ccxt", mock_ccxt):
        with patch("app.adapters.crypto._CCXT_AVAILABLE", True):
            a = CryptoAdapter({"exchange": "binance", "api_key": "key", "api_secret": "secret"})
            a.connect()
            assert a.is_live is True
            assert a._connected is True
            mock_ccxt.binance.assert_called_once()
            # Verify credentials were passed
            call_kwargs = mock_ccxt.binance.call_args[0][0]
            assert call_kwargs["apiKey"] == "key"
            assert call_kwargs["secret"] == "secret"

def test_crypto_submit_order_with_mocked_ccxt():
    """Verifies the ccxt call pattern for create_order."""
    mock_ccxt = MagicMock()
    mock_exchange = MagicMock()
    mock_exchange.fetch_balance.return_value = {"free": {"USDT": 10000}, "used": {}, "total": {"USDT": 10000}}
    mock_exchange.create_order.return_value = {
        "id": "binance-12345",
        "status": "closed",
        "average": 50000.5,
        "filled": 0.1,
    }
    mock_ccxt.binance.return_value = mock_exchange

    with patch("app.adapters.crypto.ccxt", mock_ccxt):
        with patch("app.adapters.crypto._CCXT_AVAILABLE", True):
            a = CryptoAdapter({"exchange": "binance", "api_key": "k", "api_secret": "s"})
            a.connect()
            result = a.submit_order("INV", "BTC/USDT", "buy", Decimal("0.1"), "market", Decimal("50000"))
            assert result.status == "filled"
            assert result.broker_order_id == "binance-12345"
            assert result.fill_price == Decimal("50000.5")
            assert result.filled_lots == Decimal("0.1")
            mock_exchange.create_order.assert_called_once()
            call_args = mock_exchange.create_order.call_args
            assert call_args[1]["symbol"] == "BTC/USDT"
            assert call_args[1]["side"] == "buy"
            assert call_args[1]["amount"] == 0.1


# ==================== Registry ====================

def test_registry_lists_all_four_adapters():
    adapters = list_adapters()
    types = {a["type"] for a in adapters}
    assert types == {"simulated", "mt5", "ctrader", "crypto"}

def test_registry_marks_blocked_adapters_correctly():
    adapters = list_adapters()
    by_type = {a["type"]: a for a in adapters}
    assert by_type["simulated"]["blocked"] is False
    assert by_type["simulated"]["is_live"] is False
    # MT5/cTrader/crypto are blocked when SDK is unavailable
    if not _MT5_AVAILABLE:
        assert by_type["mt5"]["blocked"] is True
    if not _CTRADER_AVAILABLE:
        assert by_type["ctrader"]["blocked"] is True
    if not _CCXT_AVAILABLE:
        assert by_type["crypto"]["blocked"] is True

def test_registry_get_adapter_returns_correct_class():
    from app.adapters.simulated import SimulatedAdapter
    from app.adapters.mt5 import MT5Adapter
    assert isinstance(get_adapter("simulated"), SimulatedAdapter)
    assert isinstance(get_adapter("mt5"), MT5Adapter)

def test_registry_get_adapter_rejects_unknown():
    try:
        get_adapter("unknown")
        assert False
    except ValueError as e:
        assert "unknown adapter" in str(e)
