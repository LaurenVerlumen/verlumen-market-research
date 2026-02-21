"""Amazon fee calculator for profitability analysis.

Estimates referral fees, FBA fulfillment fees, and monthly storage costs
to provide realistic profit margins.

Fee schedule source: Amazon Seller Central Fee Schedule
Last updated: 2025 Q4 (effective Jan 15, 2025 -- Dec 31, 2026)
Rates reflect the 2025-2026 Amazon FBA fee structure including
inbound placement service fees and aged inventory surcharges.
"""

# Fee version identifier -- update whenever fee tables are refreshed
FEE_VERSION = "2025-Q4"


def get_fee_version() -> str:
    """Return the version string of the current fee schedule."""
    return FEE_VERSION


# Amazon referral fee percentages by category slug (2025-2026 rates)
_REFERRAL_FEES: dict[str, float] = {
    "toys-and-games": 0.15,
    "baby": 0.08,
    "arts-crafts-and-sewing": 0.15,
    "home-and-kitchen": 0.15,
    "kitchen-and-dining": 0.15,
    "beauty-and-personal-care": 0.08,
    "health-and-household": 0.08,
    "sports-and-outdoors": 0.15,
    "tools-and-home-improvement": 0.15,
    "electronics": 0.08,
    "clothing-shoes-and-jewelry": 0.17,
    "pet-supplies": 0.15,
    "office-products": 0.15,
    "automotive": 0.12,
    "grocery-and-gourmet-food": 0.08,
    "patio-lawn-and-garden": 0.15,
    "industrial-and-scientific": 0.12,
    "cell-phones-and-accessories": 0.08,
    "computers-and-accessories": 0.08,
    "musical-instruments": 0.15,
    "appliances": 0.08,
    "books": 0.15,
    "video-games": 0.15,
    "handmade": 0.15,
    "collectibles-and-fine-art": 0.20,
    "watches": 0.16,
    "jewelry": 0.20,
    "luggage": 0.15,
    "furniture": 0.15,
    "mattresses": 0.15,
}

_DEFAULT_REFERRAL_FEE = 0.15

# FBA fulfillment fees by size tier (2025-2026 rates, effective Jan 15 2025)
_FBA_FEES: dict[str, float] = {
    "small-standard": 3.06,          # Small standard, up to 2oz-6oz range
    "small-standard-heavy": 3.68,    # Small standard, 12oz-16oz
    "large-standard": 4.99,          # Large standard, up to 0.5lb
    "large-standard-1lb": 5.60,      # Large standard, 0.5-1lb
    "large-standard-2lb": 6.62,      # Large standard, 1-2lb
    "large-standard-3lb": 7.17,      # Large standard, 2-3lb
    "large-standard-heavy": 7.72,    # Large standard, 3-20lb (base + $0.16/half-lb above 3lb)
    "small-oversize": 9.73,          # Small oversize
    "medium-oversize": 19.05,        # Medium oversize
    "large-oversize": 89.98,         # Large oversize
    "special-oversize": 158.49,      # Special oversize
}

# Monthly storage fee per cubic foot (2025-2026 rates)
_STORAGE_FEE_STANDARD = 0.87   # Standard size, Jan-Sep
_STORAGE_FEE_PEAK = 2.40       # Standard size, Oct-Dec (peak season)

# Aged inventory surcharge (per cubic foot, assessed monthly)
_AGED_INVENTORY_SURCHARGE_271_365 = 6.90   # 271-365 days
_AGED_INVENTORY_SURCHARGE_365_PLUS = 6.90  # 365+ days (same base, may stack)

# Default PPC advertising cost as percentage of selling price
_DEFAULT_PPC_PCT = 0.10

# Default shipping cost per unit (Alibaba -> Amazon FBA warehouse)
_DEFAULT_SHIPPING = 3.00


