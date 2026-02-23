"""Brand Moat Detector -- classify sellers and compute brand concentration metrics."""

from __future__ import annotations

_AMAZON_KEYWORDS = {"amazon", "amzn"}
_CHINESE_COUNTRIES = {"CN", "HK"}
_ESTABLISHED_MARKERS = {
    "llc", "inc", "ltd", "corp", "co.", "gmbh", "s.a.", "pty",
}


def classify_seller(
    brand: str | None,
    manufacturer: str | None,
    seller: str | None,
    seller_country: str | None,
) -> str:
    """Classify a seller into one of five categories.

    Returns one of:
        "amazon_1p", "established_brand", "private_label",
        "chinese_commodity", "unknown"
    """
    brand_l = (brand or "").strip().lower()
    seller_l = (seller or "").strip().lower()
    mfr_l = (manufacturer or "").strip().lower()
    country = (seller_country or "").strip().upper()

    # 1. Amazon first-party
    if any(kw in seller_l for kw in _AMAZON_KEYWORDS):
        return "amazon_1p"

    # 2. Chinese commodity: seller country CN/HK with no meaningful brand
    if country in _CHINESE_COUNTRIES and not brand_l:
        return "chinese_commodity"

    # 3. Established brand: brand contains domain-like patterns or corporate suffixes
    combined = f"{brand_l} {mfr_l}"
    if ".com" in combined or ".co" in combined:
        return "established_brand"
    if any(marker in combined for marker in _ESTABLISHED_MARKERS):
        return "established_brand"

    # 4. Has a non-trivial brand -> private label
    if brand_l and brand_l not in ("unknown", "generic", "unbranded", "n/a", "-"):
        return "private_label"

    # 5. Fallback
    return "unknown"


def compute_brand_concentration(competitors: list[dict]) -> dict:
    """Compute brand concentration metrics from a list of competitor dicts.

    Each competitor dict should include: brand, manufacturer, seller,
    seller_country, and optionally monthly_revenue or price + position.

    Returns
    -------
    dict with keys:
        hhi_score, amazon_1p_count, established_brand_count,
        private_label_count, chinese_commodity_count, unknown_count,
        concentration_level, has_amazon_1p, brand_moat_score,
        seller_type_distribution (for pie chart)
    """
    if not competitors:
        return _empty_concentration()

    # Classify each competitor
    classifications: list[str] = []
    brand_revenues: dict[str, float] = {}

    for c in competitors:
        cls = classify_seller(
            brand=c.get("brand"),
            manufacturer=c.get("manufacturer"),
            seller=c.get("seller"),
            seller_country=c.get("seller_country"),
        )
        classifications.append(cls)

        # Revenue proxy for HHI: use monthly_revenue, else price * position-weight
        brand_key = (c.get("brand") or "Unknown").strip() or "Unknown"
        rev = c.get("monthly_revenue") or 0
        if not rev:
            price = c.get("price") or 0
            position = c.get("position") or 1
            # Inverse position weight: top positions get more weight
            rev = price * (100 / max(position, 1))
        brand_revenues[brand_key] = brand_revenues.get(brand_key, 0) + rev

    # Counts by seller type
    counts = {
        "amazon_1p": 0,
        "established_brand": 0,
        "private_label": 0,
        "chinese_commodity": 0,
        "unknown": 0,
    }
    for cls in classifications:
        counts[cls] = counts.get(cls, 0) + 1

    # HHI: sum of squared market share percentages
    total_rev = sum(brand_revenues.values())
    hhi = 0.0
    if total_rev > 0:
        for rev in brand_revenues.values():
            share_pct = (rev / total_rev) * 100
            hhi += share_pct ** 2

    # Concentration level
    if hhi >= 2500:
        concentration_level = "high"
    elif hhi >= 1500:
        concentration_level = "medium"
    else:
        concentration_level = "low"

    has_amazon_1p = counts["amazon_1p"] > 0

    # Brand moat score (0-100): opportunity score
    # High fragmentation + many private labels = high score (opportunity)
    # High concentration or Amazon 1P = low score (threat)
    score = 50.0  # neutral start

    # HHI factor: low HHI = fragmented = opportunity
    if hhi < 1000:
        score += 25
    elif hhi < 1500:
        score += 15
    elif hhi < 2500:
        score += 0
    elif hhi < 4000:
        score -= 15
    else:
        score -= 25

    # Amazon 1P penalty
    total = len(competitors)
    amazon_pct = counts["amazon_1p"] / total if total > 0 else 0
    if amazon_pct > 0.1:
        score -= 20
    elif has_amazon_1p:
        score -= 10

    # Chinese commodity bonus (easy to outcompete)
    chinese_pct = counts["chinese_commodity"] / total if total > 0 else 0
    if chinese_pct > 0.3:
        score += 15
    elif chinese_pct > 0.1:
        score += 8

    # Private label heavy = fragmented opportunity
    pl_pct = counts["private_label"] / total if total > 0 else 0
    if pl_pct > 0.5:
        score += 10
    elif pl_pct > 0.3:
        score += 5

    score = max(0, min(int(round(score)), 100))

    # Distribution for pie chart
    seller_type_distribution = [
        {"name": "Amazon 1P", "value": counts["amazon_1p"]},
        {"name": "Established Brand", "value": counts["established_brand"]},
        {"name": "Private Label", "value": counts["private_label"]},
        {"name": "Chinese Commodity", "value": counts["chinese_commodity"]},
        {"name": "Unknown", "value": counts["unknown"]},
    ]
    # Filter out zero entries
    seller_type_distribution = [d for d in seller_type_distribution if d["value"] > 0]

    return {
        "hhi_score": round(hhi, 1),
        "amazon_1p_count": counts["amazon_1p"],
        "established_brand_count": counts["established_brand"],
        "private_label_count": counts["private_label"],
        "chinese_commodity_count": counts["chinese_commodity"],
        "unknown_count": counts["unknown"],
        "concentration_level": concentration_level,
        "has_amazon_1p": has_amazon_1p,
        "brand_moat_score": score,
        "seller_type_distribution": seller_type_distribution,
    }


def _empty_concentration() -> dict:
    return {
        "hhi_score": 0.0,
        "amazon_1p_count": 0,
        "established_brand_count": 0,
        "private_label_count": 0,
        "chinese_commodity_count": 0,
        "unknown_count": 0,
        "concentration_level": "low",
        "has_amazon_1p": False,
        "brand_moat_score": 50,
        "seller_type_distribution": [],
    }
