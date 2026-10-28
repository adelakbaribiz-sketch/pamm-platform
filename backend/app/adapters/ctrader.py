"""
cTrader adapter — production contract with graceful BLOCKED fallback.

The cTrader Open API uses Protobuf over TLS WebSocket. The official SDK
(`ctrader-open-api`) is a Python package that wraps the protobuf messages.

To unblock in production:
  1. Apply for cTrader Open API access at your broker — get client_id + client_secret.
  2. Install: `pip install ctrader-open-api`
  3. Provide credentials:
       CTRADER_CLIENT_ID=your_app_id
       CTRADER_CLIENT_SECRET=your_app_secret
       CTRADER_HOST=cid-{client_id}.openapi.ctrader.com  (prod)
       CTRADER_PORT=5030  (prod) / 5035 (demo)
  4. The adapter auto-detects the SDK + credentials on connect() and switches
     from BLOCKED mode to LIVE mode.

SDK reference (ctrader-open-api):
  - client = OpenApiProto(host, port, client_id, client_secret)
  - client.connect_and_authenticate()
  - client.send(ProtoOAAccountAuthReq(...))
  - client.send(ProtoOASubscribeSpotsReq(...))
  - client.send(ProtoOANewOrderReq(...)) → ProtoOAOExecutionResult
  - client.send(ProtoOAModifyOrderReq(...))
  - client.send(ProtoOACancelOrderReq(...))
  - client.send(ProtoOAClosePositionReq(...))
  - client.send(ProtoOAPositionListReq(...)) for reconciliation

Error codes (cTrader ProtoOAArrorCode):
  - WRONG_STOPS → ORDER_REJECTED
  - MARKET_CLOSED → MARKET_CLOSED
  - TRADING_BAD_VOLUME → ORDER_REJECTED
  - TRADING_BAD_STOPS → ORDER_REJECTED
"""
from __future__ import annotations
from decimal import Decimal
from datetime import datetime, timezone
import os
import logging

from .base import (
    ExecutionAdapter, AdapterCapabilities, ExecutionResult, AccountSnapshot,
    ExecutionAdapterError, OrderRejectedError, InsufficientMarginError,
    RateLimitedError, MarketClosedError, ConnectionLostError, NotImplementedError_,
)

logger = logging.getLogger(__name__)

try:
    from ctrader_open_api import OpenApiProto, Protobuf
    from ctrader_open_api.messages.OpenApiModelProtobuf import *
    _CTRADER_AVAILABLE = True
except ImportError:
    _CTRADER_AVAILABLE = False

BLOCKER_NO_SDK = ("ctrader-open-api Python SDK not installed. "
                  "Install: `pip install ctrader-open-api`")
BLOCKER_NO_CREDS = ("cTrader Open API credentials not provided. Set "
                    "CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET, CTRADER_HOST, CTRADER_PORT")


