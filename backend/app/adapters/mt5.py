"""
MT5 adapter — production implementation with graceful BLOCKED fallback.

This adapter implements the full ExecutionAdapter contract using the official
`MetaTrader5` Python package. When the SDK is installed AND credentials are
provided, it makes real SDK calls against a live MT5 server.

When the SDK is NOT installed (e.g., on Linux, or in a dev environment
without broker credentials), the adapter:
  - Returns is_live=False in capabilities.
  - Raises NotImplementedError_ on every operation with a clear BLOCKED reason.
  - Still returns the documented capability matrix for routing decisions.

To unblock in production:
  1. Install on a Windows host: `pip install MetaTrader5`
  2. Install the MT5 terminal (32-bit or 64-bit per broker).
  3. Provide credentials via environment variables or a secrets manager:
       MT5_LOGIN=12345
       MT5_PASSWORD=your_password
       MT5_SERVER=YourBroker-Server
       MT5_PATH=C:\\Program Files\\YourBroker\\terminal64.exe  (optional)
  4. The adapter auto-detects the SDK + credentials on connect() and switches
     from BLOCKED mode to LIVE mode.

SDK reference:
  - mt5.initialize(path, login, password, server) → bool
  - mt5.account_info() → named tuple with balance, equity, margin, etc.
  - mt5.symbol_info(symbol) → named tuple with point, digits, volume_min, etc.
  - mt5.order_send(request) → named tuple with retcode, deal, order, etc.
  - mt5.positions_get() → tuple of position named tuples
  - mt5.orders_get() → tuple of pending order named tuples
  - mt5.shutdown() → disconnect

Error codes (mt5 retcode):
  - 10009: TRADE_RETCODE_DONE (success)
  - 10010: TRADE_RETCODE_DONE_PARTIAL (partial fill)
  - 10013: TRADE_RETCODE_INVALID (invalid request)
  - 10014: TRADE_RETCODE_INVALID_VOLUME
  - 10015: TRADE_RETCODE_INVALID_PRICE
  - 10016: TRADE_RETCODE_INVALID_STOPS
  - 10018: TRADE_RETCODE_MARKET_CLOSED
  - 10019: TRADE_RETCODE_NO_MONEY (insufficient margin)
  - 10027: TRADE_RETCODE_AUTOTRADING_DISABLED
"""
from __future__ import annotations
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional
import os
import logging

from .base import (
    ExecutionAdapter, AdapterCapabilities, ExecutionResult, AccountSnapshot,
    ExecutionAdapterError, OrderRejectedError, InsufficientMarginError,
    RateLimitedError, MarketClosedError, ConnectionLostError, NotImplementedError_,
)

logger = logging.getLogger(__name__)

# Try to import the MetaTrader5 SDK. On Linux / without the SDK, this fails.
try:
    import MetaTrader5 as mt5
    _MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    _MT5_AVAILABLE = False

# MT5 retcode → canonical error code mapping
_MT5_RETCODE_MAP = {
    10009: ("filled", None),            # TRADE_RETCODE_DONE
    10008: ("placed", None),            # TRADE_RETCODE_PLACED
    10010: ("partial", None),          # TRADE_RETCODE_DONE_PARTIAL
    10013: ("rejected", "ORDER_REJECTED"),      # TRADE_RETCODE_INVALID
    10014: ("rejected", "ORDER_REJECTED"),      # TRADE_RETCODE_INVALID_VOLUME
    10015: ("rejected", "ORDER_REJECTED"),      # TRADE_RETCODE_INVALID_PRICE
    10016: ("rejected", "ORDER_REJECTED"),      # TRADE_RETCODE_INVALID_STOPS
    10018: ("rejected", "MARKET_CLOSED"),        # TRADE_RETCODE_MARKET_CLOSED
    10019: ("rejected", "INSUFFICIENT_MARGIN"), # TRADE_RETCODE_NO_MONEY
    10027: ("rejected", "ORDER_REJECTED"),      # TRADE_RETCODE_AUTOTRADING_DISABLED
    10030: ("rejected", "MARKET_CLOSED"),       # TRADE_RETCODE_UNSUPPORTED_FILLING
}

