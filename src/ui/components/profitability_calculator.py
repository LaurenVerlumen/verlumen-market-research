"""Interactive Helium-10-style profitability calculator component."""

import json
import re

from nicegui import ui

from src.models.database import get_session
from src.models.product import Product
from src.ui.components.helpers import section_header, INPUT_PROPS
from src.services.fee_calculator import (
    available_categories,
    calculate_detailed_profitability,
    get_fee_version,
)

# Unit conversion constants
_IN_TO_CM = 2.54
_LB_TO_KG = 0.453592


def _parse_dimensions(dim_str: str | None) -> tuple[float, float, float]:
    """Parse dimension string like '10.63 x 6.81 x 7.20 in' → (width, length, height)."""
    if not dim_str:
        return (0.0, 0.0, 0.0)
    nums = re.findall(r"[\d.]+", dim_str)
    if len(nums) >= 3:
        return (float(nums[0]), float(nums[1]), float(nums[2]))
    return (0.0, 0.0, 0.0)


def _margin_color(margin: float) -> str:
    """Return a Tailwind/Quasar background class based on margin percentage."""
    if margin > 30:
        return "bg-green-1 border-green-5"
    if margin >= 15:
        return "bg-amber-1 border-amber-5"
    return "bg-red-1 border-red-5"


def _margin_text_color(margin: float) -> str:
    if margin > 30:
        return "text-green-8"
    if margin >= 15:
        return "text-amber-9"
    return "text-red-8"


def _load_profitability_data(product_id: int) -> dict | None:
    """Load saved profitability inputs from DB, or None if not saved."""
    db = get_session()
    try:
        p = db.query(Product).filter(Product.id == product_id).first()
        if p and p.profitability_data:
            return json.loads(p.profitability_data)
    finally:
        db.close()
    return None


def _save_profitability_data(product_id: int, data: dict) -> None:
    """Persist profitability calculator inputs to DB."""
    db = get_session()
    try:
        p = db.query(Product).filter(Product.id == product_id).first()
        if p:
            p.profitability_data = json.dumps(data)
            db.commit()
    finally:
        db.close()


