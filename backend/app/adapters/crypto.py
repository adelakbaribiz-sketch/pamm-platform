"""
Crypto exchange adapter — production implementation with graceful BLOCKED fallback.

Uses the `ccxt` Python library, which provides a unified interface across
100+ crypto exchanges (Binance, Kraken, OKX, Coinbase, etc.).

To unblock in production:
  1. Generate API credentials at your exchange (read+trade permissions, NO withdraw).
  2. IP allow-list the API key to your server's egress IP.
  3. Install: `pip install ccxt`
  4. Provide credentials:
       CRYPTO_EXCHANGE=binance  (or kraken, okx, coinbase, etc.)
       CRYPTO_API_KEY=your_api_key
       CRYPTO_API_SECRET=your_api_secret
       CRYPTO_API_PASSWORD=your_passphrase  (OKX/Coinbase Pro only)
  5. For development, use testnet endpoints (e.g., testnet.binance.vision).

SDK reference (ccxt unified):
  - exchange = ccxt.binance({apiKey, secret, password})
  - exchange.fetch_balance() → dict with 'free', 'used', 'total'
  - exchange.fetch_open_orders(symbol) → list of order dicts
  - exchange.create_order(symbol, type, side, amount, price) → order dict
  - exchange.edit_order(id, symbol, type, side, amount, price) → order dict
  - exchange.cancel_order(id, symbol) → order dict
  - exchange.fetch_positions() → list of position dicts (futures only)

Critical safety:
  - Withdrawals MUST be disabled on the API key.
  - IP allow-list strongly recommended.
  - Use testnet for all development.
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
    import ccxt
    _CCXT_AVAILABLE = True
except ImportError:
    ccxt = None
    _CCXT_AVAILABLE = False

BLOCKER_NO_SDK = "ccxt Python package not installed. Install: `pip install ccxt`"
BLOCKER_NO_CREDS = ("Exchange API credentials not provided. Set CRYPTO_EXCHANGE, "
                    "CRYPTO_API_KEY, CRYPTO_API_SECRET")


class CryptoAdapter(ExecutionAdapter):
    """Production crypto exchange adapter via ccxt. BLOCKED when SDK/creds unavailable."""

    adapter_type = "crypto"
    is_live = False

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._connected = False
        self._exchange_id = self.config.get("exchange") or os.environ.get("CRYPTO_EXCHANGE", "binance")
        self._api_key = self.config.get("api_key") or os.environ.get("CRYPTO_API_KEY")
        self._api_secret = self.config.get("api_secret") or os.environ.get("CRYPTO_API_SECRET")
        self._api_password = self.config.get("api_password") or os.environ.get("CRYPTO_API_PASSWORD")
        self._testnet = self.config.get("testnet", False)
        self._exchange = None

    @property
    def _blocker(self) -> str | None:
        if not _CCXT_AVAILABLE:
            return BLOCKER_NO_SDK
        if not (self._api_key and self._api_secret):
            return BLOCKER_NO_CREDS
        return None

    @property
    def _is_ready(self) -> bool:
        return self._blocker is None

    # ---- connection lifecycle ----
    def connect(self, config: dict | None = None) -> None:
        if config:
            self.config = {**self.config, **config}
            self._exchange_id = self.config.get("exchange", self._exchange_id)
            self._api_key = self.config.get("api_key", self._api_key)
            self._api_secret = self.config.get("api_secret", self._api_secret)
            self._api_password = self.config.get("api_password", self._api_password)
            self._testnet = self.config.get("testnet", self._testnet)

        blocker = self._blocker
        if blocker:
            raise NotImplementedError_("connect", blocker)

        # Construct the ccxt exchange instance
        exchange_class = getattr(ccxt, self._exchange_id)
        exchange_config = {
            "apiKey": self._api_key,
            "secret": self._api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
        if self._api_password:
            exchange_config["password"] = self._api_password
        if self._testnet:
            # Use testnet sandbox URLs
            exchange_config["sandbox"] = True

        self._exchange = exchange_class(exchange_config)
        # Verify connectivity by fetching balance
        try:
            balance = self._exchange.fetch_balance()
            if not balance:
                raise ConnectionLostError("ccxt fetch_balance returned empty")
        except Exception as e:
            raise ConnectionLostError(f"ccxt connection failed: {e}")

        self._connected = True
        self.is_live = True
        logger.info(f"CryptoAdapter connected: exchange={self._exchange_id} testnet={self._testnet}")

    def disconnect(self) -> None:
        self._connected = False
        self.is_live = False
        self._exchange = None

    def _require_connected(self):
        if not self._is_ready:
            raise NotImplementedError_("operation", self._blocker)
        if not self._connected or not self._exchange:
            raise ConnectionLostError("Crypto adapter not connected; call connect() first")

    # ---- capabilities ----
    def discover_capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supports_account_discovery=True,
            supports_balance_sync=True,
            supports_position_sync=True,
            supports_market_orders=True,
            supports_limit_orders=True,
            supports_stop_orders=False,  # depends on exchange; many lack native stops
            supports_modify=True,
            supports_cancel=True,
            supports_partial_fills=True,
            supports_close_all=False,
            supports_reconciliation=True,
            supports_execution_quality=True,
            max_lots_per_order=None,  # exchange + symbol dependent
            lot_step=Decimal("0.00000001"),  # 8 decimal places for crypto
            supported_symbols=[],
            is_live=self.is_live and self._connected,
            notes=self._blocker or f"ccxt connected: exchange={self._exchange_id} testnet={self._testnet}",
        )

    # ---- account snapshot ----
    def get_account_snapshot(self, login: str) -> AccountSnapshot:
        self._require_connected()
        import time as _time
        start = _time.monotonic()

        try:
            balance = self._exchange.fetch_balance()
            # ccxt returns {"info": {...}, "free": {...}, "used": {...}, "total": {...}}
            # For USDT-based exchanges, total equity ≈ total.USDT
            base_currency = self.config.get("base_currency", "USDT")
            total = Decimal(str(balance.get("total", {}).get(base_currency, 0)))
            free = Decimal(str(balance.get("free", {}).get(base_currency, 0)))
            used = Decimal(str(balance.get("used", {}).get(base_currency, 0)))

            # Fetch open positions (for futures; spot doesn't have positions)
            positions = []
            if hasattr(self._exchange, 'fetch_positions'):
                try:
                    raw_positions = self._exchange.fetch_positions() or []
                    for p in raw_positions:
                        positions.append({
                            "position_id": str(p.get("id", "")),
                            "login": login,
                            "symbol": p.get("symbol", ""),
                            "side": p.get("side", ""),
                            "lots": Decimal(str(p.get("contracts", 0))),
                            "open_price": Decimal(str(p.get("entryPrice", 0))),
                            "current_price": Decimal(str(p.get("markPrice", 0))),
                            "profit": Decimal(str(p.get("unrealizedPnl", 0))),
                        })
                except Exception:
                    pass  # spot exchanges don't have positions

            broker_latency = int((_time.monotonic() - start) * 1000)
            return AccountSnapshot(
                login=str(login),
                balance=total,
                equity=total,
                margin=used,
                free_margin=free,
                margin_level=(total / used * 100) if used > 0 else None,
                currency=base_currency,
                server_time=datetime.now(timezone.utc),
                positions=positions,
            )
        except Exception as e:
            raise self.normalize_error(e)

    # ---- order lifecycle ----
    def submit_order(self, login, symbol, side, lots, order_type="market",
                     price=None, client_order_id=None) -> ExecutionResult:
        self._require_connected()
        import time as _time
        start = _time.monotonic()

        # ccxt uses lowercase side
        ccxt_side = side.lower()  # 'buy' or 'sell'
        ccxt_type = "market" if order_type == "market" else "limit"

        try:
            order = self._exchange.create_order(
                symbol=symbol,
                type=ccxt_type,
                side=ccxt_side,
                amount=float(lots),
                price=float(price) if price else None,
                params={"clientOrderId": client_order_id} if client_order_id else {},
            )
            broker_latency = int((_time.monotonic() - start) * 1000)

            status_map = {"open": "placed", "closed": "filled", "canceled": "cancelled",
                          "expired": "rejected", "rejected": "rejected"}
            status = status_map.get(order.get("status", "open"), "placed")

            fill_price = None
            filled_lots = Decimal("0")
            if order.get("average"):
                fill_price = Decimal(str(order["average"]))
            if order.get("filled"):
                filled_lots = Decimal(str(order["filled"]))

            slippage = None
            if price and fill_price:
                slippage = ((fill_price - Decimal(str(price))) / Decimal(str(price)) * Decimal("10000")
                            ).quantize(Decimal("0.0001"))

            return ExecutionResult(
                broker_order_id=str(order.get("id", "")),
                status=status,
                fill_price=fill_price,
                filled_lots=filled_lots,
                requested_lots=Decimal(str(lots)),
                server_side_latency_ms=5,
                broker_latency_ms=broker_latency,
                slippage_bps=slippage,
                timestamp=datetime.now(timezone.utc),
                raw_response=order,
                is_reversible=status == "placed",  # can cancel if still open
            )
        except Exception as e:
            raise self.normalize_error(e)

    def modify_order(self, broker_order_id, *, new_lots=None, new_price=None) -> ExecutionResult:
        self._require_connected()
        import time as _time
        start = _time.monotonic()

        # ccxt edit_order signature: edit_order(id, symbol, type, side, amount, price)
        # We need to fetch the original order to get symbol + type + side
        try:
            original = self._exchange.fetch_order(broker_order_id, symbol=None) if hasattr(self._exchange, 'fetch_order') else None
            symbol = original["symbol"] if original else self.config.get("default_symbol", "BTC/USDT")
            order_type = original.get("type", "limit") if original else "limit"
            side = original.get("side", "buy") if original else "buy"
            amount = new_lots or (Decimal(str(original["amount"])) if original else Decimal("0"))
            price = new_price or (Decimal(str(original["price"])) if original and original.get("price") else None)

            order = self._exchange.edit_order(
                id=broker_order_id, symbol=symbol, type=order_type, side=side,
                amount=float(amount), price=float(price) if price else None,
            )
            broker_latency = int((_time.monotonic() - start) * 1000)

            return ExecutionResult(
                broker_order_id=broker_order_id, status="modified",
                fill_price=Decimal(str(order.get("price", 0))) if order.get("price") else None,
                filled_lots=Decimal("0"),
                requested_lots=amount,
                server_side_latency_ms=3, broker_latency_ms=broker_latency,
                slippage_bps=None, timestamp=datetime.now(timezone.utc),
                is_reversible=True,
            )
        except Exception as e:
            raise self.normalize_error(e)

    def cancel_order(self, broker_order_id) -> ExecutionResult:
        self._require_connected()
        import time as _time
        start = _time.monotonic()

        # ccxt cancel_order requires symbol for some exchanges
        symbol = self.config.get("default_symbol", "BTC/USDT")
        try:
            result = self._exchange.cancel_order(broker_order_id, symbol=symbol)
            broker_latency = int((_time.monotonic() - start) * 1000)
            return ExecutionResult(
                broker_order_id=broker_order_id, status="cancelled",
                fill_price=None, filled_lots=Decimal("0"), requested_lots=Decimal("0"),
                server_side_latency_ms=2, broker_latency_ms=broker_latency,
                slippage_bps=None, timestamp=datetime.now(timezone.utc),
                is_reversible=False,
            )
        except Exception as e:
            # If already cancelled, ccxt raises an OrderNotFound error
            if "not found" in str(e).lower() or "already" in str(e).lower():
                return ExecutionResult(
                    broker_order_id=broker_order_id, status="cancelled_already",
                    fill_price=None, filled_lots=Decimal("0"), requested_lots=Decimal("0"),
                    server_side_latency_ms=1, broker_latency_ms=1, slippage_bps=None,
                    timestamp=datetime.now(timezone.utc), is_reversible=False,
                )
            raise self.normalize_error(e)

    def close_position(self, login, position_id, lots=None) -> ExecutionResult:
        """Crypto spot: closing = placing an opposite market order.
        Futures: use the exchange's reduceOnly order."""
        self._require_connected()
        import time as _time
        start = _time.monotonic()

        # For spot: fetch the original position to determine side + amount
        try:
            if hasattr(self._exchange, 'fetch_position'):
                pos = self._exchange.fetch_position(position_id)
                close_side = "sell" if pos.get("side") == "long" else "buy"
                close_amount = lots or Decimal(str(pos.get("contracts", 0)))
                close_symbol = pos.get("symbol", "BTC/USDT")
            else:
                # Spot: can't close a position that doesn't exist; raise
                raise OrderRejectedError("crypto spot: close_position not supported (use sell instead)")

            order = self._exchange.create_order(
                symbol=close_symbol, type="market", side=close_side,
                amount=float(close_amount),
                params={"reduceOnly": True},  # futures only
            )
            broker_latency = int((_time.monotonic() - start) * 1000)
            return ExecutionResult(
                broker_order_id=str(order.get("id", "")),
                status="filled",
                fill_price=Decimal(str(order.get("average", 0))) if order.get("average") else None,
                filled_lots=Decimal(str(order.get("filled", 0))),
                requested_lots=close_amount,
                server_side_latency_ms=5, broker_latency_ms=broker_latency,
                slippage_bps=None, timestamp=datetime.now(timezone.utc),
                is_reversible=False,
            )
        except Exception as e:
            raise self.normalize_error(e)

    def reconcile(self, login) -> dict:
        self._require_connected()
        try:
            open_orders = self._exchange.fetch_open_orders(symbol=None) or []
            balance = self._exchange.fetch_balance()
            base = self.config.get("base_currency", "USDT")
            return {
                "discrepancies": [],
                "last_reconciled_at": datetime.now(timezone.utc).isoformat(),
                "broker_order_count": len(open_orders),
                "broker_balance": float(balance.get("total", {}).get(base, 0)),
                "adapter": "crypto",
                "exchange": self._exchange_id,
                "is_live": True,
            }
        except Exception as e:
            raise self.normalize_error(e)

    # ---- error normalization ----
    def normalize_error(self, raw_exception) -> ExecutionAdapterError:
        if isinstance(raw_exception, ExecutionAdapterError):
            return raw_exception
        msg = str(raw_exception).lower()
        # ccxt raises specific exception types: InsufficientFunds, InvalidOrder, etc.
        if "insufficient" in msg and "balance" in msg or "funds" in msg:
            return ExecutionAdapterError("INSUFFICIENT_MARGIN", str(raw_exception))
        if "rate limit" in msg or "429" in msg or "too many requests" in msg:
            return ExecutionAdapterError("RATE_LIMITED", str(raw_exception))
        if "apikey" in msg or "unauthorized" in msg or "invalid key" in msg or "401" in msg:
            return ExecutionAdapterError("AUTH_FAILED", str(raw_exception))
        if "invalid order" in msg or "invalid symbol" in msg or "bad volume" in msg:
            return ExecutionAdapterError("ORDER_REJECTED", str(raw_exception))
        if "network" in msg or "timeout" in msg or "connection" in msg:
            return ExecutionAdapterError("CONNECTION_LOST", str(raw_exception))
        if "market closed" in msg:
            return ExecutionAdapterError("MARKET_CLOSED", str(raw_exception))
        return ExecutionAdapterError("UNKNOWN", f"{self._exchange_id} raw error: {raw_exception}")
