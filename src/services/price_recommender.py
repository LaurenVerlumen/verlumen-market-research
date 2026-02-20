"""Price strategy recommendations using k-means clustering and statistical analysis."""
import statistics
from typing import Optional

import numpy as np
from sklearn.cluster import KMeans


def recommend_pricing(
    competitors: list[dict],
    alibaba_cost: Optional[float] = None,
) -> dict:
    """Analyze competitor pricing and recommend entry strategies.

    Parameters
    ----------
    competitors : list[dict]
        Competitor dicts with ``"price"``, ``"rating"``, ``"review_count"``,
        and ``"bought_last_month"`` keys.
    alibaba_cost : float | None
        Optional Alibaba unit cost for margin calculations.

    Returns
    -------
    dict with keys:
        - strategies: dict with "budget", "competitive", "premium" entries
        - price_clusters: list of cluster center prices
        - price_gap_opportunities: list of price ranges with no competitors
        - summary_stats: percentile data
    """
    if not competitors:
        return _empty_result()

    prices = [c["price"] for c in competitors if c.get("price") is not None and c["price"] > 0]
    if not prices:
        return _empty_result()

    sorted_prices = sorted(prices)
    n = len(sorted_prices)

    # --- Percentiles ---
    p10 = float(np.percentile(sorted_prices, 10))
    p25 = float(np.percentile(sorted_prices, 25))
    p50 = float(np.percentile(sorted_prices, 50))
    p75 = float(np.percentile(sorted_prices, 75))
    p90 = float(np.percentile(sorted_prices, 90))

    # --- K-Means price clusters ---
    clusters = _compute_clusters(sorted_prices)

    # --- Demand estimation per price tier ---
    bought_data = []
    for c in competitors:
        price = c.get("price")
        bought = _parse_bought(c.get("bought_last_month"))
        if price is not None and price > 0 and bought is not None:
            bought_data.append((price, bought))

    # Estimate monthly units at each strategy price
    budget_units = _estimate_units_at_price(p25, bought_data)
    competitive_units = _estimate_units_at_price(p50, bought_data)
    premium_units = _estimate_units_at_price(p75, bought_data)

    # --- Build strategies ---
    strategies = {
        "budget": {
            "price": round(p25, 2),
            "rationale": f"Undercut 75% of the market. Positioned at the 25th percentile (${p25:.2f}) to attract price-sensitive buyers.",
            "estimated_monthly_units": budget_units,
            "estimated_monthly_revenue": round(p25 * budget_units, 2),
        },
        "competitive": {
            "price": round(p50, 2),
            "rationale": f"Match the median market price (${p50:.2f}). Balanced positioning to compete on value and features.",
            "estimated_monthly_units": competitive_units,
            "estimated_monthly_revenue": round(p50 * competitive_units, 2),
        },
        "premium": {
            "price": round(p75, 2),
            "rationale": f"Position as premium at the 75th percentile (${p75:.2f}). Target quality-focused buyers willing to pay more.",
            "estimated_monthly_units": premium_units,
            "estimated_monthly_revenue": round(p75 * premium_units, 2),
        },
    }

    # Add margin info if cost is provided
    if alibaba_cost is not None and alibaba_cost > 0:
        for key in strategies:
            sp = strategies[key]["price"]
            margin = ((sp - alibaba_cost) / sp) * 100 if sp > 0 else 0
            strategies[key]["margin_percent"] = round(margin, 1)
            strategies[key]["profit_per_unit"] = round(sp - alibaba_cost, 2)

    # --- Price gap opportunities ---
    gaps = _find_price_gaps(sorted_prices)

    return {
        "strategies": strategies,
        "price_clusters": clusters,
        "price_gap_opportunities": gaps,
        "summary_stats": {
            "p10": round(p10, 2),
            "p25": round(p25, 2),
            "p50": round(p50, 2),
            "p75": round(p75, 2),
            "p90": round(p90, 2),
            "min": round(sorted_prices[0], 2),
            "max": round(sorted_prices[-1], 2),
            "count": n,
        },
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_clusters(prices: list[float]) -> list[float]:
    """Run k-means with k=3 on prices and return sorted cluster centers."""
    if len(prices) < 3:
        return sorted(prices)

    k = min(3, len(prices))
    arr = np.array(prices).reshape(-1, 1)
    try:
        km = KMeans(n_clusters=k, n_init=10, random_state=42)
        km.fit(arr)
        centers = sorted(float(c) for c in km.cluster_centers_.flatten())
        return [round(c, 2) for c in centers]
    except Exception:
        # Fallback: return simple tercile averages
        third = len(prices) // 3
        if third == 0:
            return [round(statistics.mean(prices), 2)]
        low = statistics.mean(prices[:third])
        mid = statistics.mean(prices[third : 2 * third])
        high = statistics.mean(prices[2 * third :])
        return [round(low, 2), round(mid, 2), round(high, 2)]


def _parse_bought(value) -> Optional[int]:
    """Parse 'X+ bought in past month' or numeric values into an int."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        # Extract leading number from strings like "1K+ bought in past month"
        cleaned = value.lower().replace(",", "").strip()
        if not cleaned:
            return None
        # Handle "1K+", "10K+" style
        if "k" in cleaned:
            cleaned = cleaned.split("k")[0].strip().rstrip("+").strip()
            try:
                return int(float(cleaned) * 1000)
            except (ValueError, TypeError):
                return None
        # Extract first number
        import re
        match = re.search(r"(\d+)", cleaned)
        if match:
            return int(match.group(1))
    return None


def _estimate_units_at_price(target_price: float, bought_data: list[tuple[float, int]]) -> int:
    """Estimate monthly units at a given price based on observed price/demand data."""
    if not bought_data:
        return 0

    # Simple approach: weighted average of nearby competitors' bought_last_month
    # Weight by inverse price distance
    total_weight = 0.0
    weighted_units = 0.0
    for price, units in bought_data:
        distance = abs(price - target_price) + 1.0  # +1 to avoid division by zero
        weight = 1.0 / distance
        total_weight += weight
        weighted_units += weight * units

    if total_weight == 0:
        return 0
    return max(1, int(weighted_units / total_weight))


def _find_price_gaps(sorted_prices: list[float]) -> list[dict]:
    """Find price ranges where no competitors exist."""
    if len(sorted_prices) < 2:
        return []

    gaps = []
    median_price = statistics.median(sorted_prices)
    # A gap is significant if the distance between consecutive prices is > 20% of median
    threshold = median_price * 0.20 if median_price > 0 else 5.0

    for i in range(len(sorted_prices) - 1):
        gap = sorted_prices[i + 1] - sorted_prices[i]
        if gap >= threshold:
            gaps.append({
                "low": round(sorted_prices[i], 2),
                "high": round(sorted_prices[i + 1], 2),
                "gap_size": round(gap, 2),
                "midpoint": round((sorted_prices[i] + sorted_prices[i + 1]) / 2, 2),
            })

    # Sort by gap size descending
    gaps.sort(key=lambda g: g["gap_size"], reverse=True)
    return gaps


def _empty_result() -> dict:
    return {
        "strategies": {},
        "price_clusters": [],
        "price_gap_opportunities": [],
        "summary_stats": {},
    }