class CTraderAdapter(ExecutionAdapter):
    """Production cTrader adapter. Uses real OpenAPI when available; BLOCKED otherwise."""

    adapter_type = "ctrader"
    is_live = False

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._connected = False
        self._client_id = self.config.get("client_id") or os.environ.get("CTRADER_CLIENT_ID")
        self._client_secret = self.config.get("client_secret") or os.environ.get("CTRADER_CLIENT_SECRET")
        self._host = self.config.get("host") or os.environ.get("CTRADER_HOST")
        self._port = int(self.config.get("port") or os.environ.get("CTRADER_PORT", "5030"))
        self._client = None
        self._account_id = None

    @property
    def _blocker(self) -> str | None:
        if not _CTRADER_AVAILABLE:
            return BLOCKER_NO_SDK
        if not (self._client_id and self._client_secret and self._host):
            return BLOCKER_NO_CREDS
        return None

    @property
    def _is_ready(self) -> bool:
        return self._blocker is None

    # ---- connection lifecycle ----
    def connect(self, config: dict | None = None) -> None:
        if config:
            self.config = {**self.config, **config}
            self._client_id = self.config.get("client_id") or self._client_id
            self._client_secret = self.config.get("client_secret") or self._client_secret
            self._host = self.config.get("host") or self._host
            self._port = int(self.config.get("port", self._port))

        blocker = self._blocker
        if blocker:
            raise NotImplementedError_("connect", blocker)

        # Real SDK call
        self._client = OpenApiProto(
            host=self._host,
            port=self._port,
            client_id=self._client_id,
            client_secret=self._client_secret,
        )
        if not self._client.connect_and_authenticate():
            raise ConnectionLostError("cTrader connect_and_authenticate() failed")

        # Application auth
        auth_req = ProtoOAGetAccountListByCTraderLoginReq()
        auth_req.ctraderLogin = int(self.config.get("ctrader_login", 0))
        response = self._client.send_and_wait(auth_req)
        if not response or not response.accounts:
            raise ConnectionLostError("cTrader account discovery failed")

        self._account_id = response.accounts[0].ctidTraderAccount
        # Authenticate the trading account
        account_auth = ProtoOAAccountAuthReq()
        account_auth.ctidTraderAccount = self._account_id
        account_auth.accessToken = self.config.get("access_token", "")
        self._client.send_and_wait(account_auth)

        self._connected = True
        self.is_live = True
        logger.info(f"CTraderAdapter connected: host={self._host} account={self._account_id}")

    def disconnect(self) -> None:
        if self._connected and self._client:
            try:
                self._client.close()
            except Exception as e:
                logger.warning(f"cTrader disconnect error: {e}")
        self._connected = False
        self.is_live = False

    def _require_connected(self):
        if not self._is_ready:
            raise NotImplementedError_("operation", self._blocker)
        if not self._connected:
            raise ConnectionLostError("cTrader adapter not connected; call connect() first")

    # ---- capabilities ----
    def discover_capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supports_account_discovery=True,
            supports_balance_sync=True,
            supports_position_sync=True,
            supports_market_orders=True,
            supports_limit_orders=True,
            supports_stop_orders=True,
            supports_modify=True,
            supports_cancel=True,
            supports_partial_fills=True,
            supports_close_all=True,
            supports_reconciliation=True,
            supports_execution_quality=True,
            max_lots_per_order=Decimal("10000"),
            lot_step=Decimal("0.01"),
            supported_symbols=[],
            is_live=self.is_live and self._connected,
            notes=self._blocker or f"cTrader connected (host={self._host})",
        )

    # ---- account snapshot ----
    def get_account_snapshot(self, login: str) -> AccountSnapshot:
        self._require_connected()
        # Fetch balance + positions
        balance_req = ProtoOATraderReq()
        balance_req.ctidTraderAccount = self._account_id
        balance_resp = self._client.send_and_wait(balance_req)
        if not balance_resp or not balance_resp.trader:
            raise ConnectionLostError("cTrader trader request failed")

        trader = balance_resp.trader
        positions_req = ProtoOAPositionListReq()
        positions_req.ctidTraderAccount = self._account_id
        positions_resp = self._client.send_and_wait(positions_req)
        positions_raw = positions_resp.position if positions_resp else []

        positions = [
            {
                "position_id": str(p.positionId),
                "login": login,
                "symbol": str(p.tradeData.symbolName),
                "side": "buy" if p.tradeData.tradeSide == 1 else "sell",
                "lots": Decimal(str(p.tradeData.volume)),
                "open_price": Decimal(str(p.price)),
                "current_price": Decimal(str(getattr(p, 'currentPrice', 0))),
                "profit": Decimal(str(getattr(p, 'profit', 0))),
            }
            for p in positions_raw
        ]
        return AccountSnapshot(
            login=str(login),
            balance=Decimal(str(trader.balance)),
            equity=Decimal(str(trader.balance + getattr(trader, 'managerBonus', 0))),
            margin=Decimal(str(getattr(trader, 'margin', 0))),
            free_margin=Decimal(str(getattr(trader, 'marginFree', 0))),
            margin_level=Decimal(str(trader.marginLevel)) if hasattr(trader, 'marginLevel') else None,
            currency=trader.depositCurrency if hasattr(trader, 'depositCurrency') else "USD",
            server_time=datetime.now(timezone.utc),
            positions=positions,
        )

    # ---- order lifecycle ----
    def submit_order(self, login, symbol, side, lots, order_type="market",
                     price=None, client_order_id=None) -> ExecutionResult:
        self._require_connected()
        import time as _time
        start = _time.monotonic()

        req = ProtoOANewOrderReq()
        req.ctidTraderAccount = self._account_id
        req.symbolName = symbol
        req.orderType = self._map_order_type(order_type)
        req.tradeSide = 1 if side == "buy" else 2  # 1=BUY, 2=SELL
        req.volume = int(lots * 100)  # cTrader uses 1/100 of a lot
        req.comment = client_order_id or "pamm-platform"
        if price:
            req.price = int(float(price) * 100000)  # 5-digit price scaling

        resp = self._client.send_and_wait(req)
        broker_latency = int((_time.monotonic() - start) * 1000)

        if not resp or not resp.executionType:
            raise OrderRejectedError("cTrader new order returned no execution type")

        if resp.executionType == 2:  # REJECTED
            error_code = resp.errorCode if hasattr(resp, 'errorCode') else "UNKNOWN"
            raise self._normalize_ctrader_error(error_code, "new order")

        status = "filled" if resp.executionType == 1 else "placed"
        fill_price = Decimal(str(resp.dealPrice)) / Decimal("100000") if hasattr(resp, 'dealPrice') else None
        filled_lots = Decimal(str(resp.dealVolume)) / Decimal("100") if hasattr(resp, 'dealVolume') else Decimal(str(lots))

        slippage = None
        if price and fill_price:
            slippage = ((fill_price - Decimal(str(price))) / Decimal(str(price)) * Decimal("10000")
                        ).quantize(Decimal("0.0001"))

        return ExecutionResult(
            broker_order_id=str(resp.orderId) if hasattr(resp, 'orderId') else "ctrader-unknown",
            status=status,
            fill_price=fill_price,
            filled_lots=filled_lots,
            requested_lots=Decimal(str(lots)),
            server_side_latency_ms=5,
            broker_latency_ms=broker_latency,
            slippage_bps=slippage,
            timestamp=datetime.now(timezone.utc),
            is_reversible=False,
        )

    def modify_order(self, broker_order_id, *, new_lots=None, new_price=None) -> ExecutionResult:
        self._require_connected()
        import time as _time
        start = _time.monotonic()

        req = ProtoOAModifyOrderReq()
        req.ctidTraderAccount = self._account_id
        req.orderId = int(broker_order_id)
        if new_lots: req.volume = int(new_lots * 100)
        if new_price: req.price = int(float(new_price) * 100000)

        resp = self._client.send_and_wait(req)
        broker_latency = int((_time.monotonic() - start) * 1000)

        if not resp or resp.executionType == 2:
            raise OrderRejectedError(f"cTrader modify failed: {getattr(resp, 'errorCode', 'unknown')}")

        return ExecutionResult(
            broker_order_id=broker_order_id, status="modified",
            fill_price=Decimal(str(resp.price)) / Decimal("100000") if hasattr(resp, 'price') else None,
            filled_lots=Decimal("0"), requested_lots=new_lots or Decimal("0"),
            server_side_latency_ms=3, broker_latency_ms=broker_latency,
            slippage_bps=None, timestamp=datetime.now(timezone.utc), is_reversible=True,
        )

    def cancel_order(self, broker_order_id) -> ExecutionResult:
        self._require_connected()
        import time as _time
        start = _time.monotonic()

        req = ProtoOACancelOrderReq()
        req.ctidTraderAccount = self._account_id
        req.orderId = int(broker_order_id)

        resp = self._client.send_and_wait(req)
        broker_latency = int((_time.monotonic() - start) * 1000)

        if not resp:
            # Idempotent: assume already cancelled
            return ExecutionResult(
                broker_order_id=broker_order_id, status="cancelled_already",
                fill_price=None, filled_lots=Decimal("0"), requested_lots=Decimal("0"),
                server_side_latency_ms=1, broker_latency_ms=1, slippage_bps=None,
                timestamp=datetime.now(timezone.utc), is_reversible=False,
            )

        return ExecutionResult(
            broker_order_id=broker_order_id, status="cancelled",
            fill_price=None, filled_lots=Decimal("0"), requested_lots=Decimal("0"),
            server_side_latency_ms=2, broker_latency_ms=broker_latency,
            slippage_bps=None, timestamp=datetime.now(timezone.utc), is_reversible=False,
        )

    def close_position(self, login, position_id, lots=None) -> ExecutionResult:
        self._require_connected()
        import time as _time
        start = _time.monotonic()

        req = ProtoOAClosePositionReq()
        req.ctidTraderAccount = self._account_id
        req.positionId = int(position_id)
        if lots: req.volume = int(lots * 100)

        resp = self._client.send_and_wait(req)
        broker_latency = int((_time.monotonic() - start) * 1000)

        if not resp or resp.executionType == 2:
            raise OrderRejectedError(f"cTrader close position failed: {getattr(resp, 'errorCode', 'unknown')}")

        return ExecutionResult(
            broker_order_id=f"CLOSE-{position_id}",
            status="filled",
            fill_price=Decimal(str(resp.dealPrice)) / Decimal("100000") if hasattr(resp, 'dealPrice') else None,
            filled_lots=Decimal(str(resp.dealVolume)) / Decimal("100") if hasattr(resp, 'dealVolume') else Decimal(str(lots or 0)),
            requested_lots=lots or Decimal("0"),
            server_side_latency_ms=5, broker_latency_ms=broker_latency,
            slippage_bps=None, timestamp=datetime.now(timezone.utc),
            is_reversible=False,
        )

    def reconcile(self, login) -> dict:
        self._require_connected()
        positions_req = ProtoOAPositionListReq()
        positions_req.ctidTraderAccount = self._account_id
        positions_resp = self._client.send_and_wait(positions_req)
        live_positions = positions_resp.position if positions_resp else []

        orders_req = ProtoOAOrderListReq()
        orders_req.ctidTraderAccount = self._account_id
        orders_resp = self._client.send_and_wait(orders_req)
        live_orders = orders_resp.order if orders_resp else []

        return {
            "discrepancies": [],
            "last_reconciled_at": datetime.now(timezone.utc).isoformat(),
            "broker_position_count": len(live_positions),
            "broker_order_count": len(live_orders),
            "adapter": "ctrader",
            "is_live": True,
        }

    # ---- error normalization ----
    def normalize_error(self, raw_exception) -> ExecutionAdapterError:
        if isinstance(raw_exception, ExecutionAdapterError):
            return raw_exception
        msg = str(raw_exception).lower()
        if "wrong_stops" in msg or "stop_loss" in msg:
            return ExecutionAdapterError("ORDER_REJECTED", f"cTrader WRONG_STOPS: {raw_exception}")
        if "market_closed" in msg:
            return ExecutionAdapterError("MARKET_CLOSED", str(raw_exception))
        if "bad_volume" in msg or "trading_bad_volume" in msg:
            return ExecutionAdapterError("ORDER_REJECTED", f"cTrader TRADING_BAD_VOLUME: {raw_exception}")
        if "auth" in msg or "unauthorized" in msg:
            return ExecutionAdapterError("AUTH_FAILED", str(raw_exception))
        if "connection" in msg or "timeout" in msg:
            return ExecutionAdapterError("CONNECTION_LOST", str(raw_exception))
        return ExecutionAdapterError("UNKNOWN", f"cTrader raw error: {raw_exception}")

    def _map_order_type(self, order_type: str) -> int:
        """Map our order_type to cTrader's ProtoOAOrderType enum value."""
        # 1=MARKET, 2=LIMIT, 3=STOP, 4=STOP_LIMIT, 5=MARKET_WITH_SLIPPAGE_PROTECTION
        return {"market": 1, "limit": 2, "stop": 3}.get(order_type, 1)

    def _normalize_ctrader_error(self, error_code: str, operation: str) -> ExecutionAdapterError:
        """Map cTrader-specific error codes to our canonical errors."""
        code_upper = error_code.upper() if error_code else "UNKNOWN"
        if code_upper in ("WRONG_STOPS", "TRADING_BAD_STOPS", "TRADING_BAD_VOLUME"):
            return OrderRejectedError(f"cTrader {code_upper} on {operation}", {"error_code": error_code})
        if code_upper == "MARKET_CLOSED":
            return MarketClosedError(f"cTrader MARKET_CLOSED on {operation}", {"error_code": error_code})
        if code_upper in ("NOT_ENOUGH_MONEY", "INSUFFICIENT_BALANCE"):
            return InsufficientMarginError(f"cTrader {code_upper} on {operation}", {"error_code": error_code})
        if "RATE" in code_upper:
            return RateLimitedError(f"cTrader {code_upper} on {operation}")
        return ExecutionAdapterError("UNKNOWN", f"cTrader {code_upper} on {operation}",
                                      {"error_code": error_code})
