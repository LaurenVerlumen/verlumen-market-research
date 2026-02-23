"""Verlumen Viability Score (VVS) -- multi-dimensional product scoring engine."""
import statistics
from typing import Optional

from src.services.utils import parse_bought as _parse_bought
from src.services.brand_moat import compute_brand_concentration


# Configurable dimension weights (must sum to 1.0)
_WEIGHTS = {
    "demand": 0.25,
    "competition": 0.25,
    "profitability": 0.25,
    "market_quality": 0.10,
    "differentiation": 0.05,
    "brand_moat": 0.10,
}

# Verdict thresholds
_VERDICTS = [
    (8.0, "STRONG GO", "green"),
    (6.0, "CONDITIONAL GO", "yellow"),
    (4.0, "CAUTION", "orange"),
    (0.0, "NO GO", "red"),
]


def calculate_vvs(
    product,
    competitors: list[dict],
    alibaba_cost: Optional[float] = None,
) -> dict:
    """Calculate the Verlumen Viability Score across 5 dimensions.

    Parameters
    ----------
    product : Product ORM object or dict-like with alibaba_price_min/max.
    competitors : list[dict]
        Competitor dicts with price, rating, review_count, bought_last_month,
        badge, is_prime, is_sponsored keys.
    alibaba_cost : float | None
        Alibaba unit cost for profitability estimation.

    Returns
    -------
    dict with vvs_score, verdict, verdict_color, dimensions, recommendation.
    """
    if not competitors:
        return _empty_result()

    demand = _score_demand(competitors)
    competition = _score_competition(competitors)
    profitability = _score_profitability(competitors, alibaba_cost)
    market_quality = _score_market_quality(competitors)
    differentiation = _score_differentiation(competitors)
    brand_moat = _score_brand_moat(competitors)

    dimensions = {
        "demand": {"score": demand[0], "weight": _WEIGHTS["demand"], "details": demand[1]},
        "competition": {"score": competition[0], "weight": _WEIGHTS["competition"], "details": competition[1]},
        "profitability": {"score": profitability[0], "weight": _WEIGHTS["profitability"], "details": profitability[1]},
        "market_quality": {"score": market_quality[0], "weight": _WEIGHTS["market_quality"], "details": market_quality[1]},
        "differentiation": {"score": differentiation[0], "weight": _WEIGHTS["differentiation"], "details": differentiation[1]},
        "brand_moat": {"score": brand_moat[0], "weight": _WEIGHTS["brand_moat"], "details": brand_moat[1]},
    }

    composite = sum(
        dimensions[dim]["score"] * dimensions[dim]["weight"]
        for dim in dimensions
    )
    composite = round(composite, 1)

    verdict, verdict_color = _get_verdict(composite)
    recommendation = _build_recommendation(composite, dimensions)

    return {
        "vvs_score": composite,
        "verdict": verdict,
        "verdict_color": verdict_color,
        "dimensions": dimensions,
        "recommendation": recommendation,
    }


# ---------------------------------------------------------------------------
# Dimension scorers -- each returns (score: int, details: str)
# ---------------------------------------------------------------------------

