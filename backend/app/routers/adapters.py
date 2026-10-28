"""Adapter management router — list adapters + their capabilities + blocked status."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..auth import get_principal, Principal, require_roles
from ..db import get_db
from ..adapters.registry import list_adapters, get_adapter
from ..adapters.base import ExecutionAdapterError

router = APIRouter()

@router.get("/adapters")
def list_all_adapters(p: Annotated[Principal, Depends(get_principal)]):
    """List all registered adapters with their capability matrices + blocked status."""
    return list_adapters()

@router.get("/adapters/{adapter_type}")
def get_adapter_details(adapter_type: str,
                         p: Annotated[Principal, Depends(get_principal)]):
    """Get capabilities + connection-status for a specific adapter type."""
    try:
        from ..adapters.registry import REGISTRY
        if adapter_type not in REGISTRY:
            raise HTTPException(404, f"Unknown adapter: {adapter_type}")
        adapter = REGISTRY[adapter_type]()
        caps = adapter.discover_capabilities()
        return {
            "type": adapter_type,
            "is_live": caps.is_live,
            "blocked": not caps.is_live and adapter_type != "simulated",
            "capabilities": {
                "supports_account_discovery": caps.supports_account_discovery,
                "supports_balance_sync": caps.supports_balance_sync,
                "supports_position_sync": caps.supports_position_sync,
                "supports_market_orders": caps.supports_market_orders,
                "supports_limit_orders": caps.supports_limit_orders,
                "supports_stop_orders": caps.supports_stop_orders,
                "supports_modify": caps.supports_modify,
                "supports_cancel": caps.supports_cancel,
                "supports_partial_fills": caps.supports_partial_fills,
                "supports_close_all": caps.supports_close_all,
                "supports_reconciliation": caps.supports_reconciliation,
                "supports_execution_quality": caps.supports_execution_quality,
            },
            "limits": {
                "max_lots_per_order": str(caps.max_lots_per_order) if caps.max_lots_per_order else None,
                "lot_step": str(caps.lot_step),
                "supported_symbols": caps.supported_symbols,
            },
            "notes": caps.notes,
        }
    except ExecutionAdapterError as e:
        raise HTTPException(422, detail={"code": e.code, "message": e.message, "details": e.details})

@router.post("/adapters/{adapter_type}/test-connect")
def test_connect(adapter_type: str,
                 p: Annotated[Principal, Depends(require_roles("broker_admin", "super_admin"))],
                 config: dict | None = None):
    """Attempt to connect to an adapter. For blocked adapters, returns the BLOCKED reason.
    For simulated, returns success."""
    try:
        adapter = get_adapter(adapter_type, config or {})
        adapter.connect(config or {})
        caps = adapter.discover_capabilities()
        return {
            "type": adapter_type,
            "connected": True,
            "is_live": caps.is_live,
            "warning": "SIMULATED — no real connection" if adapter_type == "simulated" else None,
        }
    except ExecutionAdapterError as e:
        return {
            "type": adapter_type,
            "connected": False,
            "blocked": True,
            "code": e.code,
            "reason": e.message,
            "details": e.details,
        }
    except Exception as e:
        return {
            "type": adapter_type,
            "connected": False,
            "blocked": True,
            "code": "UNKNOWN",
            "reason": str(e),
        }
