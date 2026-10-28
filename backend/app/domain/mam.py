"""
MAM allocation engine.

Splits a single master order into per-investor child tickets using one of:
  - equity_ratio:    weight = investor_equity / sum(equity)
  - balance_ratio:   weight = investor_balance / sum(balance)
  - fixed_lot_mult:  each investor gets lots = master_lots * fixed_multiplier
  - percentage:      explicit per-investor percentage weights (sum=1)

Deterministic lot rounding:
  - Apply lot_step rounding DOWN (floor) to each child.
  - Sum of rounded lots usually < master_lots.
  - Distribute the RESIDUAL one lot-step at a time to investors with the
    largest fractional remainders, until the residual is exhausted.

This guarantees sum(child_lots) == master_lots exactly (when lot_step divides master_lots).
"""
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN, getcontext
getcontext().prec = 50

def q_lots(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

class MamInvestor:
    def __init__(self, subscription_id, investor_account_id,
                 equity=None, balance=None, percentage=None,
                 lot_multiplier=Decimal("1")):
        self.subscription_id = subscription_id
        self.investor_account_id = investor_account_id
        self.equity = Decimal(equity or 0)
        self.balance = Decimal(balance or 0)
        self.percentage = Decimal(percentage or 0)
        self.lot_multiplier = Decimal(lot_multiplier)

class MamChildAllocation:
    def __init__(self, subscription_id, investor_account_id,
                 requested_lots, allocated_lots, residual_lots=Decimal("0")):
        self.subscription_id = subscription_id
        self.investor_account_id = investor_account_id
        self.requested_lots = Decimal(requested_lots)
        self.allocated_lots = Decimal(allocated_lots)
        self.residual_lots = Decimal(residual_lots)

def split_order(master_lots, investors, method, lot_step=Decimal("0.01")) -> list[MamChildAllocation]:
    """
    Returns list of MamChildAllocation with deterministic residual distribution.
    Guarantees sum(allocated_lots) == floor(master_lots / lot_step) * lot_step.
    """
    master_lots = Decimal(master_lots)
    lot_step = Decimal(lot_step)
    if lot_step <= 0:
        raise ValueError("lot_step must be positive")

    if method == "fixed_lot_mult":
        results = []
        for inv in investors:
            raw = master_lots * inv.lot_multiplier
            floored = (raw // lot_step) * lot_step
            results.append(MamChildAllocation(
                inv.subscription_id, inv.investor_account_id,
                requested_lots=raw, allocated_lots=floored,
            ))
        return results

    if method == "percentage":
        weights = {inv.subscription_id: inv.percentage for inv in investors}
    elif method == "equity_ratio":
        weights = {inv.subscription_id: inv.equity for inv in investors}
    elif method == "balance_ratio":
        weights = {inv.subscription_id: inv.balance for inv in investors}
    else:
        raise ValueError(f"Unknown MAM allocation method: {method}")

    total = sum(weights.values())
    if total <= 0:
        raise ValueError("Total weighting is zero")

    results = []
    fractions = {}  # subscription_id -> (floored, fractional_remainder)
    for inv in investors:
        raw = (weights[inv.subscription_id] / total) * master_lots
        floored = (raw // lot_step) * lot_step
        remainder = raw - floored
        fractions[inv.subscription_id] = (raw, floored, remainder)
        results.append(MamChildAllocation(
            inv.subscription_id, inv.investor_account_id,
            requested_lots=raw, allocated_lots=floored,
        ))

    # Residual distribution: one lot-step at a time to largest fractional remainder
    allocated_total = sum(r.allocated_lots for r in results)
    total_target = (master_lots // lot_step) * lot_step
    residual = total_target - allocated_total
    steps_remaining = int(residual / lot_step)
    while steps_remaining > 0:
        # Find largest fractional remainder that hasn't been rounded up yet
        # Re-sort by remainder descending
        remainders = [(inv.subscription_id, fractions[inv.subscription_id][2])
                       for inv in investors]
        remainders.sort(key=lambda x: -x[1])
        for sid, _ in remainders[:steps_remaining]:
            r = next(x for x in results if x.subscription_id == sid)
            r.allocated_lots += lot_step
            r.residual_lots += lot_step
            steps_remaining -= 1
            if steps_remaining == 0:
                break
    return results

def reconcile(allocations, master_lots, lot_step=Decimal("0.01")) -> bool:
    """sum(allocated) == floor(master_lots / lot_step) * lot_step, within lot_step."""
    total = sum((a.allocated_lots for a in allocations), Decimal("0"))
    target = (Decimal(master_lots) // Decimal(lot_step)) * Decimal(lot_step)
    return abs(total - target) < Decimal(lot_step)