def _score_demand(competitors: list[dict]) -> tuple[int, str]:
    """Score demand 1-10 based on bought_last_month data, competitor count, avg price."""
    total = len(competitors)
    bought_values: list[int] = []
    for c in competitors:
        b = _parse_bought(c.get("bought_last_month"))
        if b is not None and b > 0:
            bought_values.append(b)

    prices = [c["price"] for c in competitors if c.get("price") is not None and c["price"] > 0]
    avg_price = statistics.mean(prices) if prices else 0.0

    bought_ratio = len(bought_values) / total if total > 0 else 0
    avg_bought = statistics.mean(bought_values) if bought_values else 0

    score = 1
    details_parts = []

    # Competitor count signal
    if total >= 15:
        score += 2
        details_parts.append(f"{total} competitors (proven market)")
    elif total >= 8:
        score += 1
        details_parts.append(f"{total} competitors")
    else:
        details_parts.append(f"Only {total} competitors")

    # Bought last month data coverage
    if bought_ratio >= 0.5 and avg_bought >= 100:
        score += 4
        details_parts.append(f"{len(bought_values)} with sales data, avg {avg_bought:.0f}/mo")
    elif bought_ratio >= 0.3 and avg_bought >= 50:
        score += 3
        details_parts.append(f"{len(bought_values)} with sales data")
    elif bought_ratio >= 0.1:
        score += 2
        details_parts.append("Some demand signals")
    else:
        details_parts.append("Limited demand data")

    # Price level bonus
    if avg_price >= 25:
        score += 2
        details_parts.append(f"Avg ${avg_price:.0f} (healthy market)")
    elif avg_price >= 12:
        score += 1
        details_parts.append(f"Avg ${avg_price:.0f}")

    score = max(1, min(score, 10))
    return score, "; ".join(details_parts)


def _score_competition(competitors: list[dict]) -> tuple[int, str]:
    """Score competition 1-10 (HIGH competition = LOW score)."""
    total = len(competitors)
    if total == 0:
        return 5, "No data"

    reviews = [c.get("review_count") or 0 for c in competitors]
    badges = [c.get("badge") or "" for c in competitors]

    # Top 10 competitors by review count
    top_reviews = sorted(reviews, reverse=True)[:10]
    avg_top_reviews = statistics.mean(top_reviews) if top_reviews else 0

    has_best_seller = any("Best Seller" in b for b in badges)
    has_amazon_choice = any("Amazon" in b and "Choice" in b for b in badges)
    established_pct = sum(1 for r in reviews if r >= 500) / total if total > 0 else 0

    # Brand concentration: check how many unique price clusters exist
    # (proxy for brand diversity)

    details_parts = []

    # Start from 10 (best = low competition) and subtract
    score = 10

    # Avg top reviews penalty
    if avg_top_reviews >= 5000:
        score -= 4
        details_parts.append(f"Top 10 avg {avg_top_reviews:.0f} reviews (very established)")
    elif avg_top_reviews >= 2000:
        score -= 3
        details_parts.append(f"Top 10 avg {avg_top_reviews:.0f} reviews (established)")
    elif avg_top_reviews >= 500:
        score -= 2
        details_parts.append(f"Top 10 avg {avg_top_reviews:.0f} reviews")
    else:
        details_parts.append(f"Top 10 avg {avg_top_reviews:.0f} reviews (low barrier)")

    # Badge penalty
    if has_best_seller and has_amazon_choice:
        score -= 2
        details_parts.append("Best Seller + Amazon's Choice present")
    elif has_best_seller or has_amazon_choice:
        score -= 1
        badge_name = "Best Seller" if has_best_seller else "Amazon's Choice"
        details_parts.append(f"{badge_name} present")

    # Established players penalty
    if established_pct >= 0.5:
        score -= 2
        details_parts.append(f"{established_pct:.0%} have 500+ reviews")
    elif established_pct >= 0.25:
        score -= 1
        details_parts.append(f"{established_pct:.0%} have 500+ reviews")

    score = max(1, min(score, 10))
    return score, "; ".join(details_parts)


def _score_profitability(competitors: list[dict], alibaba_cost: Optional[float]) -> tuple[int, str]:
    """Score profitability 1-10 based on margin after estimated fees."""
    prices = [c["price"] for c in competitors if c.get("price") is not None and c["price"] > 0]
    if not prices:
        return 5, "No price data"

    avg_amazon_price = statistics.mean(prices)

    if alibaba_cost is None or alibaba_cost <= 0:
        return 5, f"No Alibaba cost; avg Amazon ${avg_amazon_price:.2f} (neutral)"

    # Estimate fees: ~15% referral + ~$4 FBA
    estimated_fee_pct = 0.15
    estimated_fba = 4.0
    total_fees = avg_amazon_price * estimated_fee_pct + estimated_fba
    net = avg_amazon_price - total_fees - alibaba_cost
    margin_pct = (net / avg_amazon_price * 100) if avg_amazon_price > 0 else 0

    details = f"Est. margin {margin_pct:.0f}% (avg ${avg_amazon_price:.2f} - cost ${alibaba_cost:.2f} - fees ${total_fees:.2f})"

    if margin_pct > 50:
        return 10, details
    elif margin_pct > 40:
        return 9, details
    elif margin_pct > 30:
        return 8, details
    elif margin_pct > 20:
        return 6, details
    elif margin_pct > 10:
        return 4, details
    elif margin_pct > 0:
        return 2, details
    else:
        return 1, details


