"""Public market data router — top-performing accounts, manager portfolios, P&L charts.

These endpoints are read-only and power the public homepage. They do NOT
require authentication — they show aggregated performance data only.
Individual investor PII is never exposed.
"""
from typing import Annotated, Optional
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, text
from ..db import get_db
from ..models import (MasterAccount, Strategy, Subscription, Rollover, RolloverEntry,
                       InvestorAccount, User, Broker, Tenant)
from ..domain import pamm
from ..config import settings

router = APIRouter()


def _public_tenant_id(db: Session) -> str | None:
    """Public pages show a single tenant's showcase (settings.default_tenant).

    Without this scope the unauthenticated endpoints aggregated every tenant's
    accounts, leaking one broker's book to another broker's public page.
    """
    t = db.query(Tenant).filter(Tenant.slug == settings.default_tenant).first()
    return t.id if t else "__none__"


@router.get("/top-accounts")
def top_performing_accounts(
    db: Session = Depends(get_db),
    limit: int = Query(10, ge=1, le=50),
    sort_by: str = Query("equity", regex="^(equity|return_pct|total_fee)$"),
):
    """Returns top-performing master accounts with aggregated stats.

    No authentication required — public performance data only.
    """
    tid = _public_tenant_id(db)
    q = db.query(MasterAccount).filter(MasterAccount.status == "active", MasterAccount.tenant_id == tid)
    accounts = q.all()

    results = []
    for m in accounts:
        # Calculate total return percentage
        initial_capital = Decimal("0")
        if m.total_units > 0:
            initial_capital = m.equity - (m.equity - m.base_nav * m.total_units)
            initial_capital = m.equity / m.total_units * m.total_units if m.total_units > 0 else Decimal("0")

        # Get rollover history for P&L chart
        rollovers = db.query(Rollover).filter(
            Rollover.master_account_id == m.id,
        ).order_by(Rollover.period_end.desc()).limit(120).all()

        pnl_history = []
        cumulative_pnl = Decimal("0")
        for r in reversed(rollovers):
            cumulative_pnl += r.master_pnl or Decimal("0")
            pnl_history.append({
                "date": r.period_end.isoformat() if r.period_end else None,
                "nav": float(r.nav_after) if r.nav_after else 0,
                "pnl": float(r.master_pnl) if r.master_pnl else 0,
                "cumulative_pnl": float(cumulative_pnl),
                "total_fee": float(r.total_performance_fee),
                "equity": float(r.master_equity_after) if r.master_equity_after is not None else None,
            })

        # Count active subscribers
        subscriber_count = db.query(Subscription).filter(
            Subscription.master_account_id == m.id,
            Subscription.status == "active",
        ).count()

        # Total AUM
        total_aum = m.equity

        # Return percentage based on NAV change from base
        if m.base_nav > 0 and m.nav_at_period_start > 0:
            current_nav = pamm.compute_nav(m.equity, m.total_units, m.base_nav)
            return_pct = ((current_nav - m.base_nav) / m.base_nav * Decimal("100"))
        else:
            return_pct = Decimal("0")

        # Get manager name
        manager = db.query(User).filter(User.id == m.manager_user_id).first() if m.manager_user_id else None
        strat = db.query(Strategy).filter(Strategy.master_account_id == m.id).first()

        results.append({
            "master_account_id": m.id,
            "login": m.login,
            "currency": m.currency,
            "equity": str(m.equity),
            "nav": str(pamm.compute_nav(m.equity, m.total_units, m.base_nav)),
            "base_nav": str(m.base_nav),
            "return_pct": str(return_pct.quantize(Decimal("0.01"))),
            "total_aum": str(total_aum),
            "subscriber_count": subscriber_count,
            "performance_fee_rate": str(m.performance_fee_rate),
            "allocation_method": m.allocation_method,
            "manager_name": manager.email.split("@")[0] if manager else "unknown",
            "manager_id": manager.id if manager else None,
            "strategy_id": strat.id if strat else None,
            "strategy_name": strat.name if strat else None,
            "strategy_kind": strat.kind if strat else "pamm",
            "pnl_history": pnl_history,
        })

    # Sort
    if sort_by == "equity":
        results.sort(key=lambda x: float(x["equity"]), reverse=True)
    elif sort_by == "return_pct":
        results.sort(key=lambda x: float(x["return_pct"]), reverse=True)
    elif sort_by == "total_fee":
        results.sort(key=lambda x: float(x.get("pnl_history", [{}])[-1].get("total_fee", 0)), reverse=True)

    return results[:limit]