BLOCKER_NO_SDK = ("MetaTrader5 Python SDK not installed. "
                  "Install on Windows: `pip install MetaTrader5`")
BLOCKER_NO_CREDS = ("MT5 credentials not provided. Set MT5_LOGIN, MT5_PASSWORD, "
                    "MT5_SERVER environment variables (or pass via config).")


class MT5Adapter(ExecutionAdapter):
    """Production MT5 adapter. Uses real SDK when available; BLOCKED otherwise."""

    adapter_type = "mt5"
    is_live = False  # Set to True on successful connect()

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._connected = False
        self._login = self.config.get("login") or os.environ.get("MT5_LOGIN")
        self._password = self.config.get("password") or os.environ.get("MT5_PASSWORD")
        self._server = self.config.get("server") or os.environ.get("MT5_SERVER")
        self._path = self.config.get("path") or os.environ.get("MT5_PATH")
        self._timeout = int(self.config.get("timeout", 60000))

    @property
    def _blocker(self) -> Optional[str]:
        """Returns the BLOCKED reason, or None if the adapter is ready to connect."""
        if not _MT5_AVAILABLE:
            return BLOCKER_NO_SDK
        if not (self._login and self._password and self._server):
            return BLOCKER_NO_CREDS
        return None

    @property
    def _is_ready(self) -> bool:
        return self._blocker is None

    # ---- connection lifecycle ----
    def connect(self, config: dict | None = None) -> None:
        if config:
            self.config = {**self.config, **config}
            self._login = self.config.get("login") or self._login
            self._password = self.config.get("password") or self._password
            self._server = self.config.get("server") or self._server
            self._path = self.config.get("path") or self._path

        blocker = self._blocker
        if blocker:
            raise NotImplementedError_("connect", blocker)

        # Real SDK call
        init_kwargs = {
            "login": int(self._login),
            "password": self._password,
            "server": self._server,
            "timeout": self._timeout,
        }
        if self._path:
            init_kwargs["path"] = self._path

        if not mt5.initialize(**init_kwargs):
            error = mt5.last_error()
            raise ConnectionLostError(f"MT5 initialize() failed: {error}")

        # Verify by fetching account info
        info = mt5.account_info()
        if info is None:
            error = mt5.last_error()
            mt5.shutdown()
            raise ConnectionLostError(f"MT5 account_info() returned None: {error}")

        self._connected = True
        self.is_live = True
        logger.info(f"MT5Adapter connected: login={self._login} server={self._server} "
                    f"balance={info.balance} equity={info.equity}")

    def disconnect(self) -> None:
        if self._connected and _MT5_AVAILABLE:
            try:
                mt5.shutdown()
            except Exception as e:
                logger.warning(f"MT5 shutdown error: {e}")
        self._connected = False
        self.is_live = False

    def _require_connected(self):
        if not self._is_ready:
            raise NotImplementedError_("operation", self._blocker)
        if not self._connected:
            raise ConnectionLostError("MT5 adapter not connected; call connect() first")

    # ---- capabilities ----
    def discover_capabilities(self) -> AdapterCapabilities:
        # The capability matrix is documented even when blocked, so the platform
        # can route on expected MT5 behavior.
        return AdapterCapabilities(
            supports_account_discovery=True,
            supports_balance_sync=True,
            supports_position_sync=True,
            supports_market_orders=True,
            supports_limit_orders=True,
            supports_stop_orders=True,
            supports_modify=True,
            supports_cancel=True,
            supports_partial_fills=True,  # broker-dependent; verified at runtime
            supports_close_all=True,
            supports_reconciliation=True,
            supports_execution_quality=True,
            max_lots_per_order=Decimal("1000"),
            lot_step=Decimal("0.01"),
            supported_symbols=[],  # discovered at runtime via mt5.symbols_get()
            is_live=self.is_live and self._connected,
            notes=self._blocker or f"MT5 connected (login={self._login}, server={self._server})",
        )

    # ---- account snapshot ----
    def get_account_snapshot(self, login: str) -> AccountSnapshot:
        self._require_connected()
        info = mt5.account_info()
        if info is None:
            error = mt5.last_error()
            raise ConnectionLostError(f"account_info() failed: {error}")
        # Get positions
        positions_raw = mt5.positions_get() or []
        positions = [
            {
                "position_id": str(p.ticket),
                "login": str(p.login),
                "symbol": p.symbol,
                "side": "buy" if p.type == 0 else "sell",  # 0=POSITION_TYPE_BUY
                "lots": Decimal(str(p.volume)),
                "open_price": Decimal(str(p.price_open)),
                "current_price": Decimal(str(p.price_current)),
                "profit": Decimal(str(p.profit)),
                "swap": Decimal(str(p.swap)),
                "broker_order_id": str(p.ticket),
            }
            for p in positions_raw
        ]
        return AccountSnapshot(
            login=str(info.login),
            balance=Decimal(str(info.balance)),
            equity=Decimal(str(info.equity)),
            margin=Decimal(str(info.margin)),
            free_margin=Decimal(str(info.margin_free)),
            margin_level=Decimal(str(info.margin_level)) if info.margin_level else None,
            currency=info.currency,
            server_time=datetime.fromtimestamp(info.server_time, tz=timezone.utc),
            positions=positions,
        )

    # ---- order lifecycle ----
    def submit_order(self, login: str, symbol: str, side: str,
                     lots: Decimal, order_type: str = "market",
                     price: Decimal | None = None,
                     client_order_id: str | None = None) -> ExecutionResult:
        self._require_connected()
        import time as _time
        start = _time.monotonic()

        # Ensure symbol is selected
        if not mt5.symbol_select(symbol, True):
            raise OrderRejectedError(f"symbol_select({symbol}) failed: {mt5.last_error()}")

        # Get symbol info for lot step + digits
        sym = mt5.symbol_info(symbol)
        if sym is None:
            raise OrderRejectedError(f"symbol_info({symbol}) returned None")

        # Normalize lots to the symbol's volume step
        normalized_lots = self._normalize_volume(Decimal(str(lots), ), Decimal(str(sym.volume_step)))
        if normalized_lots < Decimal(str(sym.volume_min)):
            raise OrderRejectedError(f"volume {normalized_lots} below min {sym.volume_min}")
        if normalized_lots > Decimal(str(sym.volume_max)):
            raise OrderRejectedError(f"volume {normalized_lots} above max {sym.volume_max}")

        # Build the MT5 order request
        mt5_type = self._map_order_type(side, order_type)
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(normalized_lots),
            "type": mt5_type,
            "deviation": 20,  # max slippage in points
            "magic": int(self.config.get("magic", 234000)),
            "comment": client_order_id or "pamm-platform",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        if order_type == "limit" and price is not None:
            request["price"] = float(price)
        elif mt5_type == mt5.ORDER_TYPE_BUY:
            # Market buy: use ask
            tick = mt5.symbol_info_tick(symbol)
            request["price"] = tick.ask if tick else float(price or 0)
        elif mt5_type == mt5.ORDER_TYPE_SELL:
            # Market sell: use bid
            tick = mt5.symbol_info_tick(symbol)
            request["price"] = tick.bid if tick else float(price or 0)

        # Send the order
        result = mt5.order_send(request)
        broker_latency = int((_time.monotonic() - start) * 1000)
        server_latency = 5  # our processing estimate

        if result is None:
            raise ConnectionLostError(f"order_send() returned None: {mt5.last_error()}")

        status, error_code = self._map_retcode(result.retcode)

        if result.retcode != 10009 and result.retcode != 10010:
            # Not a success
            msg = f"MT5 order_send retcode={result.retcode} comment={result.comment}"
            if error_code == "INSUFFICIENT_MARGIN":
                raise InsufficientMarginError(msg, {"retcode": result.retcode})
            elif error_code == "MARKET_CLOSED":
                raise MarketClosedError(msg, {"retcode": result.retcode})
            elif error_code == "ORDER_REJECTED":
                raise OrderRejectedError(msg, {"retcode": result.retcode})
            else:
                raise ExecutionAdapterError("UNKNOWN", msg, {"retcode": result.retcode})

        # Calculate slippage
        slippage_bps = None
        if price and result.price and float(price) > 0:
            slippage_bps = Decimal(str(
                (result.price - float(price)) / float(price) * 10000
            )).quantize(Decimal("0.0001"))

        return ExecutionResult(
            broker_order_id=str(result.order),
            status=status,
            fill_price=Decimal(str(result.price)) if result.price else None,
            filled_lots=Decimal(str(result.volume)),
            requested_lots=normalized_lots,
            server_side_latency_ms=server_latency,
            broker_latency_ms=broker_latency,
            slippage_bps=slippage_bps,
            timestamp=datetime.now(timezone.utc),
            raw_response={
                "retcode": result.retcode,
                "deal": result.deal,
                "order": result.order,
                "comment": result.comment,
                "external_id": getattr(result, "external_id", None),
            },
            is_reversible=False,  # Filled market orders can't be reversed; only hedged
            warning=None if self.is_live else "SIMULATED — MT5 SDK reported success",
        )

    def modify_order(self, broker_order_id: str, *,
                     new_lots: Decimal | None = None,
                     new_price: Decimal | None = None) -> ExecutionResult:
        self._require_connected()
        import time as _time
        start = _time.monotonic()

        request = {
            "action": mt5.TRADE_ACTION_MODIFY,
            "order": int(broker_order_id),
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        if new_lots is not None:
            request["volume"] = float(new_lots)
        if new_price is not None:
            request["price"] = float(new_price)

        result = mt5.order_send(request)
        broker_latency = int((_time.monotonic() - start) * 1000)

        if result is None:
            raise ConnectionLostError(f"order_send(modify) returned None: {mt5.last_error()}")

        if result.retcode != 10009:
            raise OrderRejectedError(
                f"MT5 modify retcode={result.retcode} comment={result.comment}",
                {"retcode": result.retcode})

        return ExecutionResult(
            broker_order_id=broker_order_id,
            status="modified",
            fill_price=Decimal(str(result.price)) if result.price else None,
            filled_lots=Decimal(str(result.volume)) if result.volume else Decimal("0"),
            requested_lots=Decimal(str(new_lots)) if new_lots else Decimal("0"),
            server_side_latency_ms=3,
            broker_latency_ms=broker_latency,
            slippage_bps=None,
            timestamp=datetime.now(timezone.utc),
            is_reversible=True,
        )

    def cancel_order(self, broker_order_id: str) -> ExecutionResult:
        self._require_connected()
        import time as _time
        start = _time.monotonic()

        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": int(broker_order_id),
        }
        result = mt5.order_send(request)
        broker_latency = int((_time.monotonic() - start) * 1000)

        if result is None:
            raise ConnectionLostError(f"order_send(cancel) returned None: {mt5.last_error()}")

        if result.retcode != 10009:
            # If the order doesn't exist, MT5 returns an error — treat as already cancelled
            if result.retcode == 10013:  # INVALID
                return ExecutionResult(
                    broker_order_id=broker_order_id, status="cancelled_already",
                    fill_price=None, filled_lots=Decimal("0"), requested_lots=Decimal("0"),
                    server_side_latency_ms=1, broker_latency_ms=1, slippage_bps=None,
                    timestamp=datetime.now(timezone.utc), is_reversible=False,
                )
            raise OrderRejectedError(
                f"MT5 cancel retcode={result.retcode} comment={result.comment}",
                {"retcode": result.retcode})

        return ExecutionResult(
            broker_order_id=broker_order_id, status="cancelled",
            fill_price=None, filled_lots=Decimal("0"), requested_lots=Decimal("0"),
            server_side_latency_ms=2, broker_latency_ms=broker_latency,
            slippage_bps=None,
            timestamp=datetime.now(timezone.utc), is_reversible=False,
        )

    def close_position(self, login: str, position_id: str,
                       lots: Decimal | None = None) -> ExecutionResult:
        self._require_connected()
        import time as _time
        start = _time.monotonic()

        # Get the position to determine side + symbol
        positions = mt5.positions_get(ticket=int(position_id))
        if not positions:
            raise OrderRejectedError(f"position {position_id} not found")
        pos = positions[0]

        # Close by opening an opposite trade
        close_side = "sell" if pos.type == 0 else "buy"  # 0=POSITION_TYPE_BUY
        close_lots = lots or Decimal(str(pos.volume))

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": float(close_lots),
            "type": mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY,
            "position": int(position_id),
            "deviation": 20,
            "magic": int(self.config.get("magic", 234000)),
            "comment": f"close-{position_id}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        # Get current price
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick:
            request["price"] = tick.bid if pos.type == 0 else tick.ask

        result = mt5.order_send(request)
        broker_latency = int((_time.monotonic() - start) * 1000)

        if result is None:
            raise ConnectionLostError(f"close position order_send returned None: {mt5.last_error()}")

        if result.retcode != 10009:
            raise OrderRejectedError(
                f"MT5 close position retcode={result.retcode} comment={result.comment}",
                {"retcode": result.retcode, "position_id": position_id})

        return ExecutionResult(
            broker_order_id=str(result.order),
            status="filled",
            fill_price=Decimal(str(result.price)) if result.price else None,
            filled_lots=Decimal(str(result.volume)),
            requested_lots=close_lots,
            server_side_latency_ms=5,
            broker_latency_ms=broker_latency,
            slippage_bps=None,
            timestamp=datetime.now(timezone.utc),
            is_reversible=False,  # closing is irreversible
        )

    # ---- reconciliation ----
    def reconcile(self, login: str) -> dict:
        self._require_connected()
        # Fetch live positions + orders from broker
        live_positions = mt5.positions_get() or []
        live_orders = mt5.orders_get() or []
        account = mt5.account_info()

        return {
            "discrepancies": [],  # platform-level reconciliation compares against internal state
            "last_reconciled_at": datetime.now(timezone.utc).isoformat(),
            "broker_position_count": len(live_positions),
            "broker_order_count": len(live_orders),
            "broker_balance": float(account.balance) if account else None,
            "broker_equity": float(account.equity) if account else None,
            "adapter": "mt5",
            "is_live": True,
        }

    # ---- error normalization ----
    def normalize_error(self, raw_exception: Exception) -> ExecutionAdapterError:
        if isinstance(raw_exception, ExecutionAdapterError):
            return raw_exception
        msg = str(raw_exception).lower()
        if "auth" in msg or "invalid_account" in msg:
            return ExecutionAdapterError("AUTH_FAILED", str(raw_exception))
        if "no_money" in msg or "margin" in msg:
            return ExecutionAdapterError("INSUFFICIENT_MARGIN", str(raw_exception))
        if "market_closed" in msg or "trade_disabled" in msg:
            return ExecutionAdapterError("MARKET_CLOSED", str(raw_exception))
        if "connection" in msg or "timeout" in msg or "not_connected" in msg:
            return ExecutionAdapterError("CONNECTION_LOST", str(raw_exception))
        if "retcode" in msg:
            return ExecutionAdapterError("ORDER_REJECTED", str(raw_exception))
        return ExecutionAdapterError("UNKNOWN", f"MT5 raw error: {raw_exception}")

    # ---- helpers ----
    def _normalize_volume(self, lots: Decimal, step: Decimal) -> Decimal:
        """Round volume down to the symbol's volume step."""
        if step <= 0:
            return lots
        steps = int(lots / step)
        return Decimal(str(steps)) * step

    def _map_order_type(self, side: str, order_type: str) -> int:
        """Map our side+order_type to MT5's ORDER_TYPE_* constant."""
        if not _MT5_AVAILABLE:
            raise NotImplementedError_("_map_order_type", BLOCKER_NO_SDK)
        if order_type == "limit":
            return mt5.ORDER_TYPE_BUY_LIMIT if side == "buy" else mt5.ORDER_TYPE_SELL_LIMIT
        if order_type == "stop":
            return mt5.ORDER_TYPE_BUY_STOP if side == "buy" else mt5.ORDER_TYPE_SELL_STOP
        # Market order (default)
        return mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL

    def _map_retcode(self, retcode: int) -> tuple[str, Optional[str]]:
        """Map an MT5 retcode to (status, canonical_error_code)."""
        return _MT5_RETCODE_MAP.get(retcode, ("rejected", "UNKNOWN"))
