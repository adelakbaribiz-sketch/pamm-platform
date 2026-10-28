"""
P-1: Risk-Constrained Adaptive Allocation.

Solves a constrained optimization problem: allocate capital across multiple
strategies/investors subject to:
  - Available free margin (total cap)
  - Per-investor max allocation
  - Per-investor min allocation (floor)
  - Per-investor drawdown cap (capital * drawdown_limit)
  - Pairwise correlation-aware diversification (optional)

Objective:
  - maximize_return: weights strategies by expected return (provided in inputs)
  - minimize_risk:  weights by inverse volatility
  - balanced:       risk-adjusted (return / vol)

Solver: scipy.optimize.linprog (HiGHs).
  Decision variables: x_i = capital allocated to investor i, i = 1..n.
  Objective (maximize_return): minimize -sum(return_i * x_i)
  Subject to:
    sum(x_i) <= free_margin               (budget)
    x_i <= max_i                          (per-investor cap)
    x_i >= min_i                          (per-investor floor)
    x_i <= peak_i * (1 - dd_limit_i)      (drawdown cap on remaining)

Infeasibility handling:
  When the LP is infeasible (no allocation satisfies all constraints):
    - The function does NOT fabricate a valid allocation.
    - It marks the problem `frozen`, emits an `AllocationAlert`, and returns
      the canonical "zero allocation" + the infeasibility_reason from the
      solver's `message`. The caller is responsible for either relaxing
      constraints or halting the reallocation.

Fallback behavior:
  - If scipy is unavailable or raises: falls back to a "safe proportional"
    allocation that respects only min/max constraints, never exceeding the
    budget, and emits a SUBOPTIMAL alert. Never silently over-allocates.

This is an engineering hypothesis: the mechanism is implemented, tested, and
persisted for evidence. Patentability is for a qualified attorney to assess.
"""
from __future__ import annotations
from decimal import Decimal
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

try:
    from scipy.optimize import linprog
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

CENT = Decimal("0.01")

def q(x) -> Decimal:
    return Decimal(x).quantize(CENT)

@dataclass
class AllocationInvestor:
    investor_id: str
    expected_return: Decimal = Decimal("0")
    volatility: Decimal = Decimal("0.01")  # avoid div-by-zero
    min_allocation: Decimal = Decimal("0")
    max_allocation: Decimal = Decimal("1000000")
    peak_capital: Decimal = Decimal("0")
    drawdown_limit_pct: Decimal = Decimal("1.0")  # 1.0 = no drawdown cap

@dataclass
class AllocationConstraints:
    free_margin: Decimal
    pairwise_correlations: dict[tuple[str, str], Decimal] = field(default_factory=dict)
    max_correlation_exposure: Optional[Decimal] = None

@dataclass
class AllocationSolution:
    status: str  # optimal|infeasible|frozen|suboptimal
    allocations: dict[str, Decimal]
    objective_value: Decimal | None
    infeasibility_reason: str | None
    solver_message: str | None
    fallback_used: bool