def profitability_calculator(
    product_id: int,
    initial_price: float | None = None,
    initial_cost: float | None = None,
    initial_dimensions: str | None = None,
    initial_weight: float | None = None,
    initial_size_tier: str | None = None,
    initial_category: str = "toys-and-games",
) -> None:
    """Render a fully interactive profitability calculator."""

    # Load saved state (if any)
    saved = _load_profitability_data(product_id)

    if saved:
        price_val = saved.get("price", initial_price or 0.0)
        iw = saved.get("width", 0.0)
        il = saved.get("length", 0.0)
        ih = saved.get("height", 0.0)
        weight_val = saved.get("weight", initial_weight or 0.0)
        cost_val = saved.get("unit_cost", initial_cost or 0.0)
        freight_mode_val = saved.get("freight_mode", "per_cbm")
        freight_rate_val = saved.get("freight_rate", 400.0)
        storage_months_val = saved.get("storage_months", 1.0)
        category_val = saved.get("category", initial_category)
        duties_mode_val = saved.get("duties_mode", "percent")
        duties_value_val = saved.get("duties_value", 0.0)
        other_mode_val = saved.get("other_mode", "percent")
        other_value_val = saved.get("other_value", 0.0)
        unit_imperial = saved.get("unit_system", "imperial") == "imperial"
    else:
        iw, il, ih = _parse_dimensions(initial_dimensions)
        price_val = initial_price or 0.0
        cost_val = initial_cost or 0.0
        weight_val = initial_weight or 0.0
        freight_mode_val = "per_cbm"
        freight_rate_val = 400.0
        storage_months_val = 1.0
        category_val = initial_category
        duties_mode_val = "percent"
        duties_value_val = 0.0
        other_mode_val = "percent"
        other_value_val = 0.0
        unit_imperial = True

    # Category options for referral fee select
    categories = available_categories()
    cat_labels = {c: c.replace("-", " ").title() for c in categories}

    # Select options
    freight_modes = {"per_cbm": "Per cubic meter", "per_unit": "Per unit"}
    duties_modes = {"percent": "Percent %", "flat": "Flat $"}
    other_modes = {"percent": "Percent %", "flat": "Flat $"}

    # Determine initial suffixes based on unit system
    dim_suffix = "in" if unit_imperial else "cm"
    wt_suffix = "lb" if unit_imperial else "kg"

    # ── Section 1: Product Specs ──────────────────────────────────────────
    with ui.card().classes("w-full p-5"):
        with ui.row().classes("w-full items-center justify-between"):
            section_header("Product Specs", icon="settings")
            unit_toggle = ui.toggle(
                {True: "Imperial (in/lb)", False: "Metric (cm/kg)"},
                value=unit_imperial,
            ).props("dense no-caps size=sm color=accent")

        inp_price = (
            ui.number(label="Price", value=price_val, format="%.2f", min=0)
            .props("outlined dense prefix='$' debounce=300")
            .classes("w-full")
        )
        inp_price.tooltip("The Amazon selling price for this product")

        ui.label("Dimensions (L x W x H)").classes("text-caption text-secondary mt-1")
        with ui.column().classes("w-full gap-1"):
            inp_length = (
                ui.number(label="Length", value=il, format="%.2f", min=0)
                .props(f"outlined dense suffix='{dim_suffix}' debounce=300")
                .classes("w-full")
            )
            inp_length.tooltip("Product length — longest side (as shipped)")

            inp_width = (
                ui.number(label="Width", value=iw, format="%.2f", min=0)
                .props(f"outlined dense suffix='{dim_suffix}' debounce=300")
                .classes("w-full")
            )
            inp_width.tooltip("Product width — median side (as shipped)")

            inp_height = (
                ui.number(label="Height", value=ih, format="%.2f", min=0)
                .props(f"outlined dense suffix='{dim_suffix}' debounce=300")
                .classes("w-full")
            )
            inp_height.tooltip("Product height — shortest side (as shipped)")

        inp_weight = (
            ui.number(label="Weight", value=weight_val, format="%.2f", min=0)
            .props(f"outlined dense suffix='{wt_suffix}' debounce=300")
            .classes("w-full")
        )
        inp_weight.tooltip("Product weight (as shipped)")

        ui.separator()

        with ui.row().classes("w-full justify-between items-center"):
            lbl = ui.label("Outbound Shipping Weight").classes(
                "text-caption text-secondary"
            )
            lbl.tooltip(
                "Unit weight plus estimated packaging weight added by Amazon"
            )
            lbl_outbound_weight = ui.label("-- lb").classes("font-medium")

        with ui.row().classes("w-full justify-between items-center"):
            lbl2 = ui.label("Size Tier").classes("text-caption text-secondary")
            lbl2.tooltip(
                "Amazon FBA size classification based on dimensions and weight"
            )
            lbl_size_tier = ui.label("--").classes("font-medium")

    # ── Section 2: Manufacturing Cost ─────────────────────────────────────
    with ui.card().classes("w-full p-5"):
        section_header("Manufacturing Cost", icon="factory")

        inp_unit_cost = (
            ui.number(
                label="Unit Manufacturing Cost", value=cost_val, format="%.2f", min=0
            )
            .props("outlined dense prefix='$' debounce=300")
            .classes("w-full")
        )
        inp_unit_cost.tooltip(
            "Your per-unit cost from the supplier (e.g., Alibaba price)"
        )

        with ui.row().classes("w-full gap-2 items-end"):
            sel_freight_mode = ui.select(
                label="Freight Cost",
                options=freight_modes,
                value=freight_mode_val,
            ).props(INPUT_PROPS).classes("w-48")
            sel_freight_mode.tooltip(
                "Choose between cost per cubic meter or flat per-unit rate"
            )

            inp_freight_rate = (
                ui.number(label="Rate", value=freight_rate_val, format="%.2f", min=0)
                .props("outlined dense prefix='$' debounce=300")
                .classes("flex-1")
            )
            inp_freight_rate.tooltip(
                "Shipping cost from supplier to Amazon FBA warehouse"
            )

        ui.separator()

        with ui.row().classes("w-full justify-between items-center"):
            lbl3 = ui.label("Unit Freight Cost").classes(
                "text-caption text-secondary"
            )
            lbl3.tooltip(
                "Calculated per-unit freight cost based on product volume"
            )
            lbl_unit_freight = ui.label("$--").classes("font-medium")

    # ── Section 3: Fulfillment Cost ───────────────────────────────────────
    with ui.card().classes("w-full p-5"):
        with ui.row().classes("w-full items-center justify-between"):
            section_header("Fulfillment Cost", icon="local_shipping")
            ui.badge(
                f"Fee rates: {get_fee_version()}", color="grey-5",
            ).props("outline").classes("text-caption")

        with ui.row().classes("w-full justify-between items-center"):
            lbl4 = ui.label("FBA Fee").classes("text-caption text-secondary")
            lbl4.tooltip(
                "Amazon FBA fulfillment fee based on size tier, weight, and price tier"
            )
            lbl_fba_fee = ui.label("$--").classes("font-medium")

        inp_storage_months = (
            ui.number(
                label="Est. Time in Storage",
                value=storage_months_val,
                format="%.1f",
                min=0,
            )
            .props("outlined dense suffix='month' debounce=300")
            .classes("w-full")
        )
        inp_storage_months.tooltip(
            "Average months inventory sits in Amazon's warehouse before selling"
        )

        with ui.row().classes("w-full justify-between items-center"):
            lbl5 = ui.label("Storage Fee").classes("text-caption text-secondary")
            lbl5.tooltip(
                "Monthly storage fee per unit (different rates Jan-Sep vs Oct-Dec)"
            )
            lbl_storage_fee = ui.label("Jan - Sep $-- / Oct - Dec $--").classes(
                "font-medium"
            )

        with ui.row().classes("w-full gap-2 items-end"):
            sel_category = ui.select(
                label="Referral Fee",
                options=cat_labels,
                value=category_val,
            ).props(INPUT_PROPS).classes("flex-1")
            sel_category.tooltip(
                "Amazon's commission based on product category and selling price"
            )
            lbl_referral_fee = ui.label("$--").classes(
                "font-medium self-center whitespace-nowrap"
            )

        with ui.row().classes("w-full gap-2 items-end"):
            sel_duties_mode = ui.select(
                label="Duties & Tariffs",
                options=duties_modes,
                value=duties_mode_val,
            ).props(INPUT_PROPS).classes("w-40")
            sel_duties_mode.tooltip(
                "Import duties and tariffs (as % of price or flat $ per unit)"
            )
            inp_duties_value = (
                ui.number(label="Value", value=duties_value_val, format="%.2f", min=0)
                .props("outlined dense debounce=300")
                .classes("flex-1")
            )

        # Tariff presets — quick-apply common scenarios
        with ui.expansion(
            "Tariff presets & lookup", icon="travel_explore",
        ).classes("w-full").props(
            "dense header-class='text-caption text-amber-9'"
        ):
            ui.label(
                "Quick-apply common import duty rates, or look up "
                "exact HTS codes for your product."
            ).classes("text-caption text-secondary mb-2")

            _tariff_presets = [
                ("China (toys) ~25%", 25.0,
                 "Section 301 + IEEPA (Chapter 95 toys)"),
                ("China (general) ~30%", 30.0,
                 "Higher-tariff CN goods (electronics, furniture)"),
                ("China (low-risk) ~10%", 10.0,
                 "De minimis / lower HTS sub-headings"),
                ("MFN Standard ~5%", 5.0,
                 "Most-Favored-Nation rate (non-China origins)"),
                ("Duty-Free (0%)", 0.0,
                 "FTA countries, GSP-eligible, or zero-rate HTS"),
            ]

            def _make_apply(pct):
                def _apply():
                    sel_duties_mode.value = "percent"
                    inp_duties_value.value = pct
                return _apply

            for label, pct, hint in _tariff_presets:
                with ui.row().classes("w-full items-center gap-2 py-1"):
                    ui.chip(
                        label, icon="bolt", on_click=_make_apply(pct),
                    ).props(
                        "clickable outlined color=amber-8 dense size=sm"
                    )
                    ui.label(hint).classes("text-caption text-secondary")

            ui.separator().classes("my-2")
            ui.label(
                "Need the exact rate? Look up your product's HTS code:"
            ).classes("text-caption text-secondary")
            with ui.row().classes("items-center gap-2 mt-1"):
                ui.icon("open_in_new", size="xs").classes("text-primary")
                ui.link(
                    "HTS Tariff Lookup (USITC)",
                    "https://hts.usitc.gov/",
                    new_tab=True,
                ).classes("text-primary text-caption font-medium")
                ui.label("— Toys = Chapter 95").classes(
                    "text-caption text-secondary"
                )

        with ui.row().classes("w-full gap-2 items-end"):
            sel_other_mode = ui.select(
                label="Other Costs",
                options=other_modes,
                value=other_mode_val,
            ).props(INPUT_PROPS).classes("w-40")
            sel_other_mode.tooltip(
                "Any additional per-unit costs (inspection, labeling, prep, etc.)"
            )
            inp_other_value = (
                ui.number(label="Value", value=other_value_val, format="%.2f", min=0)
                .props("outlined dense debounce=300")
                .classes("flex-1")
            )

    # ── Section 4: Results ────────────────────────────────────────────────
    with ui.row().classes("w-full gap-4"):
        card_jan_sep = ui.card().classes("flex-1 p-5 border")
        with card_jan_sep:
            ui.label("January - September").classes("text-subtitle2 font-bold")
            with ui.grid(columns=2).classes("gap-x-4 gap-y-2 w-full mt-2"):
                ui.label("Net:").classes("text-caption text-secondary")
                lbl_net_jan = ui.label("$--").classes("font-bold text-right")
                ui.label("Margin:").classes("text-caption text-secondary")
                lbl_margin_jan = ui.label("--%").classes("font-bold text-right")
                ui.label("ROI:").classes("text-caption text-secondary")
                lbl_roi_jan = ui.label("--%").classes("font-bold text-right")

        card_oct_dec = ui.card().classes("flex-1 p-5 border")
        with card_oct_dec:
            ui.label("October - December").classes("text-subtitle2 font-bold")
            with ui.grid(columns=2).classes("gap-x-4 gap-y-2 w-full mt-2"):
                ui.label("Net:").classes("text-caption text-secondary")
                lbl_net_oct = ui.label("$--").classes("font-bold text-right")
                ui.label("Margin:").classes("text-caption text-secondary")
                lbl_margin_oct = ui.label("--%").classes("font-bold text-right")
                ui.label("ROI:").classes("text-caption text-secondary")
                lbl_roi_oct = ui.label("--%").classes("font-bold text-right")

    # ── Unit toggle helpers ───────────────────────────────────────────────

    dim_inputs = (inp_width, inp_length, inp_height)

    def _update_unit_suffixes(is_imperial: bool):
        """Update input field suffixes based on unit system."""
        sfx_dim = "in" if is_imperial else "cm"
        sfx_wt = "lb" if is_imperial else "kg"
        for inp in dim_inputs:
            inp.props(f"outlined dense suffix='{sfx_dim}' debounce=300")
        inp_weight.props(f"outlined dense suffix='{sfx_wt}' debounce=300")

    def _on_unit_toggle(e):
        """Convert values in-place when toggling between imperial and metric."""
        is_imperial = e.value
        if is_imperial:
            # Was metric → convert to imperial: cm→in, kg→lb
            for inp in dim_inputs:
                if inp.value:
                    inp.value = round(inp.value / _IN_TO_CM, 2)
            if inp_weight.value:
                inp_weight.value = round(inp_weight.value / _LB_TO_KG, 2)
        else:
            # Was imperial → convert to metric: in→cm, lb→kg
            for inp in dim_inputs:
                if inp.value:
                    inp.value = round(inp.value * _IN_TO_CM, 2)
            if inp_weight.value:
                inp_weight.value = round(inp_weight.value * _LB_TO_KG, 2)
        _update_unit_suffixes(is_imperial)
        # Value changes above will trigger _recalculate automatically

    unit_toggle.on_value_change(_on_unit_toggle)

    # ── Recalculation logic ───────────────────────────────────────────────

    def _recalculate(*_args):
        """Read all inputs, compute profitability, update all labels."""
        price = inp_price.value or 0.0
        unit_cost = inp_unit_cost.value or 0.0
        length = inp_length.value or 0.0
        width = inp_width.value or 0.0
        height = inp_height.value or 0.0
        weight = inp_weight.value or 0.0
        category = sel_category.value or "toys-and-games"
        freight_mode = sel_freight_mode.value or "per_cbm"
        freight_rate = inp_freight_rate.value or 0.0
        storage_months = inp_storage_months.value or 0.0
        duties_mode = "percent" if sel_duties_mode.value == "percent" else "flat"
        duties_value = inp_duties_value.value or 0.0
        other_mode = "percent" if sel_other_mode.value == "percent" else "flat"
        other_value = inp_other_value.value or 0.0

        # Convert to imperial for fee calculator if in metric mode
        is_imperial = unit_toggle.value
        if is_imperial:
            length_in, width_in, height_in, weight_lbs = length, width, height, weight
        else:
            length_in = length / _IN_TO_CM if length else 0.0
            width_in = width / _IN_TO_CM if width else 0.0
            height_in = height / _IN_TO_CM if height else 0.0
            weight_lbs = weight / _LB_TO_KG if weight else 0.0

        result = calculate_detailed_profitability(
            price=price,
            unit_cost=unit_cost,
            length_in=length_in,
            width_in=width_in,
            height_in=height_in,
            weight_lbs=weight_lbs,
            category=category,
            freight_mode=freight_mode,
            freight_rate=freight_rate,
            storage_months=storage_months,
            duties_mode=duties_mode,
            duties_value=duties_value,
            other_mode=other_mode,
            other_value=other_value,
        )

        # Update product specs labels (unit-aware)
        if is_imperial:
            lbl_outbound_weight.text = f"{result['outbound_weight']:.2f} lb"
        else:
            lbl_outbound_weight.text = (
                f"{result['outbound_weight'] * _LB_TO_KG:.2f} kg"
            )
        lbl_size_tier.text = result["size_tier"]

        # Update manufacturing cost labels
        lbl_unit_freight.text = f"${result['unit_freight_cost']:.2f}"

        # Update fulfillment cost labels
        lbl_fba_fee.text = f"${result['fba_fee']:.2f}"
        lbl_storage_fee.text = (
            f"Jan - Sep ${result['storage_jan_sep']:.2f} / "
            f"Oct - Dec ${result['storage_oct_dec']:.2f}"
        )
        ref_pct = result["referral_pct"] * 100
        lbl_referral_fee.text = (
            f"${result['referral_fee']:.2f} ({ref_pct:.0f}%)"
        )

        # Update result cards — Jan-Sep
        lbl_net_jan.text = f"${result['net_jan_sep']:.2f}"
        lbl_margin_jan.text = f"{result['margin_jan_sep']:.2f}%"
        lbl_roi_jan.text = f"{result['roi_jan_sep']:.2f}%"

        # Update result cards — Oct-Dec
        lbl_net_oct.text = f"${result['net_oct_dec']:.2f}"
        lbl_margin_oct.text = f"{result['margin_oct_dec']:.2f}%"
        lbl_roi_oct.text = f"{result['roi_oct_dec']:.2f}%"

        # Color-code result cards by margin
        jan_color = _margin_color(result["margin_jan_sep"])
        oct_color = _margin_color(result["margin_oct_dec"])
        jan_text = _margin_text_color(result["margin_jan_sep"])
        oct_text = _margin_text_color(result["margin_oct_dec"])

        card_jan_sep.classes(replace=f"flex-1 p-5 border {jan_color}")
        card_oct_dec.classes(replace=f"flex-1 p-5 border {oct_color}")

        lbl_net_jan.classes(replace=f"font-bold text-right {jan_text}")
        lbl_margin_jan.classes(replace=f"font-bold text-right {jan_text}")
        lbl_roi_jan.classes(replace=f"font-bold text-right {jan_text}")

        lbl_net_oct.classes(replace=f"font-bold text-right {oct_text}")
        lbl_margin_oct.classes(replace=f"font-bold text-right {oct_text}")
        lbl_roi_oct.classes(replace=f"font-bold text-right {oct_text}")

        # Persist calculator state to DB
        _save_profitability_data(product_id, {
            "price": price,
            "width": width,
            "length": length,
            "height": height,
            "weight": weight,
            "unit_cost": unit_cost,
            "freight_mode": freight_mode,
            "freight_rate": freight_rate,
            "storage_months": storage_months,
            "category": category,
            "duties_mode": duties_mode,
            "duties_value": duties_value,
            "other_mode": other_mode,
            "other_value": other_value,
            "unit_system": "imperial" if is_imperial else "metric",
        })

    # Wire up all inputs to recalculate on change
    inp_price.on_value_change(_recalculate)
    inp_width.on_value_change(_recalculate)
    inp_length.on_value_change(_recalculate)
    inp_height.on_value_change(_recalculate)
    inp_weight.on_value_change(_recalculate)
    inp_unit_cost.on_value_change(_recalculate)
    sel_freight_mode.on_value_change(_recalculate)
    inp_freight_rate.on_value_change(_recalculate)
    inp_storage_months.on_value_change(_recalculate)
    sel_category.on_value_change(_recalculate)
    sel_duties_mode.on_value_change(_recalculate)
    inp_duties_value.on_value_change(_recalculate)
    sel_other_mode.on_value_change(_recalculate)
    inp_other_value.on_value_change(_recalculate)

    # ── Reference Sources ────────────────────────────────────────────────
    with ui.expansion("Reference Sources", icon="menu_book").classes("w-full").props(
        "dense header-class='text-caption text-secondary'"
    ):
        ui.label(
            "Use these official sources to double-check fee rates and tariffs."
        ).classes("text-caption text-secondary mb-2")

        _sources = [
            (
                "Amazon FBA Fulfillment Fees (2026)",
                "https://sellercentral.amazon.com/help/hub/reference/external/GPDC3KPYAGDTVDJP",
                "Official fee schedule — size tiers, weight bands, price-tiered rates",
            ),
            (
                "2026 US FBA Fee Changes",
                "https://sellercentral.amazon.com/help/hub/reference/external/GABBX6GZPA8MSZGW",
                "Summary of what changed Jan 15, 2026 vs 2025",
            ),
            (
                "Amazon Referral Fee Schedule",
                "https://sellercentral.amazon.com/help/hub/reference/external/GTG4BAWSY39Z98EN",
                "Category-specific referral fee percentages",
            ),
            (
                "FBA Revenue Calculator",
                "https://sellercentral.amazon.com/hz/fba/profitabilityCalculator/index",
                "Amazon's own calculator — use to verify specific ASINs",
            ),
            (
                "US Tariffs on Toys from China",
                "https://www.examinechina.com/us-tariffs-on-toys-from-china/",
                "Section 301 + IEEPA tariff breakdown for toy imports",
            ),
            (
                "HTS Tariff Lookup (USITC)",
                "https://hts.usitc.gov/",
                "Look up exact duty rates by HTS code (toys = Chapter 95)",
            ),
        ]

        for title, url, desc in _sources:
            with ui.row().classes("items-start gap-2 w-full py-1"):
                ui.icon("open_in_new", size="xs").classes("text-primary mt-1")
                with ui.column().classes("gap-0"):
                    ui.link(title, url, new_tab=True).classes(
                        "text-primary text-caption font-medium"
                    )
                    ui.label(desc).classes("text-caption text-secondary")

    # Initial calculation
    _recalculate()
