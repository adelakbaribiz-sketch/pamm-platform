"""MAM engine: lot splitting, residual allocation, reconciliation."""
from decimal import Decimal
from app.domain import mam

def test_split_equity_ratio():
    inv = [
        mam.MamInvestor("s1", "i1", equity=Decimal("1000"), lot_multiplier=Decimal("1")),
        mam.MamInvestor("s2", "i2", equity=Decimal("3000"), lot_multiplier=Decimal("1")),
    ]
    allocs = mam.split_order(Decimal("4"), inv, "equity_ratio", Decimal("0.01"))
    # 1000/4000 * 4 = 1 lot; 3000/4000 * 4 = 3 lots
    assert sum((a.allocated_lots for a in allocs), Decimal("0")) == Decimal("4.00")
    a1 = next(a for a in allocs if a.subscription_id == "s1")
    a2 = next(a for a in allocs if a.subscription_id == "s2")
    assert a1.allocated_lots == Decimal("1.00")
    assert a2.allocated_lots == Decimal("3.00")

def test_split_residual_distributed():
    """3 investors, 1 lot each at lot_step 0.01. Master=1.0 -> 33.33, 33.33, 33.34 (residual)."""
    inv = [
        mam.MamInvestor("s1", "i1", equity=Decimal("1")),
        mam.MamInvestor("s2", "i2", equity=Decimal("1")),
        mam.MamInvestor("s3", "i3", equity=Decimal("1")),
    ]
    allocs = mam.split_order(Decimal("1"), inv, "equity_ratio", Decimal("0.01"))
    total = sum((a.allocated_lots for a in allocs), Decimal("0"))
    # Reconciled to nearest lot_step
    assert mam.reconcile(allocs, Decimal("1"), Decimal("0.01"))
    # No investor got more than master
    for a in allocs:
        assert a.allocated_lots <= Decimal("1")

def test_split_percentage():
    inv = [
        mam.MamInvestor("s1", "i1", percentage=Decimal("0.5")),
        mam.MamInvestor("s2", "i2", percentage=Decimal("0.5")),
    ]
    allocs = mam.split_order(Decimal("10"), inv, "percentage", Decimal("0.01"))
    a1 = next(a for a in allocs if a.subscription_id == "s1")
    a2 = next(a for a in allocs if a.subscription_id == "s2")
    assert a1.allocated_lots == Decimal("5.00")
    assert a2.allocated_lots == Decimal("5.00")

def test_split_fixed_lot_mult():
    inv = [mam.MamInvestor("s1", "i1", lot_multiplier=Decimal("0.5")),
           mam.MamInvestor("s2", "i2", lot_multiplier=Decimal("2"))]
    allocs = mam.split_order(Decimal("4"), inv, "fixed_lot_mult", Decimal("0.01"))
    a1 = next(a for a in allocs if a.subscription_id == "s1")
    a2 = next(a for a in allocs if a.subscription_id == "s2")
    assert a1.allocated_lots == Decimal("2.00")
    assert a2.allocated_lots == Decimal("8.00")

def test_reconcile_fails_on_mismatch():
    inv = [mam.MamInvestor("s1", "i1", equity=Decimal("1"))]
    allocs = mam.split_order(Decimal("1"), inv, "equity_ratio", Decimal("0.01"))
    assert mam.reconcile(allocs, Decimal("1"), Decimal("0.01"))
    assert not mam.reconcile(allocs, Decimal("2"), Decimal("0.01"))

def test_split_invalid_method():
    inv = [mam.MamInvestor("s1", "i1", equity=Decimal("1"))]
    try:
        mam.split_order(Decimal("1"), inv, "unknown_method", Decimal("0.01"))
        assert False
    except ValueError as e:
        assert "Unknown MAM" in str(e)

def test_split_zero_total_weight_rejected():
    inv = [mam.MamInvestor("s1", "i1", equity=Decimal("0"))]
    try:
        mam.split_order(Decimal("1"), inv, "equity_ratio", Decimal("0.01"))
        assert False
    except ValueError as e:
        assert "zero" in str(e).lower()
