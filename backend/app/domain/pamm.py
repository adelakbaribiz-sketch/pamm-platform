"""PAMM allocation engine — Decimal-only accounting."""
from decimal import Decimal, ROUND_HALF_UP, getcontext
getcontext().prec = 50

CENT = Decimal("0.01")
UNIT_Q = Decimal("0.00000001")

def q2(x) -> Decimal:
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)

def q_units(x) -> Decimal:
    return Decimal(x).quantize(UNIT_Q, rounding=ROUND_HALF_UP)

def compute_nav(master_equity, total_units, base_nav) -> Decimal:
    if Decimal(total_units) <= 0:
        return Decimal(base_nav)
    return Decimal(master_equity) / Decimal(total_units)

def issue_units(capital, current_nav) -> Decimal:
    if Decimal(current_nav) <= 0:
        raise ValueError("NAV must be positive to issue units")
    return q_units(Decimal(capital) / Decimal(current_nav))

class InvestorSnapshot:
    def __init__(self, subscription_id, units, start_capital, end_capital, euro_days, hwm):
        self.subscription_id = subscription_id
        self.units = Decimal(units)
        self.start_capital = Decimal(start_capital)
        self.end_capital = Decimal(end_capital)
        self.euro_days = Decimal(euro_days)
        self.hwm = Decimal(hwm)

class RolloverResult:
    def __init__(self, subscription_id):
        self.subscription_id = subscription_id
        self.units = Decimal("0")
        self.start_capital = Decimal("0")
        self.end_capital = Decimal("0")
        self.euro_days = Decimal("0")
        self.pnl_share = Decimal("0")
        self.performance_fee = Decimal("0")
        self.nav_before = Decimal("0")
        self.nav_after = Decimal("0")
        self.units_after = Decimal("0")
        self.new_hwm = Decimal("0")
        self.gav_end = Decimal("0")

def allocate_pnl(pnl, investors, method) -> dict:
    if not investors: return {}
    pnl = Decimal(pnl)
    if pnl == 0:
        return {inv.subscription_id: Decimal("0") for inv in investors}
    if method == "start_capital":
        weights = {inv.subscription_id: inv.start_capital for inv in investors}
    elif method == "end_capital":
        weights = {inv.subscription_id: inv.end_capital for inv in investors}
    elif method == "euro_days":
        weights = {inv.subscription_id: inv.euro_days for inv in investors}
    else:
        raise ValueError(f"Unknown allocation method: {method}")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("Total weighting is zero; cannot allocate PnL")
    shares = {sid: q2(weights[sid] / total * pnl) for sid in weights}
    allocated_total = q2(sum(shares.values()))
    residual = q2(pnl) - allocated_total
    if residual != 0:
        largest = max(weights.items(), key=lambda kv: kv[1])[0]
        shares[largest] = q2(shares[largest] + residual)
    return shares

def apply_rollover(nav_before, nav_after_gross, investors, performance_fee_rate, method):
    nav_before = Decimal(nav_before)
    nav_after_gross = Decimal(nav_after_gross)
    master_pnl_per_unit = nav_after_gross - nav_before
    total_units = sum((inv.units for inv in investors), Decimal("0"))
    master_pnl = q2(master_pnl_per_unit * total_units)
    pnl_shares = allocate_pnl(master_pnl, investors, method)
    results = []
    total_fee = Decimal("0")
    for inv in investors:
        r = RolloverResult(inv.subscription_id)
        r.units = q_units(inv.units)
        r.start_capital = q2(inv.start_capital)
        r.end_capital = q2(inv.end_capital)
        r.euro_days = q_units(inv.euro_days)
        r.nav_before = q2(nav_before)
        r.nav_after = q2(nav_after_gross)
        r.pnl_share = q2(pnl_shares[inv.subscription_id])
        gav_end = q2(inv.units * nav_after_gross)
        r.gav_end = gav_end
        new_high = max(inv.hwm, gav_end)
        gain_above_hwm = max(Decimal("0"), gav_end - inv.hwm)
        fee = q2(Decimal(performance_fee_rate) * gain_above_hwm)
        r.performance_fee = fee
        r.new_hwm = new_high
        total_fee += fee
        units_redeemed = q_units(fee / nav_after_gross) if nav_after_gross > 0 else Decimal("0")
        r.units_after = q_units(inv.units - units_redeemed)
        results.append(r)
    return results, q2(total_fee)

def reconcile(master_equity_after, investor_results, total_fee) -> bool:
    investor_total = q2(sum((r.gav_end for r in investor_results), Decimal("0")))
    lhs = q2(investor_total + total_fee)
    rhs = q2(master_equity_after)
    return abs(lhs - rhs) <= Decimal("0.01")