@router.get("/managers")
def list_managers(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    """Returns a directory of money managers with their aggregate portfolio stats."""
    # Find all users with role=money_manager
    tid = _public_tenant_id(db)
    managers = db.query(User).filter(User.role == "money_manager", User.status == "active",
                                     User.tenant_id == tid).all()

    results = []
    for mgr in managers:
        # Get all master accounts managed by this user
        master_accounts = db.query(MasterAccount).filter(
            MasterAccount.manager_user_id == mgr.id,
            MasterAccount.status == "active",
        ).all()

        if not master_accounts:
            continue

        total_aum = Decimal("0")
        total_subscribers = 0
        total_return_pct = Decimal("0")
        strategies = []

        for m in master_accounts:
            total_aum += m.equity
            subs = db.query(Subscription).filter(
                Subscription.master_account_id == m.id,
                Subscription.status == "active",
            ).count()
            total_subscribers += subs

            current_nav = pamm.compute_nav(m.equity, m.total_units, m.base_nav)
            if m.base_nav > 0:
                total_return_pct += (current_nav - m.base_nav) / m.base_nav * Decimal("100")

            strat = db.query(Strategy).filter(Strategy.master_account_id == m.id).first()
            if strat:
                strategies.append({
                    "strategy_id": strat.id,
                    "name": strat.name,
                    "kind": strat.kind,
                    "master_login": m.login,
                    "equity": str(m.equity),
                    "nav": str(current_nav),
                    "return_pct": str(((current_nav - m.base_nav) / m.base_nav * Decimal("100")).quantize(Decimal("0.01"))) if m.base_nav > 0 else "0",
                    "subscriber_count": subs,
                    "performance_fee_rate": str(m.performance_fee_rate),
                    "allocation_method": m.allocation_method,
                })

        avg_return = (total_return_pct / len(master_accounts)).quantize(Decimal("0.01")) if master_accounts else Decimal("0")

        results.append({
            "manager_id": mgr.id,
            "manager_name": mgr.email.split("@")[0],
            "master_account_count": len(master_accounts),
            "total_aum": str(total_aum.quantize(Decimal("0.01"))),
            "total_subscribers": total_subscribers,
            "avg_return_pct": str(avg_return),
            "strategies": strategies,
        })

    results.sort(key=lambda x: float(x["total_aum"]), reverse=True)
    return results[:limit]


@router.get("/strategies")
def list_public_strategies(
    db: Session = Depends(get_db),
    kind: Optional[str] = Query(None, regex="^(pamm|mam|copy)$"),
    limit: int = Query(20, ge=1, le=100),
):
    """Returns investable strategies with performance stats — powers the
    'Invest' section on the public homepage."""
    tid = _public_tenant_id(db)
    q = db.query(Strategy).filter(Strategy.status == "active", Strategy.tenant_id == tid)
    if kind:
        q = q.filter(Strategy.kind == kind)
    strategies = q.all()

    results = []
    for s in strategies:
        m = db.query(MasterAccount).filter(MasterAccount.id == s.master_account_id).first()
        if not m or m.status != "active":
            continue

        subscriber_count = db.query(Subscription).filter(
            Subscription.strategy_id == s.id,
            Subscription.status == "active",
        ).count()

        current_nav = pamm.compute_nav(m.equity, m.total_units, m.base_nav)
        return_pct = ((current_nav - m.base_nav) / m.base_nav * Decimal("100")).quantize(Decimal("0.01")) if m.base_nav > 0 else Decimal("0")

        results.append({
            "strategy_id": s.id,
            "name": s.name,
            "description": s.description,
            "kind": s.kind,
            "master_login": m.login,
            "currency": m.currency,
            "nav": str(current_nav),
            "base_nav": str(m.base_nav),
            "return_pct": str(return_pct),
            "equity": str(m.equity),
            "subscriber_count": subscriber_count,
            "performance_fee_rate": str(m.performance_fee_rate),
            "allocation_method": m.allocation_method,
            "min_investment": "100",  # configurable per-strategy in production
        })

    results.sort(key=lambda x: float(x["return_pct"]), reverse=True)
    return results[:limit]


@router.get("/stats")
def platform_stats(db: Session = Depends(get_db)):
    """Returns platform-wide aggregate stats for the homepage hero section."""
    tid = _public_tenant_id(db)
    total_masters = db.query(MasterAccount).filter(MasterAccount.status == "active", MasterAccount.tenant_id == tid).count()
    total_strategies = db.query(Strategy).filter(Strategy.status == "active", Strategy.tenant_id == tid).count()
    total_investors = db.query(Subscription).filter(Subscription.status == "active", Subscription.tenant_id == tid).count()
    total_aum = db.query(func.sum(MasterAccount.equity)).filter(MasterAccount.status == "active", MasterAccount.tenant_id == tid).scalar() or Decimal("0")

    # Count rollovers in last 30 days
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    recent_rollovers = db.query(Rollover).filter(Rollover.created_at >= thirty_days_ago, Rollover.tenant_id == tid).count()

    return {
        "total_masters": total_masters,
        "total_strategies": total_strategies,
        "total_active_investors": total_investors,
        "total_aum": str(total_aum),
        "recent_rollovers_30d": recent_rollovers,
    }
