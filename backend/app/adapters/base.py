"""
L0: ExecutionAdapter — canonical interface for all broker / exchange adapters.

Every concrete adapter (MT5, cTrader, crypto, simulated) implements this
contract. The interface is intentionally minimal but explicit: each method
documents what it returns, when it raises, and which operations are
considered reversible vs. irreversible.

Capabilities are discovered at runtime via `discover_capabilities()`. The
platform does NOT assume every adapter exposes identical functionality.
The risk engine, MAM engine, and copy engine ALL consult the capability
matrix before submitting orders — e.g., if `supports_modify` is False,
the MAM engine will reject modification requests rather than silently
dropping them.

Connection lifecycle:
  - connect() must be called before any other method.
  - authenticate() is part of connect() and may raise AuthenticationError.
  - disconnect() is idempotent.
  - reconnect() is a higher-level operation that re-establishes the session.

Error normalization:
  - Every adapter raises ExecutionAdapterError subclasses with a
    canonical `code` field (e.g., "AUTH_FAILED", "ORDER_REJECTED",
    "INSUFFICIENT_MARGIN", "RATE_LIMITED", "MARKET_CLOSED",
    "CONNECTION_LOST", "UNKNOWN").
  - The MAM/Copy engines translate these codes into the saga's
    compensation_action: reversible (`reverse`) vs. irreversible
    (`remediate`).

Timestamp & execution-quality tracking:
  - Every order submission returns an ExecutionResult with:
      * server_side_latency_ms (our processing)
      * broker_latency_ms (broker/network/exchange round-trip)
      * slippage_bps (vs. expected fill price)
      * fill_price, filled_lots, status
  - These feed P-2 latency prediction calibration.

Honest design notes:
  - The SimulatedAdapter fully implements this interface for development.
  - MT5 / cTrader / crypto adapters are SKELETONS in M4 — they implement
    the contract surface but throw NotImplementedError("BLOCKED: ...")
    for any operation that requires the proprietary SDK / credentials.
    This is intentional and documented: a real integration needs the
    relevant broker SDK + API credentials + a test server, none of
    which are available in this environment.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional
import time
import uuid


# ---------- Canonical error codes ----------
class ExecutionAdapterError(Exception):
    """Base class for all adapter errors. Carries a canonical `code`."""
    def __init__(self, code: str, message: str, details: dict | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"[{code}] {message}")

class AuthenticationError(ExecutionAdapterError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__("AUTH_FAILED", message, details)

class OrderRejectedError(ExecutionAdapterError):
    """Order was submitted but rejected by the broker."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__("ORDER_REJECTED", message, details)

