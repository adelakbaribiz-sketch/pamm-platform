"""Non-bypassable pre-trade risk interlock."""
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from ..models import RiskRule, RiskRejection

class RiskError(Exception):
    def __init__(self, code: str, details: dict):
        self.code = code
        self.details = details
        super().__init__(code)

def active_rules(db: Session, tenant_id: str, master_account_id: str | None = None):
    q = db.query(RiskRule).filter(RiskRule.tenant_id == tenant_id, RiskRule.active.is_(True))
    if master_account_id:
        q = q.filter((RiskRule.master_account_id == master_account_id) | (RiskRule.master_account_id.is_(None)))
    return q.all()

def reject(db: Session, tenant_id: str, master_account_id: str | None, code: str, details: dict, payload: dict | None = None):
    db.add(RiskRejection(tenant_id=tenant_id, master_account_id=master_account_id,
                         reason_code=code, reason_details=details, payload=payload))
    db.flush()

def check_pnl_mutation(db, tenant_id, master_account_id, current_equity, proposed_pnl):
    rules = active_rules(db, tenant_id, master_account_id)
    new_equity = Decimal(current_equity) + Decimal(proposed_pnl)
    for rule in rules:
        if rule.kind == "max_total_exposure":
            limit = Decimal(str(rule.params.get("limit")))
            if abs(new_equity) > limit:
                reject(db, tenant_id, master_account_id, "MAX_TOTAL_EXPOSURE",
                       {"limit": str(limit), "actual": str(abs(new_equity))},
                       payload={"proposed_pnl": str(proposed_pnl)})
                raise RiskError("MAX_TOTAL_EXPOSURE",
                                {"limit": str(limit), "actual": str(abs(new_equity))})
        elif rule.kind == "max_drawdown":
            limit_pct = Decimal(str(rule.params.get("limit_pct")))
            peak = Decimal(str(rule.params.get("peak", str(current_equity))))
            dd = (peak - new_equity) / peak if peak > 0 else Decimal("0")
            if dd > limit_pct:
                reject(db, tenant_id, master_account_id, "MAX_DRAWDOWN",
                       {"limit_pct": str(limit_pct), "actual_pct": str(dd)},
                       payload={"proposed_pnl": str(proposed_pnl)})
                raise RiskError("MAX_DRAWDOWN", {"limit_pct": str(limit_pct), "actual_pct": str(dd)})
        elif rule.kind == "news_halt":
            now = datetime.now(timezone.utc)
            start_iso = rule.params.get("start")
            end_iso = rule.params.get("end")
            if start_iso and end_iso:
                start = datetime.fromisoformat(start_iso)
                end = datetime.fromisoformat(end_iso)
                if start <= now <= end:
                    reject(db, tenant_id, master_account_id, "NEWS_HALT", {"window": [start_iso, end_iso]})
                    raise RiskError("NEWS_HALT", {"window": [start_iso, end_iso]})
        elif rule.kind == "circuit_breaker":
            if rule.params.get("tripped", False):
                reject(db, tenant_id, master_account_id, "CIRCUIT_BREAKER_TRIPPED", {})
                raise RiskError("CIRCUIT_BREAKER_TRIPPED", {})

def check_order(db, tenant_id, master_account_id, symbol, lots, price):
    """Risk check for MAM/copy trade submissions."""
    rules = active_rules(db, tenant_id, master_account_id)
    for rule in rules:
        if rule.kind == "circuit_breaker" and rule.params.get("tripped", False):
            reject(db, tenant_id, master_account_id, "CIRCUIT_BREAKER_TRIPPED",
                   {"symbol": symbol, "lots": str(lots)})
            raise RiskError("CIRCUIT_BREAKER_TRIPPED", {"symbol": symbol})
        if rule.kind == "max_symbol_exposure":
            limit = Decimal(str(rule.params.get("limit")))
            notional = Decimal(lots) * (Decimal(price) if price else Decimal("0"))
            if notional > limit:
                reject(db, tenant_id, master_account_id, "MAX_SYMBOL_EXPOSURE",
                       {"symbol": symbol, "limit": str(limit), "notional": str(notional)})
                raise RiskError("MAX_SYMBOL_EXPOSURE", {"symbol": symbol, "notional": str(notional)})
        if rule.kind == "max_lot_per_order":
            limit = Decimal(str(rule.params.get("limit")))
            if Decimal(lots) > limit:
                reject(db, tenant_id, master_account_id, "MAX_LOT_PER_ORDER",
                       {"symbol": symbol, "limit": str(limit), "lots": str(lots)})
                raise RiskError("MAX_LOT_PER_ORDER", {"symbol": symbol, "lots": str(lots)})

def check_subscription(db, tenant_id, master_account_id, capital):
    if Decimal(capital) <= 0:
        reject(db, tenant_id, master_account_id, "INVALID_CAPITAL", {"capital": str(capital)})
        raise RiskError("INVALID_CAPITAL", {"capital": str(capital)})
    rules = active_rules(db, tenant_id, master_account_id)
    for rule in rules:
        if rule.kind == "circuit_breaker" and rule.params.get("tripped", False):
            reject(db, tenant_id, master_account_id, "CIRCUIT_BREAKER_TRIPPED", {})
            raise RiskError("CIRCUIT_BREAKER_TRIPPED", {})
