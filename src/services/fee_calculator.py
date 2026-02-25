"""Amazon fee calculator for profitability analysis.

Estimates referral fees, FBA fulfillment fees, and monthly storage costs
to provide realistic profit margins.

Fee schedule source: Amazon Seller Central Fee Schedule
Updated: 2026-Q1 (effective Jan 15, 2026)
Rates reflect the 2026 Amazon FBA fee structure including price-tiered
fulfillment fees, updated storage rates, and new bulky tiers.
"""

# Fee version identifier -- update whenever fee tables are refreshed
FEE_VERSION = "2026-Q1"


def get_fee_version() -> str:
    """Return the version string of the current fee schedule."""
    return FEE_VERSION


# ---------------------------------------------------------------------------
# Referral fees by category (2026 rates — unchanged from 2025)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# FBA fulfillment fees (2026, effective Jan 15, 2026)
# Price-tiered: <$10, $10-$50, >$50
# Source: sellerapp.com/blog/amazon-fba-fees-calculator-guide/
# ---------------------------------------------------------------------------

# Small Standard-Size: (max_weight_oz, fee_under_10, fee_10_50, fee_over_50)
_SMALL_STANDARD_FEES: list[tuple[float, float, float, float]] = [
    (2,  2.43, 3.32, 3.58),
    (4,  2.49, 3.42, 3.68),
    (6,  2.56, 3.45, 3.71),
    (8,  2.66, 3.54, 3.80),
    (10, 2.77, 3.68, 3.94),
    (12, 2.82, 3.78, 4.04),
    (14, 2.92, 3.91, 4.17),
    (16, 2.95, 3.96, 4.22),
]

# Large Standard-Size: (max_weight_oz, fee_under_10, fee_10_50, fee_over_50)
# For 3-20lb: base + $0.08 per 4oz above 3lb
_LARGE_STANDARD_FEES: list[tuple[float, float, float, float]] = [
    (4,  2.91, 3.73, 3.99),
    (8,  3.13, 3.95, 4.21),
    (12, 3.38, 4.20, 4.46),
    (16, 3.78, 4.60, 4.86),
    (20, 4.22, 5.04, 5.30),   # 1-1.25 lb
    (24, 4.60, 5.42, 5.68),   # 1.25-1.5 lb
    (28, 4.75, 5.57, 5.83),   # 1.5-1.75 lb
    (32, 5.00, 5.82, 6.08),   # 1.75-2 lb
    (36, 5.10, 5.92, 6.18),   # 2-2.25 lb
    (40, 5.28, 6.10, 6.36),   # 2.25-2.5 lb
    (44, 5.44, 6.26, 6.52),   # 2.5-2.75 lb
    (48, 5.85, 6.67, 6.93),   # 2.75-3 lb
]
# 3-20lb base fees (+ $0.08 per 4oz above 3lb)
_LARGE_STANDARD_HEAVY_BASE = (6.15, 6.97, 7.23)  # (under_10, 10_50, over_50)
_LARGE_STANDARD_HEAVY_PER_4OZ = 0.08

# Large Bulky: base + $0.38/lb above first lb
_LARGE_BULKY_BASE = 8.58
_LARGE_BULKY_PER_LB = 0.38

# Extra-Large: $25.56 base for 0-50lb
_EXTRA_LARGE_BASE = 25.56
_EXTRA_LARGE_PER_LB = 0.38

# Monthly storage fee per cubic foot (2026 rates)
_STORAGE_FEE_STANDARD = 0.87   # Standard size, Jan-Sep
_STORAGE_FEE_PEAK = 2.40       # Standard size, Oct-Dec (peak season)

# Aged inventory surcharge (per cubic foot, assessed monthly)
_AGED_INVENTORY_SURCHARGE_12_15M = 6.90   # 12-15 months ($0.30/unit or $6.90/ft³)
_AGED_INVENTORY_SURCHARGE_15M_PLUS = 7.90  # 15+ months ($0.35/unit or $7.90/ft³)

# Default PPC advertising cost as percentage of selling price
_DEFAULT_PPC_PCT = 0.10

# Default shipping cost per unit (Alibaba -> Amazon FBA warehouse)
_DEFAULT_SHIPPING = 3.00

# Default duties suggestion for China imports (Section 301 + IEEPA tariffs)
DEFAULT_DUTIES_PCT_CHINA = 25.0


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
    fba_fee = _get_fba_fee(size_tier, weight_lbs, selling_price)

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
# Size tier & dimension helpers
# ---------------------------------------------------------------------------

# Packaging weight estimates (lbs)
_PACKAGING_WEIGHT_STANDARD = 0.25
_PACKAGING_WEIGHT_OVERSIZE = 1.0

# Map display size tier names → internal tier key for _get_fba_fee
_SIZE_TIER_FEE_MAP = {
    "Small Standard-Size": "small-standard",
    "Large Standard-Size": "large-standard",
    "Large Bulky": "large-bulky",
    "Extra-Large": "extra-large",
}


