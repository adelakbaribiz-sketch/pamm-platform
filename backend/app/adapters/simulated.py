"""SIMULATED broker adapter — fully implements ExecutionAdapter.

Clearly labeled: is_live=False, every response carries `warning`.
Use ONLY in development. MT5/cTrader/crypto adapters are BLOCKED.
"""
from __future__ import annotations
from decimal import Decimal
from datetime import datetime, timezone
import time
import hashlib
from .base import (
    ExecutionAdapter, AdapterCapabilities, ExecutionResult, AccountSnapshot,
    ExecutionAdapterError, OrderRejectedError, ConnectionLostError,
    NotImplementedError_, timed_call, make_client_order_id,
)


class SimulatedAdapter(ExecutionAdapter):
    adapter_type = "simulated"
    is_live = False

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._equity = Decimal(str(self.config.get("starting_equity", "100000")))
        self._connected = False
        self._orders: dict[str, dict] = {}  # broker_order_id -> order record
        self._positions: dict[str, dict] = {}
        self._next_order_id = 1

    # ---- connection lifecycle ----
    def connect(self, config: dict | None = None) -> None:
        if config: self.config = {**self.config, **config}
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def _require_connected(self):
        if not self._connected:
            raise ConnectionLostError("adapter not connected")

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
            max_lots_per_order=Decimal("100"),
            lot_step=Decimal("0.01"),
            supported_symbols=["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"],
            is_live=False,
            notes="SIMULATED — no real orders placed. Latency is synthetic.",
        )

    # ---- account snapshot ----
    def get_account_snapshot(self, login: str) -> AccountSnapshot:
        self._require_connected()
        return AccountSnapshot(
            login=login,
            balance=self._equity,
            equity=self._equity,
            margin=Decimal("0"),
            free_margin=self._equity,
            margin_level=None,
            currency=self.config.get("currency", "USD"),
            server_time=datetime.now(timezone.utc),
            positions=list(self._positions.values()),
            warning="SIMULATED — not a real broker connection",
        )

    # ---- order lifecycle ----
    def submit_order(self, login: str, symbol: str, side: str,
                     lots: Decimal, order_type: str = "market",
                     price: Decimal | None = None,
                     client_order_id: str | None = None) -> ExecutionResult:
        self._require_connected()
        if side not in ("buy", "sell"):
            raise OrderRejectedError(f"invalid side: {side}")
        if Decimal(lots) <= 0:
            raise OrderRejectedError(f"invalid lots: {lots}")
        if Decimal(lots) > Decimal("100"):
            raise OrderRejectedError(f"lots exceed max: {lots} > 100")

        # Simulated latency: deterministic per order hash
        order_seed = hash((login, symbol, side, str(lots), client_order_id or ""))
        server_lat = 5 + (order_seed % 11)  # 5-15ms
        broker_lat = 20 + (order_seed % 51)  # 20-70ms

        # Simulated fill price
        expected_price = price or Decimal("100")
        slippage_bps = Decimal(str((order_seed % 21) - 10)) / Decimal("10")  # -1.0 to +1.0 bps
        actual_price = expected_price * (Decimal("1") + slippage_bps / Decimal("10000"))

        broker_order_id = f"SIM-{self._next_order_id:08d}"
        self._next_order_id += 1

        result = ExecutionResult(
            broker_order_id=broker_order_id,
            status="filled",
            fill_price=actual_price,
            filled_lots=Decimal(lots),
            requested_lots=Decimal(lots),
            server_side_latency_ms=server_lat,
            broker_latency_ms=broker_lat,
            slippage_bps=slippage_bps,
            timestamp=datetime.now(timezone.utc),
            raw_response={"simulated": True, "client_order_id": client_order_id},
            is_reversible=True,
            warning="SIMULATED — no real order was placed",
        )
        self._orders[broker_order_id] = {
            "login": login, "symbol": symbol, "side": side, "lots": str(lots),
            "type": order_type, "price": str(actual_price), "status": "filled",
            "client_order_id": client_order_id,
        }
        # Open a position too
        position_id = f"POS-{broker_order_id}"
        self._positions[position_id] = {
            "position_id": position_id, "login": login, "symbol": symbol,
            "side": side, "lots": str(lots), "open_price": str(actual_price),
            "broker_order_id": broker_order_id,
        }
        # Adjust equity by simulated PnL impact (none in this simulation)
        return result

    def modify_order(self, broker_order_id: str, *,
                     new_lots: Decimal | None = None,
                     new_price: Decimal | None = None) -> ExecutionResult:
        self._require_connected()
        if broker_order_id not in self._orders:
            raise OrderRejectedError(f"order not found: {broker_order_id}")
        order = self._orders[broker_order_id]
        if new_lots: order["lots"] = str(new_lots)
        if new_price: order["price"] = str(new_price)
        return ExecutionResult(
            broker_order_id=broker_order_id,
            status="modified",
            fill_price=Decimal(order["price"]),
            filled_lots=Decimal(order["lots"]),
            requested_lots=Decimal(order["lots"]),
            server_side_latency_ms=3,
            broker_latency_ms=15,
            slippage_bps=Decimal("0"),
            timestamp=datetime.now(timezone.utc),
            is_reversible=True,
            warning="SIMULATED — modify acknowledged",
        )

    def cancel_order(self, broker_order_id: str) -> ExecutionResult:
        self._require_connected()
        if broker_order_id not in self._orders:
            # Idempotent: second cancel is a no-op
            return ExecutionResult(
                broker_order_id=broker_order_id, status="cancelled_already",
                fill_price=None, filled_lots=Decimal("0"), requested_lots=Decimal("0"),
                server_side_latency_ms=1, broker_latency_ms=1, slippage_bps=None,
                timestamp=datetime.now(timezone.utc), is_reversible=False,
                warning="SIMULATED — order already cancelled",
            )
        # If already cancelled, return cancelled_already
        if self._orders[broker_order_id].get("status") == "cancelled":
            return ExecutionResult(
                broker_order_id=broker_order_id, status="cancelled_already",
                fill_price=None, filled_lots=Decimal("0"), requested_lots=Decimal("0"),
                server_side_latency_ms=1, broker_latency_ms=1, slippage_bps=None,
                timestamp=datetime.now(timezone.utc), is_reversible=False,
                warning="SIMULATED — order already cancelled",
            )
        self._orders[broker_order_id]["status"] = "cancelled"
        return ExecutionResult(
            broker_order_id=broker_order_id, status="cancelled",
            fill_price=None, filled_lots=Decimal("0"), requested_lots=Decimal("0"),
            server_side_latency_ms=2, broker_latency_ms=10, slippage_bps=None,
            timestamp=datetime.now(timezone.utc), is_reversible=False,
            warning="SIMULATED — cancel acknowledged",
        )

    def close_position(self, login: str, position_id: str,
                       lots: Decimal | None = None) -> ExecutionResult:
        self._require_connected()
        if position_id not in self._positions:
            raise OrderRejectedError(f"position not found: {position_id}")
        pos = self._positions[position_id]
        close_lots = lots or Decimal(pos["lots"])
        del self._positions[position_id]
        return ExecutionResult(
            broker_order_id=f"CLOSE-{position_id}",
            status="filled",
            fill_price=Decimal(pos["open_price"]),
            filled_lots=close_lots,
            requested_lots=close_lots,
            server_side_latency_ms=5,
            broker_latency_ms=25,
            slippage_bps=Decimal("0.5"),
            timestamp=datetime.now(timezone.utc),
            is_reversible=False,  # closing is irreversible
            warning="SIMULATED — position closed",
        )

    def reconcile(self, login: str) -> dict:
        self._require_connected()
        # Simulated: no discrepancies
        return {
            "discrepancies": [],
            "last_reconciled_at": datetime.now(timezone.utc).isoformat(),
            "positions_checked": len(self._positions),
            "orders_checked": len(self._orders),
            "adapter": "simulated",
            "is_live": False,
        }

    def normalize_error(self, raw_exception: Exception) -> ExecutionAdapterError:
        if isinstance(raw_exception, ExecutionAdapterError):
            return raw_exception
        msg = str(raw_exception).lower()
        if "auth" in msg: return ExecutionAdapterError("AUTH_FAILED", str(raw_exception))
        if "margin" in msg: return ExecutionAdapterError("INSUFFICIENT_MARGIN", str(raw_exception))
        if "rate" in msg and "limit" in msg: return ExecutionAdapterError("RATE_LIMITED", str(raw_exception))
        if "closed" in msg or "holiday" in msg: return ExecutionAdapterError("MARKET_CLOSED", str(raw_exception))
        if "connection" in msg or "timeout" in msg: return ExecutionAdapterError("CONNECTION_LOST", str(raw_exception))
        return ExecutionAdapterError("UNKNOWN", str(raw_exception))

    # ---- Backwards-compat with the M1 routers that called apply_pnl + get_account_snapshot ----
    def apply_pnl(self, pnl: Decimal) -> Decimal:
        """Legacy method used by /api/simulate-pnl. Apply synthetic PnL to the simulated account."""
        self._equity += Decimal(str(pnl))
        return self._equity