def _score_market_quality(competitors: list[dict]) -> tuple[int, str]:
    """Score market quality 1-10 based on price spread, diversity, Prime %."""
    prices = [c["price"] for c in competitors if c.get("price") is not None and c["price"] > 0]
    total = len(competitors)

    if not prices or total == 0:
        return 5, "Insufficient data"

    price_min = min(prices)
    price_max = max(prices)
    price_mean = statistics.mean(prices)
    spread = price_max - price_min
    coeff_var = (statistics.stdev(prices) / price_mean) if len(prices) >= 2 and price_mean > 0 else 0

    prime_count = sum(1 for c in competitors if c.get("is_prime"))
    prime_pct = prime_count / total

    # Review velocity proxy: avg reviews / avg position (higher = faster growth)
    reviews_with_pos = [
        (c.get("review_count") or 0, c.get("position") or 1)
        for c in competitors
        if c.get("review_count") is not None
    ]
    avg_velocity = (
        statistics.mean(r / max(p, 1) for r, p in reviews_with_pos)
        if reviews_with_pos else 0
    )

    details_parts = []
    score = 5  # Start neutral

    # Price spread: wide = room for positioning
    if coeff_var >= 0.5:
        score += 2
        details_parts.append(f"Wide price spread (${price_min:.0f}-${price_max:.0f})")
    elif coeff_var >= 0.25:
        score += 1
        details_parts.append(f"Moderate spread (${price_min:.0f}-${price_max:.0f})")
    else:
        score -= 1
        details_parts.append(f"Narrow spread (${price_min:.0f}-${price_max:.0f})")

    # Prime percentage: >80% = mature market (slightly negative), 40-80% = healthy
    if prime_pct > 0.8:
        score -= 1
        details_parts.append(f"{prime_pct:.0%} Prime (very mature)")
    elif prime_pct >= 0.4:
        score += 1
        details_parts.append(f"{prime_pct:.0%} Prime (healthy)")
    else:
        details_parts.append(f"{prime_pct:.0%} Prime")

    # Competitor diversity
    if total >= 15 and coeff_var >= 0.3:
        score += 1
        details_parts.append("Diverse market")

    score = max(1, min(score, 10))
    return score, "; ".join(details_parts)


def _score_differentiation(competitors: list[dict]) -> tuple[int, str]:
    """Score differentiation opportunity 1-10 based on listing quality gaps."""
    if not competitors:
        return 5, "No data"

    ratings = [c.get("rating") for c in competitors if c.get("rating") is not None]
    reviews = [c.get("review_count") or 0 for c in competitors]
    total = len(competitors)

    avg_rating = statistics.mean(ratings) if ratings else 0
    details_parts = []
    score = 5

    # Low ratings = customer dissatisfaction = opportunity
    if avg_rating < 3.5:
        score += 3
        details_parts.append(f"Avg rating {avg_rating:.1f} (high dissatisfaction)")
    elif avg_rating < 4.0:
        score += 2
        details_parts.append(f"Avg rating {avg_rating:.1f} (some dissatisfaction)")
    elif avg_rating < 4.3:
        score += 1
        details_parts.append(f"Avg rating {avg_rating:.1f}")
    else:
        details_parts.append(f"Avg rating {avg_rating:.1f} (well-served)")

    # Weak listings: products with few reviews but decent ratings
    # (implies they're new or have weak marketing -- opportunity to outperform)
    weak_listings = sum(
        1 for c in competitors
        if (c.get("review_count") or 0) < 50 and (c.get("rating") or 0) >= 3.5
    )
    weak_pct = weak_listings / total if total > 0 else 0
    if weak_pct >= 0.3:
        score += 2
        details_parts.append(f"{weak_listings} weak listings ({weak_pct:.0%})")
    elif weak_pct >= 0.15:
        score += 1
        details_parts.append(f"{weak_listings} weak listings")

    # Many low-review products in top positions = beatable
    low_review_in_top = sum(
        1 for c in competitors
        if (c.get("position") or 99) <= 10 and (c.get("review_count") or 0) < 100
    )
    if low_review_in_top >= 3:
        score += 1
        details_parts.append(f"{low_review_in_top} low-review products in top 10")

    score = max(1, min(score, 10))
    return score, "; ".join(details_parts)