def detect_size_tier(
    length_in: float, width_in: float, height_in: float, weight_lbs: float,
) -> str:
    """Auto-detect Amazon FBA size tier from dimensions and weight.

    Uses 2026 Amazon FBA size tier thresholds.
    """
    dims = sorted([length_in, width_in, height_in], reverse=True)
    longest, median, shortest = dims

    if longest <= 15 and median <= 12 and shortest <= 0.75 and weight_lbs <= 1.0:
        return "Small Standard-Size"
    if longest <= 18 and median <= 14 and shortest <= 8 and weight_lbs <= 20:
        return "Large Standard-Size"
    if longest <= 59 and median <= 33 and shortest <= 33 and weight_lbs <= 50:
        return "Large Bulky"
    return "Extra-Large"


def calculate_outbound_shipping_weight(
    weight_lbs: float,
    size_tier: str,
    length_in: float = 0,
    width_in: float = 0,
    height_in: float = 0,
) -> float:
    """Calculate outbound shipping weight.

    Amazon uses the *greater* of (unit weight + packaging) or dimensional weight.
    Dimensional weight = L x W x H / 139 (standard) or / 166 (oversize).
    """
    if "bulky" in size_tier.lower() or "extra" in size_tier.lower():
        pkg_weight = weight_lbs + _PACKAGING_WEIGHT_OVERSIZE
        dim_weight = (length_in * width_in * height_in) / 166
    else:
        pkg_weight = weight_lbs + _PACKAGING_WEIGHT_STANDARD
        dim_weight = (length_in * width_in * height_in) / 139
    return round(max(pkg_weight, dim_weight), 2)


def calculate_cubic_feet(
    length_in: float, width_in: float, height_in: float,
) -> float:
    """Calculate volume in cubic feet from dimensions in inches."""
    return round((length_in * width_in * height_in) / 1728, 4)


def calculate_storage_fee(
    cubic_feet: float, months: float = 1.0, season: str = "jan_sep",
) -> float:
    """Calculate monthly storage fee.

    Parameters
    ----------
    season : str
        ``"jan_sep"`` for standard rate, ``"oct_dec"`` for peak rate.
    """
    rate = _STORAGE_FEE_STANDARD if season == "jan_sep" else _STORAGE_FEE_PEAK
    return round(cubic_feet * months * rate, 2)


def calculate_freight_cost_per_unit(
    length_in: float,
    width_in: float,
    height_in: float,
    freight_mode: str = "per_cbm",
    freight_rate: float = 400.0,
) -> float:
    """Calculate freight cost per unit.

    Parameters
    ----------
    freight_mode : str
        ``"per_cbm"`` — rate is $/m³; ``"per_unit"`` — rate is direct $/unit.
    freight_rate : float
        Dollar amount per cubic meter **or** per unit.
    """
    if freight_mode == "per_unit":
        return round(freight_rate, 2)
    # Convert inches → meters (1 in = 0.0254 m)
    vol_m3 = (length_in * 0.0254) * (width_in * 0.0254) * (height_in * 0.0254)
    return round(vol_m3 * freight_rate, 2)


def _map_size_tier_to_key(display_tier: str) -> str:
    """Map display size tier string to internal fee lookup key."""
    return _SIZE_TIER_FEE_MAP.get(display_tier, "large-standard")


