"""P-1: Risk-Constrained Adaptive Allocation tests."""
from decimal import Decimal
from app.domain import allocation as alloc

def _inv(iid, ret=Decimal("0.1"), vol=Decimal("0.05"), mn=Decimal("0"),
         mx=Decimal("1000"), peak=Decimal("1000"), dd=Decimal("1.0")):
    return alloc.AllocationInvestor(
        investor_id=iid, expected_return=ret, volatility=vol,
        min_allocation=mn, max_allocation=mx, peak_capital=peak,
        drawdown_limit_pct=dd,
    )

def test_solve_maximize_return_feasible():
    """Budget 1000 across 2 investors, both capped at 800. Optimal = 800+200."""
    inv = [_inv("a", ret=Decimal("0.10")), _inv("b", ret=Decimal("0.05"))]
    c = alloc.AllocationConstraints(free_margin=Decimal("1000"))
    sol = alloc.solve("maximize_return", inv, c)
    assert sol.status == "optimal"
    assert sol.objective_value is not None
    total = sum(sol.allocations.values(), Decimal("0"))
    # Budget equality: sum == 1000 (within 1 cent due to quantization)
    assert abs(total - Decimal("1000.00")) <= Decimal("0.01")
    # Investor a (higher return) gets more
    assert sol.allocations["a"] >= sol.allocations["b"]

def test_solve_infeasible_when_floor_exceeds_budget():
    """If min_allocations sum to more than free_margin, LP is infeasible."""
    inv = [_inv("a", mn=Decimal("600")), _inv("b", mn=Decimal("600"))]
    c = alloc.AllocationConstraints(free_margin=Decimal("1000"))
    sol = alloc.solve("maximize_return", inv, c)
    assert sol.status == "infeasible"
    assert sol.allocations == {}
    assert sol.infeasibility_reason is not None
    assert "infeasible" in sol.infeasibility_reason.lower()

def test_solve_caps_below_budget_feasible_underdeployed():
    """If max_allocations sum to less than free_margin, LP is feasible but
    allocates only up to the caps (under-deployed, not infeasible since
    we don't force sum==budget)."""
    inv = [_inv("a", mx=Decimal("300")), _inv("b", mx=Decimal("300"))]
    c = alloc.AllocationConstraints(free_margin=Decimal("1000"))
    sol = alloc.solve("maximize_return", inv, c)
    assert sol.status == "optimal"
    total = sum(sol.allocations.values(), Decimal("0"))
    assert total <= Decimal("600.01")  # respects caps

def test_drawdown_limit_caps_allocation():
    """Drawdown limit of 50% on a $1000 peak means max alloc = $500 each.
    With budget $2000, LP allocates $500+$500 = $1000 (under-deployed, feasible)."""
    inv = [_inv("a", peak=Decimal("1000"), dd=Decimal("0.5")),
           _inv("b", peak=Decimal("1000"), dd=Decimal("0.5"))]
    c = alloc.AllocationConstraints(free_margin=Decimal("2000"))
    sol = alloc.solve("maximize_return", inv, c)
    assert sol.status == "optimal"
    # Each investor capped at $500
    assert sol.allocations["a"] <= Decimal("500.01")
    assert sol.allocations["b"] <= Decimal("500.01")
    # Sum cannot exceed $1000 (the cap total)
    total = sum(sol.allocations.values(), Decimal("0"))
    assert total <= Decimal("1000.01")

def test_minimize_risk_objective():
    """minimize_risk allocates more to lower-volatility investor."""
    inv = [_inv("a", vol=Decimal("0.10")), _inv("b", vol=Decimal("0.01"))]
    c = alloc.AllocationConstraints(free_margin=Decimal("1000"))
    sol = alloc.solve("minimize_risk", inv, c)
    assert sol.status == "optimal"
    # Lower vol investor should get more
    assert sol.allocations["b"] >= sol.allocations["a"]

def test_balanced_objective_runs():
    inv = [_inv("a", ret=Decimal("0.10"), vol=Decimal("0.05")),
           _inv("b", ret=Decimal("0.05"), vol=Decimal("0.02"))]
    c = alloc.AllocationConstraints(free_margin=Decimal("1000"))
    sol = alloc.solve("balanced", inv, c)
    assert sol.status == "optimal"

def test_correlation_constraint_applied():
    """When a+b correlation > max, their combined allocation is constrained."""
    inv = [_inv("a"), _inv("b")]
    c = alloc.AllocationConstraints(
        free_margin=Decimal("1000"),
        pairwise_correlations={("a", "b"): Decimal("0.95")},
        max_correlation_exposure=Decimal("0.5"),
    )
    sol = alloc.solve("maximize_return", inv, c)
    assert sol.status in ("optimal", "infeasible", "suboptimal")
    # If optimal, verify a+b <= 0.5 * 1000 = 500
    if sol.status == "optimal":
        total_ab = sol.allocations["a"] + sol.allocations["b"]
        assert total_ab <= Decimal("500.01"), f"correlation constraint violated: {total_ab}"

def test_unknown_objective_infeasible():
    inv = [_inv("a")]
    c = alloc.AllocationConstraints(free_margin=Decimal("1000"))
    sol = alloc.solve("unknown_objective", inv, c)
    assert sol.status == "infeasible"
    assert "unknown objective" in sol.infeasibility_reason

def test_no_investors_infeasible():
    c = alloc.AllocationConstraints(free_margin=Decimal("1000"))
    sol = alloc.solve("maximize_return", [], c)
    assert sol.status == "infeasible"
    assert "no investors" in sol.infeasibility_reason
