"""Market demand estimation from Amazon competitor data."""
import statistics
from typing import Optional

from src.services.utils import parse_bought as _parse_bought


def estimate_demand(competitors: list[dict]) -> dict:
    """Estimate total market demand and revenue from competitor data.

    Parameters
    ----------
    competitors : list[dict]
        Competitor dicts with ``"price"``, ``"rating"``, ``"review_count"``,
        and ``"bought_last_month"`` keys.

    Returns
    -------
    dict with keys:
        - total_monthly_units, total_monthly_revenue, avg_monthly_revenue_per_seller
        - market_size_category ("small" / "medium" / "large")
        - demand_confidence (0-100 based on data quality)
        - top_sellers: list of dicts for top revenue competitors
        - review_velocity_avg: estimated average reviews per month
    """
    if not competitors:
        return _empty_result()

    monthly_units: list[int] = []
    monthly_revenues: list[float] = []
    review_counts: list[int] = []
    prices_with_demand: list[tuple[float, int]] = []

    for c in competitors:
        bought = _parse_bought(c.get("bought_last_month"))
        price = c.get("price")
        review_count = c.get("review_count")

        if bought is not None and bought > 0:
            monthly_units.append(bought)
            if price is not None and price > 0:
                revenue = bought * price
                monthly_revenues.append(revenue)
                prices_with_demand.append((price, bought))

        if review_count is not None:
            review_counts.append(review_count)

    total_monthly_units = sum(monthly_units)
    total_monthly_revenue = sum(monthly_revenues)
    sellers_with_data = len(monthly_revenues)
    avg_revenue = (total_monthly_revenue / sellers_with_data) if sellers_with_data > 0 else 0.0

    # Market size category
    market_size = _categorize_market(total_monthly_revenue, total_monthly_units)

    # Demand confidence: how much data do we actually have?
    confidence = _compute_confidence(competitors, monthly_units, monthly_revenues)

    # Review velocity estimate (reviews / estimated product age in months)
    review_velocity = _estimate_review_velocity(review_counts)

    # Top sellers by estimated revenue
    top_sellers = _get_top_sellers(competitors)

    return {
        "total_monthly_units": total_monthly_units,
        "total_monthly_revenue": round(total_monthly_revenue, 2),
        "avg_monthly_revenue_per_seller": round(avg_revenue, 2),
        "sellers_with_demand_data": sellers_with_data,
        "market_size_category": market_size,
        "demand_confidence": round(confidence, 1),
        "review_velocity_avg": round(review_velocity, 1),
        "top_sellers": top_sellers,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _categorize_market(total_revenue: float, total_units: int) -> str:
    """Classify market size based on estimated total monthly revenue and units."""
    if total_revenue >= 500_000 or total_units >= 50_000:
        return "large"
    if total_revenue >= 50_000 or total_units >= 5_000:
        return "medium"
    return "small"


def _compute_confidence(
    competitors: list[dict],
    monthly_units: list[int],
    monthly_revenues: list[float],
) -> float:
    """Compute a 0-100 confidence score based on data quality and coverage."""
    total = len(competitors)
    if total == 0:
        return 0.0

    score = 0.0

    # Factor 1: Percentage of competitors with demand data (0-40 pts)
    demand_coverage = len(monthly_units) / total
    score += demand_coverage * 40

    # Factor 2: Percentage of competitors with price data (0-25 pts)
    priced = sum(1 for c in competitors if c.get("price") is not None and c["price"] > 0)
    price_coverage = priced / total
    score += price_coverage * 25

    # Factor 3: Sample size bonus (0-20 pts)
    if total >= 20:
        score += 20
    elif total >= 10:
        score += 15
    elif total >= 5:
        score += 10
    else:
        score += total * 2

    # Factor 4: Revenue data consistency (0-15 pts)
    if len(monthly_revenues) >= 3:
        mean_rev = statistics.mean(monthly_revenues)
        stdev_rev = statistics.stdev(monthly_revenues)
        cv = stdev_rev / mean_rev if mean_rev > 0 else 0
        # Lower coefficient of variation = more consistent = higher confidence
        if cv < 1.0:
            score += 15
        elif cv < 2.0:
            score += 10
        else:
            score += 5
    elif monthly_revenues:
        score += 5

    return min(score, 100.0)


def _estimate_review_velocity(review_counts: list[int]) -> float:
    """Estimate average reviews per month across products.

    Assumes an average product age of 12 months as a rough heuristic.
    """
    if not review_counts:
        return 0.0
    avg_reviews = statistics.mean(review_counts)
    # Rough estimate: average Amazon product is ~12 months old
    estimated_age_months = 12
    return avg_reviews / estimated_age_months


def _get_top_sellers(competitors: list[dict], limit: int = 5) -> list[dict]:
    """Return top sellers by estimated monthly revenue."""
    scored: list[dict] = []
    for c in competitors:
        bought = _parse_bought(c.get("bought_last_month"))
        price = c.get("price")
        if bought is not None and bought > 0 and price is not None and price > 0:
            revenue = bought * price
            scored.append({
                "title": (c.get("title") or "")[:80],
                "asin": c.get("asin"),
                "price": round(price, 2),
                "monthly_units": bought,
                "estimated_monthly_revenue": round(revenue, 2),
            })
    scored.sort(key=lambda x: x["estimated_monthly_revenue"], reverse=True)
    return scored[:limit]


def _empty_result() -> dict:
    return {
        "total_monthly_units": 0,
        "total_monthly_revenue": 0.0,
        "avg_monthly_revenue_per_seller": 0.0,
        "sellers_with_demand_data": 0,
        "market_size_category": "small",
        "demand_confidence": 0.0,
        "review_velocity_avg": 0.0,
        "top_sellers": [],
    }
