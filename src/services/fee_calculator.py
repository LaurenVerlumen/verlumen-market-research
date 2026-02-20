"""Amazon fee calculator for profitability analysis.

Estimates referral fees, FBA fulfillment fees, and monthly storage costs
to provide realistic profit margins.
"""

# Amazon referral fee percentages by category slug
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
}

_DEFAULT_REFERRAL_FEE = 0.15

# FBA fulfillment fees by size tier (approximate mid-2024 rates)
_FBA_FEES: dict[str, float] = {
    "small-standard": 3.22,
    "large-standard": 4.75,
    "large-standard-heavy": 6.50,
    "small-oversize": 9.73,
    "medium-oversize": 19.05,
    "large-oversize": 89.98,
    "special-oversize": 158.49,
}

# Monthly storage fee per cubic foot (standard / Q4 peak)
_STORAGE_FEE_STANDARD = 0.87  # Jan-Sep
_STORAGE_FEE_PEAK = 2.40  # Oct-Dec

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
    """Determine FBA fulfillment fee from size tier and weight."""
    tier = size_tier.lower().strip()

    if tier in ("standard", "small-standard", "large-standard", "large-standard-heavy"):
        if tier == "standard":
            # Auto-detect based on weight
            if weight_lbs <= 0.75:
                return _FBA_FEES["small-standard"]
            elif weight_lbs <= 3.0:
                return _FBA_FEES["large-standard"]
            else:
                return _FBA_FEES["large-standard-heavy"]
        return _FBA_FEES.get(tier, _FBA_FEES["large-standard"])

    return _FBA_FEES.get(tier, _FBA_FEES["large-standard"])


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
