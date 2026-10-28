"""Adapter registry + factory."""
from .base import ExecutionAdapter
from .simulated import SimulatedAdapter
from .mt5 import MT5Adapter
from .ctrader import CTraderAdapter
from .crypto import CryptoAdapter

REGISTRY: dict[str, type[ExecutionAdapter]] = {
    "simulated": SimulatedAdapter,
    "mt5": MT5Adapter,
    "ctrader": CTraderAdapter,
    "crypto": CryptoAdapter,
}

def get_adapter(adapter_type: str, config: dict | None = None) -> ExecutionAdapter:
    cls = REGISTRY.get(adapter_type)
    if not cls:
        raise ValueError(f"unknown adapter type: {adapter_type}")
    return cls(config)

def list_adapters() -> list[dict]:
    """Return adapter metadata for the management UI."""
    out = []
    for t, cls in REGISTRY.items():
        instance = cls()
        caps = instance.discover_capabilities()
        out.append({
            "type": t,
            "is_live": caps.is_live,
            "blocked": not caps.is_live and t != "simulated",
            "notes": caps.notes,
            "supports_market_orders": caps.supports_market_orders,
            "supports_modify": caps.supports_modify,
            "supports_partial_fills": caps.supports_partial_fills,
            "supports_reconciliation": caps.supports_reconciliation,
            "supports_execution_quality": caps.supports_execution_quality,
            "max_lots_per_order": str(caps.max_lots_per_order) if caps.max_lots_per_order else None,
            "lot_step": str(caps.lot_step),
        })
    return out