def calculate_fees(
    selling_price: float,
    category: str = "toys-and-games",
    weight_lbs: float = 1.0,
    size_tier: str = "standard",
    shipping_cost: float | None = None,
    ppc_pct: float | None = None,
    include_storage: bool = True,
) -> dict:
    """Calculate estimated Amazon fees for a product.

    Parameters
    ----------
    selling_price : float
        The planned selling price on Amazon.
    category : str
        Product category slug for referral fee lookup.
    weight_lbs : float
        Estimated product weight in pounds (affects FBA tier).
    size_tier : str
        One of "standard", "large-standard", "small-oversize", etc.
        If "standard", automatically picks small vs large by weight.
    shipping_cost : float | None
        Inbound shipping cost per unit. Defaults to $3.00.
    ppc_pct : float | None
        PPC advertising cost as a fraction of selling price. Defaults to 0.10.
    include_storage : bool
        Whether to include monthly storage estimate.

    Returns
    -------
    dict with keys: referral_fee, referral_fee_pct, fba_fee, storage_fee,
        shipping_cost, ppc_cost, total_fees, net_after_fees.
    """
    if selling_price <= 0:
        return _zero_result()

    # Referral fee
    referral_pct = _REFERRAL_FEES.get(category, _DEFAULT_REFERRAL_FEE)
    referral_fee = round(selling_price * referral_pct, 2)

    # FBA fulfillment fee
    fba_fee = _get_fba_fee(size_tier, weight_lbs)

    # Storage fee (assume 0.5 cubic foot per unit as default estimate)
    storage_fee = round(_STORAGE_FEE_STANDARD * 0.5, 2) if include_storage else 0.0

    # Shipping cost
    ship = shipping_cost if shipping_cost is not None else _DEFAULT_SHIPPING

    # PPC cost
    ppc = ppc_pct if ppc_pct is not None else _DEFAULT_PPC_PCT
    ppc_cost = round(selling_price * ppc, 2)

    total_fees = round(referral_fee + fba_fee + storage_fee + ship + ppc_cost, 2)
    net = round(selling_price - total_fees, 2)

    return {
        "referral_fee": referral_fee,
        "referral_fee_pct": referral_pct,
        "fba_fee": fba_fee,
        "storage_fee": storage_fee,
        "shipping_cost": round(ship, 2),
        "ppc_cost": ppc_cost,
        "ppc_pct": ppc,
        "total_fees": total_fees,
        "net_after_fees": net,
    }


def get_referral_fee_pct(category: str = "toys-and-games") -> float:
    """Return the referral fee percentage for a category."""
    return _REFERRAL_FEES.get(category, _DEFAULT_REFERRAL_FEE)


def available_categories() -> list[str]:
    """Return list of known category slugs."""
    return sorted(_REFERRAL_FEES.keys())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_fba_fee(size_tier: str, weight_lbs: float) -> float:
    """Determine FBA fulfillment fee from size tier and weight (2025-2026 rates)."""
    tier = size_tier.lower().strip()

    # Auto-detect standard tier based on weight
    if tier == "standard":
        if weight_lbs <= 0.75:
            # Small standard size (up to ~12oz)
            return _FBA_FEES["small-standard"]
        elif weight_lbs <= 1.0:
            return _FBA_FEES["large-standard-1lb"]
        elif weight_lbs <= 2.0:
            return _FBA_FEES["large-standard-2lb"]
        elif weight_lbs <= 3.0:
            return _FBA_FEES["large-standard-3lb"]
        else:
            # 3-20lb: base fee + per-half-lb surcharge above 3lb
            base = _FBA_FEES["large-standard-heavy"]
            extra_half_lbs = max(0, (weight_lbs - 3.0) / 0.5)
            return round(base + extra_half_lbs * 0.16, 2)

    # Explicit tier names
    if tier in _FBA_FEES:
        return _FBA_FEES[tier]

    return _FBA_FEES.get("large-standard", 4.99)


def _zero_result() -> dict:
    return {
        "referral_fee": 0.0,
        "referral_fee_pct": 0.0,
        "fba_fee": 0.0,
        "storage_fee": 0.0,
        "shipping_cost": 0.0,
        "ppc_cost": 0.0,
        "ppc_pct": 0.0,
        "total_fees": 0.0,
        "net_after_fees": 0.0,
    }