def calculate_detailed_profitability(
    price: float,
    unit_cost: float,
    length_in: float,
    width_in: float,
    height_in: float,
    weight_lbs: float,
    category: str = "toys-and-games",
    freight_mode: str = "per_cbm",
    freight_rate: float = 400.0,
    storage_months: float = 1.0,
    duties_mode: str = "percent",
    duties_value: float = 0.0,
    other_mode: str = "percent",
    other_value: float = 0.0,
) -> dict:
    """Full Helium-10-style profitability breakdown with seasonal results.

    Returns a dict with size_tier, outbound_weight, cubic_feet,
    unit_freight_cost, fba_fee, referral_fee, storage per season,
    duties/other costs, and net/margin/roi for Jan-Sep & Oct-Dec.
    """
    # Ensure valid minimums
    price = max(price, 0)
    unit_cost = max(unit_cost, 0)
    length_in = max(length_in, 0)
    width_in = max(width_in, 0)
    height_in = max(height_in, 0)
    weight_lbs = max(weight_lbs, 0)

    # 1. Size tier
    size_tier = detect_size_tier(length_in, width_in, height_in, weight_lbs)

    # 2. Outbound shipping weight
    outbound_weight = calculate_outbound_shipping_weight(
        weight_lbs, size_tier, length_in, width_in, height_in,
    )

    # 3. Cubic feet (for storage)
    cubic_feet = calculate_cubic_feet(length_in, width_in, height_in)

    # 4. FBA fulfillment fee (now price-aware)
    fba_fee = _get_fba_fee(
        _map_size_tier_to_key(size_tier), outbound_weight, price,
    )

    # 5. Referral fee
    referral_pct = _REFERRAL_FEES.get(category, _DEFAULT_REFERRAL_FEE)
    referral_fee = round(price * referral_pct, 2)

    # 6. Freight cost per unit
    unit_freight = calculate_freight_cost_per_unit(
        length_in, width_in, height_in, freight_mode, freight_rate,
    )

    # 7. Storage fees (seasonal)
    storage_jan_sep = calculate_storage_fee(cubic_feet, storage_months, "jan_sep")
    storage_oct_dec = calculate_storage_fee(cubic_feet, storage_months, "oct_dec")

    # 8. Duties & tariffs
    if duties_mode == "percent":
        duties_cost = round(price * duties_value / 100, 2)
    else:
        duties_cost = round(duties_value, 2)

    # 9. Other costs
    if other_mode == "percent":
        other_cost = round(price * other_value / 100, 2)
    else:
        other_cost = round(other_value, 2)

    # 10. Total costs per season
    base_costs = unit_cost + unit_freight + fba_fee + referral_fee + duties_cost + other_cost
    total_jan_sep = round(base_costs + storage_jan_sep, 2)
    total_oct_dec = round(base_costs + storage_oct_dec, 2)

    # 11. Net profit
    net_jan_sep = round(price - total_jan_sep, 2)
    net_oct_dec = round(price - total_oct_dec, 2)

    # 12. Margin & ROI
    margin_jan_sep = round((net_jan_sep / price) * 100, 2) if price > 0 else 0.0
    margin_oct_dec = round((net_oct_dec / price) * 100, 2) if price > 0 else 0.0
    total_investment = unit_cost + unit_freight + duties_cost + other_cost
    roi_jan_sep = round((net_jan_sep / total_investment) * 100, 2) if total_investment > 0 else 0.0
    roi_oct_dec = round((net_oct_dec / total_investment) * 100, 2) if total_investment > 0 else 0.0

    return {
        "size_tier": size_tier,
        "outbound_weight": outbound_weight,
        "cubic_feet": cubic_feet,
        "unit_freight_cost": unit_freight,
        "fba_fee": fba_fee,
        "referral_fee": referral_fee,
        "referral_pct": referral_pct,
        "storage_jan_sep": storage_jan_sep,
        "storage_oct_dec": storage_oct_dec,
        "duties_cost": duties_cost,
        "other_cost": other_cost,
        "total_costs_jan_sep": total_jan_sep,
        "total_costs_oct_dec": total_oct_dec,
        "net_jan_sep": net_jan_sep,
        "net_oct_dec": net_oct_dec,
        "margin_jan_sep": margin_jan_sep,
        "margin_oct_dec": margin_oct_dec,
        "roi_jan_sep": roi_jan_sep,
        "roi_oct_dec": roi_oct_dec,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _price_tier_index(price: float) -> int:
    """Return 0 for <$10, 1 for $10-$50, 2 for >$50."""
    if price < 10:
        return 0
    if price <= 50:
        return 1
    return 2


def _get_fba_fee(size_tier: str, weight_lbs: float, price: float = 25.0) -> float:
    """Determine FBA fulfillment fee from size tier, weight, and price.

    Uses 2026 price-tiered fee schedule (effective Jan 15, 2026).
    """
    tier = size_tier.lower().strip()
    pt = _price_tier_index(price)
    weight_oz = weight_lbs * 16

    # Small Standard-Size
    if tier == "small-standard":
        for max_oz, f_low, f_mid, f_high in _SMALL_STANDARD_FEES:
            if weight_oz <= max_oz:
                return (f_low, f_mid, f_high)[pt]
        # Over 16oz shouldn't happen for small standard, but fallback
        return _SMALL_STANDARD_FEES[-1][1 + pt]

    # Large Standard-Size
    if tier in ("large-standard", "standard"):
        # Check fixed weight bands (up to 3 lb / 48 oz)
        for max_oz, f_low, f_mid, f_high in _LARGE_STANDARD_FEES:
            if weight_oz <= max_oz:
                return (f_low, f_mid, f_high)[pt]
        # 3-20 lb: base + $0.08 per 4oz above 3 lb
        base = _LARGE_STANDARD_HEAVY_BASE[pt]
        extra_4oz = max(0, (weight_oz - 48)) / 4
        return round(base + extra_4oz * _LARGE_STANDARD_HEAVY_PER_4OZ, 2)

    # Large Bulky
    if tier in ("large-bulky", "small-oversize"):
        return round(_LARGE_BULKY_BASE + max(0, weight_lbs - 1) * _LARGE_BULKY_PER_LB, 2)

    # Extra-Large
    if tier in ("extra-large", "large-oversize", "medium-oversize", "special-oversize"):
        return round(_EXTRA_LARGE_BASE + max(0, weight_lbs - 1) * _EXTRA_LARGE_PER_LB, 2)

    # Fallback: use large standard mid-tier
    return _LARGE_STANDARD_FEES[4][2]  # ~1lb, $10-$50 tier


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