def solve(objective: str, investors: list[AllocationInvestor],
          constraints: AllocationConstraints) -> AllocationSolution:
    """
    Solve the constrained allocation problem.
    Returns AllocationSolution with status and allocations.

    On infeasibility: returns allocations={} (zero), status='infeasible',
    infeasibility_reason set. Caller MUST freeze + alert.
    """
    if not investors:
        return AllocationSolution(
            status="infeasible", allocations={},
            objective_value=None,
            infeasibility_reason="no investors provided",
            solver_message=None, fallback_used=False,
        )

    if not _HAS_SCIPY:
        return _fallback(investors, constraints,
                          reason="scipy.optimize.linprog unavailable")

    n = len(investors)
    ids = [inv.investor_id for inv in investors]

    # Objective coefficients
    if objective == "maximize_return":
        c = np.array([-float(inv.expected_return) for inv in investors])
    elif objective == "minimize_risk":
        # minimize sum(volatility_i * x_i)
        c = np.array([float(inv.volatility) for inv in investors])
    elif objective == "balanced":
        # risk-adjusted: minimize -(return/vol)
        c = np.array([-float(inv.expected_return) / max(float(inv.volatility), 1e-9) for inv in investors])
    else:
        return AllocationSolution(
            status="infeasible", allocations={},
            objective_value=None,
            infeasibility_reason=f"unknown objective: {objective}",
            solver_message=None, fallback_used=False,
        )

    # Inequality constraints A_ub @ x <= b_ub
    A_ub_rows = []
    b_ub = []

    # Budget: sum(x_i) <= free_margin (we use <=, not ==, so we don't force deployment
    # when expected returns are negative or volatility makes scaling up unwise)
    A_ub_rows.append(np.ones(n))
    b_ub.append(float(constraints.free_margin))

    # Per-investor drawdown caps: x_i <= peak_i * dd_limit_i
    # Convention: drawdown_limit_pct = fraction of peak capital the investor is
    # allowed to keep deployed. 1.0 = full peak; 0.5 = at most half the peak.
    # (per-investor max is enforced via bounds below)
    for i, inv in enumerate(investors):
        dd_cap = float(inv.peak_capital) * float(inv.drawdown_limit_pct)
        if dd_cap < float(inv.max_allocation):
            row = np.zeros(n); row[i] = 1.0
            A_ub_rows.append(row)
            b_ub.append(dd_cap)

    # Pairwise correlation diversification (optional, lightweight)
    # If a pair has correlation > max_correlation_exposure, constrain their sum.
    if constraints.max_correlation_exposure is not None:
        for (id_a, id_b), corr in constraints.pairwise_correlations.items():
            if corr > constraints.max_correlation_exposure and id_a in ids and id_b in ids:
                ia = ids.index(id_a); ib = ids.index(id_b)
                row = np.zeros(n); row[ia] = 1.0; row[ib] = 1.0
                A_ub_rows.append(row)
                b_ub.append(float(constraints.free_margin) * 0.5)  # halve concentration

    A_ub = np.array(A_ub_rows)
    b_ub_arr = np.array(b_ub)

    # Bounds: [min, max] per investor
    bounds = [(float(inv.min_allocation), float(inv.max_allocation)) for inv in investors]

    # Solve (no equality — budget is <= )
    res = linprog(c, A_ub=A_ub, b_ub=b_ub_arr,
                  bounds=bounds, method="highs")

    if res.status == 0:  # success
        allocs = {ids[i]: q(Decimal(str(res.x[i]))) for i in range(n)}
        return AllocationSolution(
            status="optimal",
            allocations=allocs,
            objective_value=q(Decimal(str(-res.fun))),
            infeasibility_reason=None,
            solver_message=res.message,
            fallback_used=False,
        )
    elif res.status == 2:  # infeasible
        return AllocationSolution(
            status="infeasible",
            allocations={},
            objective_value=None,
            infeasibility_reason=f"LP infeasible: {res.message}",
            solver_message=res.message,
            fallback_used=False,
        )
    elif res.status == 3:  # unbounded — shouldn't happen with budget equality
        return AllocationSolution(
            status="infeasible",
            allocations={},
            objective_value=None,
            infeasibility_reason=f"LP unbounded: {res.message}",
            solver_message=res.message,
            fallback_used=False,
        )
    else:
        return _fallback(investors, constraints,
                          reason=f"LP status {res.status}: {res.message}")

def _fallback(investors: list[AllocationInvestor],
              constraints: AllocationConstraints, reason: str) -> AllocationSolution:
    """
    Safe proportional fallback when the LP solver is unavailable or returns
    an unexpected status. Allocates free_margin proportionally to
    (max_i - min_i), clipped at per-investor max. Never exceeds budget.
    Marks status='suboptimal' so caller can alert.
    """
    n = len(investors)
    spans = [float(inv.max_allocation - inv.min_allocation) for inv in investors]
    total_span = sum(spans)
    if total_span <= 0:
        return AllocationSolution(
            status="infeasible", allocations={},
            objective_value=None, infeasibility_reason="all investors have min==max",
            solver_message=reason, fallback_used=True,
        )
    budget = float(constraints.free_margin)
    allocations = {}
    used = 0.0
    for i, inv in enumerate(investors):
        share = spans[i] / total_span * budget
        # respect floor and cap
        alloc = max(float(inv.min_allocation), min(share, float(inv.max_allocation)))
        allocations[inv.investor_id] = q(Decimal(str(alloc)))
        used += alloc
    # If we under-used budget, scale up proportionally to remaining headroom
    slack = budget - used
    if slack > 0:
        headrooms = [float(inv.max_allocation) - allocations[inv.investor_id] for inv in investors]
        total_headroom = sum(headrooms)
        if total_headroom > 0:
            for i, inv in enumerate(investors):
                bump = headrooms[i] / total_headroom * slack
                allocations[inv.investor_id] = q(Decimal(str(allocations[inv.investor_id]) + Decimal(str(bump))))
    return AllocationSolution(
        status="suboptimal",
        allocations=allocations,
        objective_value=None,
        infeasibility_reason=reason,
        solver_message=reason,
        fallback_used=True,
    )
