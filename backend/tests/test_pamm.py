"""PAMM allocation + HWM + reconciliation tests."""
from decimal import Decimal
from app.domain import pamm

def test_issue_units_at_base_nav():
    assert pamm.issue_units(Decimal("1000"), Decimal("100")) == Decimal("10.00000000")

def test_nav_after_pnl():
    assert pamm.compute_nav(Decimal("1100"), Decimal("10"), Decimal("100")) == Decimal("110")

def test_allocate_start_capital_simple():
    inv = [
        pamm.InvestorSnapshot("a", Decimal("10"), Decimal("1000"), Decimal("1000"), Decimal("1000"), Decimal("0")),
        pamm.InvestorSnapshot("b", Decimal("10"), Decimal("1000"), Decimal("1000"), Decimal("1000"), Decimal("0")),
    ]
    shares = pamm.allocate_pnl(Decimal("200"), inv, "start_capital")
    assert shares["a"] == Decimal("100.00")
    assert shares["b"] == Decimal("100.00")
    assert sum(shares.values()) == Decimal("200.00")

def test_allocate_euro_days_weighted():
    inv = [
        pamm.InvestorSnapshot("a", Decimal("10"), Decimal("1000"), Decimal("1000"), Decimal("2000"), Decimal("0")),
        pamm.InvestorSnapshot("b", Decimal("10"), Decimal("1000"), Decimal("1000"), Decimal("1000"), Decimal("0")),
    ]
    shares = pamm.allocate_pnl(Decimal("300"), inv, "euro_days")
    assert shares["a"] == Decimal("200.00")
    assert shares["b"] == Decimal("100.00")

def test_cent_exact_residual_adjustment():
    inv = [
        pamm.InvestorSnapshot("a", Decimal("1"), Decimal("100"), Decimal("100"), Decimal("100"), Decimal("0")),
        pamm.InvestorSnapshot("b", Decimal("1"), Decimal("100"), Decimal("100"), Decimal("100"), Decimal("0")),
        pamm.InvestorSnapshot("c", Decimal("1"), Decimal("100"), Decimal("100"), Decimal("100"), Decimal("0")),
    ]
    shares = pamm.allocate_pnl(Decimal("100"), inv, "euro_days")
    assert sum(shares.values()) == Decimal("100.00")

def test_hwm_fee_only_on_incremental_gain():
    nav_before, nav_after = Decimal("100"), Decimal("110")
    inv = [pamm.InvestorSnapshot("a", Decimal("10"), Decimal("1000"), Decimal("1000"), Decimal("1000"), Decimal("1200"))]
    results, total_fee = pamm.apply_rollover(nav_before, nav_after, inv, Decimal("0.2"), "start_capital")
    r = results[0]
    assert r.gav_end == Decimal("1100.00")
    assert r.performance_fee == Decimal("0.00")
    assert total_fee == Decimal("0.00")

def test_hwm_fee_charged_on_new_high():
    nav_before, nav_after = Decimal("100"), Decimal("120")
    inv = [pamm.InvestorSnapshot("a", Decimal("10"), Decimal("1000"), Decimal("1000"), Decimal("1000"), Decimal("1000"))]
    results, total_fee = pamm.apply_rollover(nav_before, nav_after, inv, Decimal("0.2"), "start_capital")
    r = results[0]
    assert r.gav_end == Decimal("1200.00")
    assert r.performance_fee == Decimal("40.00")
    assert r.new_hwm == Decimal("1200.00")
    assert r.units_after < Decimal("10")

def test_reconciliation_holds():
    nav_before, nav_after = Decimal("100"), Decimal("120")
    inv = [
        pamm.InvestorSnapshot("a", Decimal("10"), Decimal("1000"), Decimal("1000"), Decimal("1000"), Decimal("1000")),
        pamm.InvestorSnapshot("b", Decimal("10"), Decimal("1000"), Decimal("1000"), Decimal("1000"), Decimal("1000")),
    ]
    results, total_fee = pamm.apply_rollover(nav_before, nav_after, inv, Decimal("0.2"), "start_capital")
    master_equity_after = sum((r.gav_end for r in results), Decimal("0")) + total_fee
    assert pamm.reconcile(master_equity_after, results, total_fee)

def test_allocation_methods_converge_without_flows():
    inv = [
        pamm.InvestorSnapshot("a", Decimal("10"), Decimal("1000"), Decimal("1000"), Decimal("1000"), Decimal("0")),
        pamm.InvestorSnapshot("b", Decimal("10"), Decimal("1000"), Decimal("1000"), Decimal("1000"), Decimal("0")),
    ]
    pnl = Decimal("200")
    assert pamm.allocate_pnl(pnl, inv, "start_capital") == pamm.allocate_pnl(pnl, inv, "end_capital") == pamm.allocate_pnl(pnl, inv, "euro_days")

def test_zero_pnl_produces_zero_shares():
    inv = [
        pamm.InvestorSnapshot("a", Decimal("10"), Decimal("1000"), Decimal("1000"), Decimal("1000"), Decimal("0")),
        pamm.InvestorSnapshot("b", Decimal("10"), Decimal("1000"), Decimal("1000"), Decimal("1000"), Decimal("0")),
    ]
    shares = pamm.allocate_pnl(Decimal("0"), inv, "euro_days")
    assert shares["a"] == Decimal("0")
    assert shares["b"] == Decimal("0")