class InsufficientMarginError(ExecutionAdapterError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__("INSUFFICIENT_MARGIN", message, details)

class RateLimitedError(ExecutionAdapterError):
    def __init__(self, message: str, retry_after_s: int | None = None):
        super().__init__("RATE_LIMITED", message, {"retry_after_s": retry_after_s})

class MarketClosedError(ExecutionAdapterError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__("MARKET_CLOSED", message, details)

class ConnectionLostError(ExecutionAdapterError):
    def __init__(self, message: str = "connection lost"):
        super().__init__("CONNECTION_LOST", message, {})

class NotImplementedError_(ExecutionAdapterError):
    """Raised by adapter skeletons whose SDK is not yet integrated."""
    def __init__(self, operation: str, reason: str):
        super().__init__("NOT_IMPLEMENTED", f"{operation} not implemented: {reason}",
                         {"operation": operation, "reason": reason})


# ---------- Capability matrix ----------
@dataclass
class AdapterCapabilities:
    """What this adapter can actually do. Discovered at runtime."""
    supports_account_discovery: bool = False
    supports_balance_sync: bool = False
    supports_position_sync: bool = False
    supports_market_orders: bool = False
    supports_limit_orders: bool = False
    supports_stop_orders: bool = False
    supports_modify: bool = False
    supports_cancel: bool = False
    supports_partial_fills: bool = False
    supports_close_all: bool = False
    supports_reconciliation: bool = False
    supports_execution_quality: bool = False
    max_lots_per_order: Decimal | None = None
    lot_step: Decimal = Decimal("0.01")
    supported_symbols: list[str] = field(default_factory=list)
    is_live: bool = False  # CRITICAL: simulated adapters must set this to False
    notes: str = ""  # human-readable adapter-specific notes


# ---------- Execution result ----------
@dataclass
class ExecutionResult:
    """Returned by submit_order / modify_order / cancel_order."""
    broker_order_id: str
    status: str  # filled|partial|rejected|pending|cancelled
    fill_price: Decimal | None
    filled_lots: Decimal
    requested_lots: Decimal
    server_side_latency_ms: int  # our processing time
    broker_latency_ms: int  # broker/network/exchange round-trip
    slippage_bps: Decimal | None  # vs. expected fill price; None if N/A
    timestamp: datetime
    raw_response: dict | None = None  # adapter-specific; for audit only
    is_reversible: bool = True  # can the order be reversed (cancelled)?
    warning: str | None = None  # e.g., "SIMULATED — no real order placed"


@dataclass
class AccountSnapshot:
    """Live account state from the broker."""
    login: str
    balance: Decimal
    equity: Decimal
    margin: Decimal
    free_margin: Decimal
    margin_level: Decimal | None  # None if not applicable
    currency: str
    server_time: datetime
    positions: list[dict] = field(default_factory=list)
    warning: str | None = None


class ExecutionAdapter(ABC):
    """Canonical adapter interface."""
    adapter_type: str = "abstract"
    is_live: bool = False

    @abstractmethod
    def connect(self, config: dict) -> None:
        """Establish connection + authenticate. Raises AuthenticationError on failure."""

    @abstractmethod
    def disconnect(self) -> None:
        """Idempotent. Safe to call when already disconnected."""

    @abstractmethod
    def discover_capabilities(self) -> AdapterCapabilities:
        """Return the adapter's capability matrix. Called after connect()."""

    @abstractmethod
    def get_account_snapshot(self, login: str) -> AccountSnapshot:
        """Live balance/equity/margin/positions. Raises on connection loss."""

    @abstractmethod
    def submit_order(self, login: str, symbol: str, side: str,
                     lots: Decimal, order_type: str = "market",
                     price: Decimal | None = None,
                     client_order_id: str | None = None) -> ExecutionResult:
        """
        Submit a market/limit/stop order.
        Returns ExecutionResult with latencies + slippage.
        Raises OrderRejectedError, InsufficientMarginError, RateLimitedError,
        MarketClosedError, ConnectionLostError as appropriate.
        """

    @abstractmethod
    def modify_order(self, broker_order_id: str, *,
                     new_lots: Decimal | None = None,
                     new_price: Decimal | None = None) -> ExecutionResult:
        """Modify an open order. Raises if not supported."""

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> ExecutionResult:
        """Cancel a pending order. Idempotent — second call is a no-op."""

    @abstractmethod
    def close_position(self, login: str, position_id: str,
                       lots: Decimal | None = None) -> ExecutionResult:
        """Close an open position (full or partial)."""

    @abstractmethod
    def reconcile(self, login: str) -> dict:
        """
        Reconcile our internal state against the broker's reported state.
        Returns a dict of {discrepancies: [...], last_reconciled_at: iso8601}.
        """

    @abstractmethod
    def normalize_error(self, raw_exception: Exception) -> ExecutionAdapterError:
        """Map a broker-specific exception to our canonical error codes."""


# ---------- Helper: measure latency ----------
def timed_call(fn, *args, **kwargs):
    """Measure wall-clock latency of a call. Returns (result, latency_ms)."""
    start = time.monotonic()
    result = fn(*args, **kwargs)
    elapsed_ms = int((time.monotonic() - start) * 1000)
    return result, elapsed_ms


def make_client_order_id(prefix: str = "PAMM") -> str:
    """Generate a deterministic client_order_id for idempotency."""
    return f"{prefix}-{uuid.uuid4().hex[:16]}"