def _score_brand_moat(competitors: list[dict]) -> tuple[int, str]:
    """Score brand moat 1-10 based on brand concentration and seller types."""
    if not competitors:
        return 5, "No data"

    conc = compute_brand_concentration(competitors)
    moat_score = conc["brand_moat_score"]
    hhi = conc["hhi_score"]
    level = conc["concentration_level"]

    details_parts = []

    # Map 0-100 brand_moat_score to 1-10 VVS dimension score
    score = max(1, min(round(moat_score / 10), 10))

    # HHI context
    details_parts.append(f"HHI {hhi:.0f} ({level} concentration)")

    if conc["has_amazon_1p"]:
        details_parts.append(f"Amazon 1P present ({conc['amazon_1p_count']})")

    if conc["chinese_commodity_count"] > 0:
        details_parts.append(f"{conc['chinese_commodity_count']} Chinese commodity sellers")

    if conc["private_label_count"] > 0:
        details_parts.append(f"{conc['private_label_count']} private labels")

    return score, "; ".join(details_parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_verdict(score: float) -> tuple[str, str]:
    """Return verdict text and color based on VVS score."""
    for threshold, text, color in _VERDICTS:
        if score >= threshold:
            return text, color
    return "NO GO", "red"


def _build_recommendation(score: float, dimensions: dict) -> str:
    """Build a one-line recommendation from score and dimension data."""
    # Find strongest and weakest dimensions
    sorted_dims = sorted(dimensions.items(), key=lambda x: x[1]["score"], reverse=True)
    strongest = sorted_dims[0]
    weakest = sorted_dims[-1]

    dim_labels = {
        "demand": "demand",
        "competition": "competition level",
        "profitability": "profitability",
        "market_quality": "market quality",
        "differentiation": "differentiation opportunity",
        "brand_moat": "brand moat",
    }

    if score >= 8:
        return (
            f"Strong opportunity. Best dimension: {dim_labels[strongest[0]]} "
            f"({strongest[1]['score']}/10). Consider fast market entry."
        )
    elif score >= 6:
        return (
            f"Promising product with good {dim_labels[strongest[0]]} "
            f"({strongest[1]['score']}/10). Watch {dim_labels[weakest[0]]} "
            f"({weakest[1]['score']}/10) closely."
        )
    elif score >= 4:
        return (
            f"Proceed with caution. {dim_labels[weakest[0]].capitalize()} "
            f"is concerning ({weakest[1]['score']}/10). "
            f"Strongest aspect: {dim_labels[strongest[0]]} ({strongest[1]['score']}/10)."
        )
    else:
        return (
            f"Not recommended. Key issue: {dim_labels[weakest[0]]} "
            f"({weakest[1]['score']}/10). Consider alternative products."
        )


def _empty_result() -> dict:
    return {
        "vvs_score": 0.0,
        "verdict": "NO GO",
        "verdict_color": "red",
        "dimensions": {},
        "recommendation": "Insufficient data to score.",
    }
