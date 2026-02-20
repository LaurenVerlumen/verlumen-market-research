"""Profit and margin analysis for Alibaba-to-Amazon arbitrage."""
from typing import Optional


def calculate_profit(
    alibaba_price_min: float,
    alibaba_price_max: float,
    amazon_competitors: list[dict],
    shipping_estimate: float = 3.0,
    amazon_fee_pct: float = 0.15,
) -> dict:
    """Calculate profit/margin metrics for budget, competitive, and premium strategies.

    Parameters
    ----------
    alibaba_price_min : float
        Minimum Alibaba unit price.
    alibaba_price_max : float
        Maximum Alibaba unit price.
    amazon_competitors : list[dict]
        Competitor dicts with ``"price"``, ``"bought_last_month"`` keys.
    shipping_estimate : float
        Estimated shipping cost per unit (default $3.00).
    amazon_fee_pct : float
        Amazon referral fee as a fraction (default 0.15 = 15%).

    Returns
    -------
    dict with keys:
        - landed_cost: average alibaba price + shipping
        - strategies: dict with budget/competitive/premium entries containing
          selling_price, amazon_fee, net_profit, profit_margin_pct, roi_pct
        - break_even_units: dict per strategy
        - monthly_profit_estimate: dict per strategy
    """
    if alibaba_price_min is None or alibaba_price_max is None:
        return _empty_result()

    alibaba_avg = (alibaba_price_min + alibaba_price_max) / 2.0
    landed_cost = alibaba_avg + shipping_estimate

    # Determine strategy prices from competitor percentiles
    prices = sorted(
        c["price"] for c in amazon_competitors
        if c.get("price") is not None and c["price"] > 0
    )

    if not prices:
        return _empty_result()

    import numpy as np

    p25 = float(np.percentile(prices, 25))
    p50 = float(np.percentile(prices, 50))
    p75 = float(np.percentile(prices, 75))

    strategy_prices = {
        "budget": p25,
        "competitive": p50,
        "premium": p75,
    }

    # Estimate demand at each price point
    demand_data = _build_demand_data(amazon_competitors)

    strategies = {}
    break_even_units = {}
    monthly_profit_estimate = {}

    # Assume MOQ of 100 for break-even calculation (initial investment)
    moq = 100

    for name, selling_price in strategy_prices.items():
        fee = round(selling_price * amazon_fee_pct, 2)
        net_profit = round(selling_price - fee - landed_cost, 2)
        margin_pct = round((net_profit / selling_price) * 100, 1) if selling_price > 0 else 0.0
        roi_pct = round((net_profit / landed_cost) * 100, 1) if landed_cost > 0 else 0.0

        # Break-even: initial investment = moq * landed_cost
        initial_investment = moq * landed_cost
        if net_profit > 0:
            be_units = int(initial_investment / net_profit) + 1
        else:
            be_units = 0  # Not profitable

        # Monthly profit estimate based on demand
        est_monthly_units = _estimate_units_at_price(selling_price, demand_data)
        monthly_profit = round(net_profit * est_monthly_units, 2)

        strategies[name] = {
            "selling_price": round(selling_price, 2),
            "amazon_fee": fee,
            "net_profit": net_profit,
            "profit_margin_pct": margin_pct,
            "roi_pct": roi_pct,
        }
        break_even_units[name] = be_units
        monthly_profit_estimate[name] = {
            "estimated_monthly_units": est_monthly_units,
            "monthly_profit": monthly_profit,
        }

    return {
        "landed_cost": round(landed_cost, 2),
        "strategies": strategies,
        "break_even_units": break_even_units,
        "monthly_profit_estimate": monthly_profit_estimate,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_demand_data(competitors: list[dict]) -> list[tuple[float, int]]:
    """Extract (price, monthly_units) pairs from competitor data."""
    import re
    data = []
    for c in competitors:
        price = c.get("price")
        bought = c.get("bought_last_month")
        units = _parse_bought(bought)
        if price is not None and price > 0 and units is not None and units > 0:
            data.append((price, units))
    return data


def _parse_bought(value) -> Optional[int]:
    """Parse 'X+ bought in past month' or numeric values into an int."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        import re
        cleaned = value.lower().replace(",", "").strip()
        if not cleaned:
            return None
        if "k" in cleaned:
            num_part = cleaned.split("k")[0].strip().rstrip("+").strip()
            try:
                return int(float(num_part) * 1000)
            except (ValueError, TypeError):
                return None
        match = re.search(r"(\d+)", cleaned)
        if match:
            return int(match.group(1))
    return None


def _estimate_units_at_price(
    target_price: float, demand_data: list[tuple[float, int]]
) -> int:
    """Estimate monthly units at a price using inverse-distance weighting."""
    if not demand_data:
        return 0
    total_weight = 0.0
    weighted_units = 0.0
    for price, units in demand_data:
        distance = abs(price - target_price) + 1.0
        weight = 1.0 / distance
        total_weight += weight
        weighted_units += weight * units
    if total_weight == 0:
        return 0
    return max(1, int(weighted_units / total_weight))


def _empty_result() -> dict:
    return {
        "landed_cost": 0.0,
        "strategies": {},
        "break_even_units": {},
        "monthly_profit_estimate": {},
    }
