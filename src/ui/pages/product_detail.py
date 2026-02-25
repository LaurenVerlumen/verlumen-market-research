"""Product detail page - Alibaba info + Amazon competition analysis."""
import asyncio
import json
import logging
import statistics as _stats
from datetime import datetime

from nicegui import ui

from config import SERPAPI_KEY, SP_API_REFRESH_TOKEN, AMAZON_MARKETPLACES, ANTHROPIC_API_KEY
from src.models import get_session, Product, AmazonCompetitor, SearchSession
from src.models.category import Category
from src.services import (
    ImageFetcher, download_image, save_uploaded_image,
    AmazonSearchService, AmazonSearchError, CompetitionAnalyzer,
    get_search_context,
)
from src.services.sp_api_client import SPAPIClient
from src.services.xray_importer import XrayImporter
from src.services.match_scorer import score_matches
from src.services.utils import parse_bought
from src.ui.components.helpers import (
    avatar_color as _avatar_color, product_image_src as _product_image_src,
    format_price as _format_price, STATUS_COLORS as _STATUS_COLORS, STATUS_LABELS as _STATUS_LABELS,
    section_header, product_thumbnail as _product_thumbnail,
)
from src.services.viability_scorer import calculate_vvs
from src.services.brand_moat import compute_brand_concentration
from src.services.gtm_brief_generator import generate_gtm_brief
from src.services.trend_tracker import compute_trends
from src.services.review_miner import mine_reviews, get_review_analysis
from src.ui.layout import build_layout
from src.ui.components.stats_card import stats_card
from src.ui.components.competitor_table import competitor_table

logger = logging.getLogger(__name__)


def product_detail_page(product_id: int):
    """Render the product detail page."""
    content = build_layout()

    with content:
        session = get_session()
        try:
            product = session.query(Product).filter(Product.id == product_id).first()
            if not product:
                ui.label("Product not found.").classes("text-negative text-h6")
                ui.button("Back to Products", on_click=lambda: ui.navigate.to("/products"))
                return

            # Header with back button, editable product name, and delete
            with ui.row().classes("items-center gap-2 w-full"):
                ui.button(
                    icon="arrow_back", on_click=lambda: ui.navigate.to("/products"),
                ).props("flat round")

                name_input = ui.input(
                    value=product.name,
                ).classes("text-h5 font-bold flex-1").props(
                    "borderless dense input-class='text-h5 font-bold'"
                )

                def _save_name():
                    new_name = name_input.value.strip()
                    if not new_name or new_name == product.name:
                        return
                    db = get_session()
                    try:
                        p = db.query(Product).filter(Product.id == product_id).first()
                        if p:
                            p.name = new_name
                            p.amazon_search_query = new_name
                            db.commit()
                            ui.notify(f"Name updated to '{new_name}'", type="positive")
                    finally:
                        db.close()

                name_input.on("blur", lambda: _save_name())
                name_input.on("keydown.enter", lambda: _save_name())

                def _show_delete_dialog():
                    with ui.dialog() as dlg, ui.card():
                        ui.label(f'Delete "{product.name}"?').classes(
                            "text-subtitle1 font-bold"
                        )
                        ui.label(
                            "Are you sure you want to delete this product? "
                            "This will also delete all associated Amazon research data."
                        ).classes("text-body2 text-secondary")
                        with ui.row().classes("justify-end gap-2 mt-4"):
                            ui.button("Cancel", on_click=dlg.close).props("flat")

                            def _confirm():
                                db = get_session()
                                try:
                                    p = db.query(Product).filter(
                                        Product.id == product_id
                                    ).first()
                                    if p:
                                        db.delete(p)
                                        db.commit()
                                finally:
                                    db.close()
                                dlg.close()
                                ui.navigate.to("/products")

                            ui.button("Delete", on_click=_confirm).props(
                                "color=negative"
                            )
                    dlg.open()

                ui.button(
                    "Delete Product", icon="delete", on_click=_show_delete_dialog,
                ).props("color=negative outline")

            # Status action bar
            with ui.row().classes("items-center gap-2 w-full"):
                _st = product.status or "imported"
                ui.badge(
                    _STATUS_LABELS.get(_st, _st.replace("_", " ").title()),
                    color=_STATUS_COLORS.get(_st, "grey-5"),
                ).classes("text-body2")

                ui.space()

                def _set_status(new_status):
                    db = get_session()
                    try:
                        p = db.query(Product).filter(Product.id == product_id).first()
                        if p:
                            old_status = p.status
                            p.status = new_status
                            # Auto-log status change
                            log_entries = json.loads(p.decision_log or "[]")
                            log_entries.append({
                                "date": datetime.utcnow().isoformat(),
                                "action": "status_changed",
                                "detail": f"{_STATUS_LABELS.get(old_status, old_status)} -> {_STATUS_LABELS.get(new_status, new_status)}",
                            })
                            p.decision_log = json.dumps(log_entries)
                            db.commit()
                            ui.notify(
                                f"Status -> {_STATUS_LABELS.get(new_status, new_status)}",
                                type="positive",
                            )
                            ui.navigate.to(f"/products/{product_id}")
                    finally:
                        db.close()

                ui.button(
                    "Approve", icon="check_circle",
                    on_click=lambda: _set_status("approved"),
                ).props("color=positive size=sm")
                ui.button(
                    "Reject", icon="cancel",
                    on_click=lambda: _set_status("rejected"),
                ).props("color=negative size=sm outline")
                ui.button(
                    "Mark for Review", icon="rate_review",
                    on_click=lambda: _set_status("under_review"),
                ).props("color=warning size=sm outline")

            # --- Eagerly resolve department + query suffix while session is still open ---
            _search_ctx = get_search_context(product.category)
            _product_dept = _search_ctx["department"]
            _query_suffix = _search_ctx["query_suffix"]
            _product_name = product.name  # cache for use after session close

            # --- Lookup latest session & all sessions for tabs ---
            latest_session = (
                session.query(SearchSession)
                .filter(SearchSession.product_id == product.id)
                .order_by(SearchSession.created_at.desc())
                .first()
            )
            all_sessions = (
                session.query(SearchSession)
                .filter(SearchSession.product_id == product.id)
                .order_by(SearchSession.created_at.desc())
                .all()
            )

            # --- Query optimizer import (used in Overview tab) ---
            try:
                from src.services.query_optimizer import suggest_queries as _suggest_queries_fn
                _has_query_optimizer = True
            except ImportError:
                _has_query_optimizer = False

            # ================================================================
            # Tabs
            # ================================================================
            with ui.tabs().classes("w-full") as tabs:
                overview_tab = ui.tab("Overview", icon="info")
                competitors_tab = ui.tab("Competitors", icon="groups")
                profitability_tab = ui.tab("Profitability", icon="calculate")
                analysis_tab = ui.tab("Analysis", icon="analytics")
                reviews_tab = ui.tab("Reviews", icon="rate_review")
                history_tab = ui.tab("History", icon="history")

            with ui.tab_panels(tabs, value=competitors_tab).classes("w-full"):

                # ============================================================
                # OVERVIEW TAB
                # ============================================================
                with ui.tab_panel(overview_tab):
                    _render_overview_tab(
                        product, product_id, session,
                        _has_query_optimizer,
                        _suggest_queries_fn if _has_query_optimizer else None,
                    )

                # ============================================================
                # COMPETITORS TAB
                # ============================================================
                with ui.tab_panel(competitors_tab):
                    _render_competitors_tab(
                        product, product_id, session, latest_session,
                        _product_dept, _product_name, _query_suffix,
                    )

                # ============================================================
                # PROFITABILITY TAB
                # ============================================================
                with ui.tab_panel(profitability_tab):
                    _render_profitability_tab(product, latest_session)

                # ============================================================
                # ANALYSIS TAB
                # ============================================================
                with ui.tab_panel(analysis_tab):
                    _render_analysis_tab(product, latest_session)

                # ============================================================
                # REVIEWS TAB
                # ============================================================
                with ui.tab_panel(reviews_tab):
                    _render_reviews_tab(product, product_id, latest_session)

                # ============================================================
                # HISTORY TAB
                # ============================================================
                with ui.tab_panel(history_tab):
                    _render_history_tab(all_sessions, product_id, product)

        finally:
            session.close()


# ====================================================================
# Tab renderers
# ====================================================================

def _render_overview_tab(product, product_id, session,
                         _has_query_optimizer, _suggest_queries_fn):
    """Render the Overview tab: product info card + decision log."""

    # Product info card with image
    with ui.card().classes("w-full p-5"):
        with ui.row().classes("items-start gap-6 w-full"):
            # Product image / avatar placeholder
            with ui.column().classes("items-center gap-1").style("flex-shrink:0"):
                img_src = _product_image_src(product)
                if img_src:
                    ui.image(img_src).classes(
                        "w-32 h-32 rounded-lg object-cover"
                    )
                else:
                    letter = product.name[0].upper() if product.name else "?"
                    bg = _avatar_color(product.name)
                    ui.avatar(
                        letter, color=bg, text_color="white", size="128px",
                        font_size="48px",
                    ).classes("rounded-lg")

                # Image action buttons
                fetch_img_btn = ui.button(
                    "Fetch Image", icon="image_search",
                ).props("flat dense size=sm color=secondary")
                fetch_img_status = ui.label("").classes(
                    "text-caption text-secondary"
                )

                async def _fetch_single_image():
                    if not SERPAPI_KEY:
                        ui.notify("SERPAPI_KEY not configured.", type="negative")
                        return

                    fetch_img_btn.disable()
                    fetch_img_status.text = "Searching..."
                    fetcher = ImageFetcher(SERPAPI_KEY)

                    url, filename = await asyncio.get_event_loop().run_in_executor(
                        None, fetcher.fetch_and_save, product.name, product_id,
                    )

                    if url:
                        db = get_session()
                        try:
                            p = db.query(Product).filter(
                                Product.id == product_id
                            ).first()
                            if p:
                                p.alibaba_image_url = url
                                if filename:
                                    p.local_image_path = filename
                                db.commit()
                        finally:
                            db.close()
                        fetch_img_status.text = "Image saved locally!"
                        ui.notify("Image fetched & saved!", type="positive")
                        ui.navigate.to(f"/products/{product_id}")
                    else:
                        fetch_img_status.text = "No image found"
                        fetch_img_btn.enable()

                fetch_img_btn.on_click(_fetch_single_image)

                # Manual image upload
                async def _handle_image_upload(e):
                    file_content = await e.file.read()
                    original_name = e.file.name
                    filename = await asyncio.get_event_loop().run_in_executor(
                        None, save_uploaded_image, file_content, product_id, original_name,
                    )
                    db = get_session()
                    try:
                        p = db.query(Product).filter(
                            Product.id == product_id
                        ).first()
                        if p:
                            p.local_image_path = filename
                            db.commit()
                    finally:
                        db.close()
                    ui.notify("Image uploaded!", type="positive")
                    ui.navigate.to(f"/products/{product_id}")

                ui.upload(
                    label="Upload image",
                    auto_upload=True,
                    on_upload=_handle_image_upload,
                ).props(
                    'accept="image/*" max-file-size=5242880 flat dense'
                ).classes("w-32").style("font-size:12px")

            # Info grid
            with ui.column().classes("flex-1 gap-2"):
                ui.label("Product Information").classes(
                    "text-subtitle1 font-bold mb-2"
                )
                with ui.grid(columns=2).classes("gap-x-8 gap-y-2"):
                    ui.label("Category").classes(
                        "text-caption text-secondary font-medium"
                    )
                    # Editable category selector
                    all_cats = session.query(Category).order_by(Category.name).all()
                    cat_options = {c.id: c.name for c in all_cats}
                    cat_select = ui.select(
                        options=cat_options,
                        value=product.category_id,
                    ).props("dense outlined").classes("text-body2")

                    def _save_category(e, pid=product.id):
                        new_cat_id = cat_select.value
                        if new_cat_id == product.category_id:
                            return
                        db = get_session()
                        try:
                            p = db.query(Product).filter(Product.id == pid).first()
                            if p:
                                p.category_id = new_cat_id
                                db.commit()
                                cat_name = cat_options.get(new_cat_id, "")
                                ui.notify(f"Category changed to '{cat_name}'", type="positive")
                        finally:
                            db.close()

                    cat_select.on("update:model-value", _save_category)
                    _info_row(
                        "Alibaba Product ID",
                        product.alibaba_product_id or "N/A",
                    )

                    # --- Editable Amazon Search Query ---
                    ui.label("Amazon Search Query").classes(
                        "text-caption text-secondary font-medium"
                    )
                    with ui.row().classes("items-center gap-1 w-full"):
                        search_query_input = ui.input(
                            value=product.amazon_search_query or product.name,
                            placeholder="Amazon search query...",
                        ).props("dense outlined").classes("text-body2 flex-1")

                        def _save_search_query(e, pid=product.id):
                            db = get_session()
                            try:
                                p = db.query(Product).filter(Product.id == pid).first()
                                if p:
                                    p.amazon_search_query = e.sender.value.strip() or None
                                    db.commit()
                            finally:
                                db.close()

                        search_query_input.on("blur", _save_search_query)

                        # --- Query Optimizer button ---
                        if _has_query_optimizer:
                            ui.button(
                                icon="auto_fix_high",
                            ).props(
                                "flat round dense size=sm color=primary"
                            ).tooltip("Suggest optimized queries").on(
                                "click", lambda: _run_query_optimizer()
                            )

                    if product.alibaba_price_min is not None or product.alibaba_price_max is not None:
                        _info_row(
                            "Alibaba Price",
                            _format_price(
                                product.alibaba_price_min,
                                product.alibaba_price_max,
                                na_text="N/A",
                            ),
                        )
                    ui.label("Supplier / Factory").classes(
                        "text-caption text-secondary font-medium"
                    )
                    supplier_input = ui.input(
                        value=product.alibaba_supplier or "",
                        placeholder="Enter supplier name...",
                    ).props("dense outlined").classes("text-body2")

                    def _save_supplier(e, pid=product.id):
                        db = get_session()
                        try:
                            p = db.query(Product).filter(Product.id == pid).first()
                            if p:
                                p.alibaba_supplier = e.sender.value.strip() or None
                                db.commit()
                        finally:
                            db.close()

                    supplier_input.on("blur", _save_supplier)
                    if product.alibaba_moq:
                        _info_row("MOQ", str(product.alibaba_moq))
                    if product.local_image_path:
                        _info_row("Image", "Saved locally")
                    elif product.alibaba_image_url:
                        _info_row("Image", "CDN only (not saved locally)")

                # Query suggestions container (outside the grid, inside the column)
                query_suggestions_row = ui.row().classes(
                    "gap-2 flex-wrap"
                )

                if _has_query_optimizer:
                    async def _run_query_optimizer():
                        current_query = search_query_input.value.strip()
                        if not current_query:
                            ui.notify("Enter a search query first.", type="warning")
                            return
                        try:
                            suggestions = await asyncio.get_event_loop().run_in_executor(
                                None, _suggest_queries_fn, current_query,
                            )
                        except Exception as exc:
                            ui.notify(f"Query optimization failed: {exc}", type="negative")
                            return
                        query_suggestions_row.clear()
                        with query_suggestions_row:
                            for s in suggestions:
                                def _use(q=s):
                                    search_query_input.value = q
                                    query_suggestions_row.clear()
                                ui.chip(s, on_click=_use).props(
                                    "clickable outlined color=primary"
                                )

                # --- Notes textarea ---
                ui.label("Notes").classes(
                    "text-subtitle2 font-medium mt-2"
                )
                notes_area = ui.textarea(
                    value=product.notes or "",
                    placeholder="Add notes about this product...",
                ).props("outlined").classes("w-full")

                def _save_notes(e, pid=product.id):
                    db = get_session()
                    try:
                        p = db.query(Product).filter(Product.id == pid).first()
                        if p:
                            p.notes = e.sender.value.strip() or None
                            db.commit()
                    finally:
                        db.close()

                notes_area.on("blur", _save_notes)

                # Prominent Alibaba link button
                if product.alibaba_url:
                    with ui.link(
                        target=product.alibaba_url, new_tab=True,
                    ).classes("no-underline mt-2"):
                        ui.button(
                            "View on Alibaba", icon="open_in_new",
                        ).props("color=accent")

    # --- AI Go-to-Market Brief ---
    _render_ai_brief_section(product, product_id)

    # --- Seasonal Demand Forecast ---
    _render_seasonal_forecast(product, product_id)

    # --- Decision Log ---
    _decision_log_entries = json.loads(product.decision_log or "[]")

    with ui.card().classes("w-full p-5"):
        with ui.row().classes("items-center gap-2 w-full"):
            ui.icon("history").classes("text-accent text-h6")
            ui.label("Decision Log").classes("text-subtitle1 font-bold")
            ui.space()

            def _show_add_note_dialog():
                with ui.dialog() as note_dlg, ui.card().classes("w-96"):
                    ui.label("Add Note").classes("text-subtitle1 font-bold")
                    note_input = ui.textarea(
                        placeholder="Enter your note...",
                    ).props("outlined autofocus").classes("w-full")
                    with ui.row().classes("justify-end gap-2 mt-2"):
                        ui.button("Cancel", on_click=note_dlg.close).props("flat")

                        def _save_note():
                            text = note_input.value.strip()
                            if not text:
                                ui.notify("Note cannot be empty.", type="warning")
                                return
                            db = get_session()
                            try:
                                p = db.query(Product).filter(Product.id == product_id).first()
                                if p:
                                    entries = json.loads(p.decision_log or "[]")
                                    entries.append({
                                        "date": datetime.utcnow().isoformat(),
                                        "action": "note_added",
                                        "detail": "Manual note",
                                        "note": text,
                                    })
                                    p.decision_log = json.dumps(entries)
                                    db.commit()
                            finally:
                                db.close()
                            note_dlg.close()
                            ui.navigate.to(f"/products/{product_id}")

                        ui.button("Save", icon="save", on_click=_save_note).props("color=primary")
                note_dlg.open()

            ui.button(
                "Add Note", icon="note_add",
                on_click=_show_add_note_dialog,
            ).props("flat dense color=primary size=sm")

        _ACTION_ICONS = {
            "status_changed": "swap_horiz",
            "note_added": "sticky_note_2",
        }
        _ACTION_COLORS = {
            "status_changed": "blue",
            "note_added": "grey",
        }

        if not _decision_log_entries:
            ui.label("No entries yet. Status changes and notes will appear here.").classes(
                "text-body2 text-secondary italic mt-2"
            )
        else:
            with ui.column().classes("w-full gap-0 mt-2"):
                for entry in reversed(_decision_log_entries):
                    e_date = entry.get("date", "")
                    e_action = entry.get("action", "")
                    e_detail = entry.get("detail", "")
                    e_note = entry.get("note", "")
                    icon_name = _ACTION_ICONS.get(e_action, "info")
                    icon_color = _ACTION_COLORS.get(e_action, "grey")

                    with ui.row().classes("items-start gap-3 w-full py-2").style(
                        "border-bottom: 1px solid rgba(0,0,0,0.06)"
                    ):
                        ui.icon(icon_name).classes(f"text-{icon_color} mt-1").style("font-size: 20px")
                        with ui.column().classes("gap-0 flex-1"):
                            with ui.row().classes("items-center gap-2"):
                                ui.label(e_detail).classes("text-body2 font-medium")
                            if e_note:
                                ui.label(e_note).classes("text-body2 text-secondary")
                            try:
                                dt = datetime.fromisoformat(e_date)
                                formatted = dt.strftime("%b %d, %Y %H:%M")
                            except (ValueError, TypeError):
                                formatted = e_date
                            ui.label(formatted).classes("text-caption text-grey-6")


def _render_ai_brief_section(product, product_id):
    """Render a collapsible AI Go-to-Market Brief section."""
    with ui.expansion(
        "AI Go-to-Market Brief", icon="auto_awesome",
    ).classes("w-full").props("dense header-class='text-subtitle1 font-bold'"):

        if not ANTHROPIC_API_KEY:
            ui.label(
                "Configure Anthropic API key in Settings to enable AI briefs."
            ).classes("text-body2 text-secondary italic")
            return

        brief_container = ui.column().classes("w-full gap-2")
        brief_btn = ui.button(
            "Generate AI Brief", icon="auto_awesome",
        ).props("outlined color=primary")
        brief_spinner = ui.spinner("dots", size="lg").classes("hidden")

        async def _generate_brief():
            brief_btn.disable()
            brief_spinner.classes(remove="hidden")

            try:
                # Gather data from the database
                db = get_session()
                try:
                    p = db.query(Product).filter(Product.id == product_id).first()
                    if not p:
                        ui.notify("Product not found.", type="negative")
                        return

                    # Get latest session's competitors
                    latest = (
                        db.query(SearchSession)
                        .filter(SearchSession.product_id == product_id)
                        .order_by(SearchSession.created_at.desc())
                        .first()
                    )
                    competitors = []
                    if latest:
                        comps = (
                            db.query(AmazonCompetitor)
                            .filter(AmazonCompetitor.search_session_id == latest.id)
                            .all()
                        )
                        competitors = [
                            {
                                "price": c.price,
                                "rating": c.rating,
                                "review_count": c.review_count,
                                "bought_last_month": c.bought_last_month,
                                "badge": c.badge,
                                "is_prime": c.is_prime,
                                "is_sponsored": c.is_sponsored,
                                "position": c.position,
                                "title": c.title,
                                "asin": c.asin,
                            }
                            for c in comps
                        ]

                    # Compute scoring data
                    alibaba_cost = p.alibaba_price_min
                    vvs = calculate_vvs(p, competitors, alibaba_cost)

                    from src.services.price_recommender import recommend_pricing
                    from src.services.demand_estimator import estimate_demand
                    pricing = recommend_pricing(competitors, alibaba_cost)
                    demand = estimate_demand(competitors)

                    prices = [c["price"] for c in competitors if c.get("price") and c["price"] > 0]
                    ratings = [c["rating"] for c in competitors if c.get("rating") is not None]

                    product_data = {
                        "name": p.name,
                        "category": p.category.name if p.category else "N/A",
                        "vvs": vvs,
                        "pricing": pricing,
                        "demand": demand,
                        "competitor_count": len(competitors),
                        "avg_price": _stats.mean(prices) if prices else None,
                        "avg_rating": _stats.mean(ratings) if ratings else None,
                        "alibaba_cost": alibaba_cost,
                    }
                finally:
                    db.close()

                # Call the AI service in executor to avoid blocking
                brief = await asyncio.get_event_loop().run_in_executor(
                    None, generate_gtm_brief, product_data,
                )

                # Render the brief
                brief_container.clear()
                with brief_container:
                    _render_brief_content(brief)

            except RuntimeError as exc:
                ui.notify(str(exc), type="negative")
            except Exception as exc:
                logger.exception("GTM brief generation failed")
                ui.notify(f"Brief generation failed: {exc}", type="negative")
            finally:
                brief_btn.enable()
                brief_spinner.classes(add="hidden")

        brief_btn.on_click(_generate_brief)


def _render_brief_content(brief: dict):
    """Render the structured GTM brief output."""
    # Market Summary
    if brief.get("market_summary"):
        with ui.card().classes("w-full bg-blue-50 p-3"):
            ui.label("Market Summary").classes("text-subtitle2 font-bold text-blue-9")
            ui.label(brief["market_summary"]).classes("text-body2")

    # Launch Price + Rationale
    with ui.row().classes("w-full gap-4 items-start"):
        if brief.get("launch_price"):
            with ui.card().classes("p-3 bg-green-50").style("min-width: 160px"):
                ui.label("Launch Price").classes("text-caption text-green-9 font-medium")
                ui.label(f"${brief['launch_price']:.2f}").classes(
                    "text-h5 font-bold text-green-10"
                )
        if brief.get("rationale"):
            with ui.card().classes("flex-1 p-3 bg-grey-50"):
                ui.label("Rationale").classes("text-caption text-grey-8 font-medium")
                ui.label(brief["rationale"]).classes("text-body2")

    # Headline Angles
    if brief.get("headline_angles"):
        with ui.card().classes("w-full p-3"):
            ui.label("Headline Angles").classes("text-subtitle2 font-bold")
            for angle in brief["headline_angles"]:
                with ui.row().classes("items-start gap-2"):
                    ui.icon("lightbulb", color="amber").style("font-size: 18px; margin-top: 2px")
                    ui.label(angle).classes("text-body2")

    with ui.row().classes("w-full gap-4 items-start"):
        # Risk Flags
        if brief.get("risk_flags"):
            with ui.card().classes("flex-1 p-3 bg-red-50"):
                ui.label("Risk Flags").classes("text-subtitle2 font-bold text-red-9")
                for risk in brief["risk_flags"]:
                    with ui.row().classes("items-start gap-2"):
                        ui.icon("warning", color="red").style("font-size: 18px; margin-top: 2px")
                        ui.label(risk).classes("text-body2")

        # 90-Day Milestones
        if brief.get("milestones_90day"):
            with ui.card().classes("flex-1 p-3 bg-purple-50"):
                ui.label("90-Day Milestones").classes("text-subtitle2 font-bold text-purple-9")
                for i, milestone in enumerate(brief["milestones_90day"], 1):
                    with ui.row().classes("items-start gap-2"):
                        ui.badge(str(i), color="purple").props("rounded")
                        ui.label(milestone).classes("text-body2")


def _render_competitors_tab(product, product_id, session, latest_session,
                            _product_dept, _product_name, _query_suffix=""):
    """Render the Competitors tab: research controls, stats, competitor table."""
    _product_thumbnail(product)

    # We need search_query_input accessible by _rerun_research.
    # Build a simple mutable container for the query value.
    _query_holder = {"value": product.amazon_search_query or product.name}

    async def _rerun_research(pid=product.id):
        """Run Amazon search + analysis for this single product with progress dialog."""
        if not SERPAPI_KEY:
            ui.notify("SERPAPI_KEY not configured.", type="negative")
            return

        rerun_btn.disable()

        query = _query_holder["value"]
        # Append subcategory suffix if not already present in query
        if _query_suffix and _query_suffix.lower() not in query.lower():
            query = f"{query} {_query_suffix}"
        dept = _product_dept
        dept_label = f" [dept: {dept}]" if dept else ""

        # --- Progress dialog ---
        with ui.dialog() as dlg, ui.card().classes("w-full").style(
            "min-width: 520px; max-width: 640px"
        ):
            ui.label("Research Progress").classes("text-subtitle1 font-bold")
            progress = ui.linear_progress(value=0, show_value=False).classes("w-full")
            step_label = ui.label("Initializing...").classes(
                "text-body2 text-secondary mt-1"
            )
            log_area = ui.log(max_lines=50).classes("w-full h-48 mt-2")
            with ui.row().classes("w-full justify-end mt-2"):
                close_btn = ui.button("Close", icon="close").props(
                    "flat dense color=grey"
                )
                close_btn.visible = False
        dlg.props("persistent")
        dlg.open()

        ts = lambda: datetime.now().strftime("%H:%M:%S")

        _selected_domain = marketplace_select.value
        log_area.push(f"[{ts()}] Starting research for: {product.name}")
        log_area.push(f"[{ts()}] Query: \"{query}\"{dept_label}")
        log_area.push(f"[{ts()}] Marketplace: {_selected_domain}")

        search_service = AmazonSearchService(api_key=SERPAPI_KEY, amazon_domain=_selected_domain)
        analyzer = CompetitionAnalyzer()

        try:
            # Step 1: Amazon search
            step_label.text = "Searching Amazon..."
            progress.value = 0.15
            log_area.push(f"[{ts()}] Searching Amazon via SerpAPI...")

            results = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: search_service.search_products(
                    query, amazon_department=dept,
                ),
            )
            comp_count = len(results["competitors"])
            cached = " (cached)" if results.get("cache_hit") else ""
            log_area.push(
                f"[{ts()}] Found {comp_count} competitors"
                f" ({results['total_organic']} organic,"
                f" {results['total_sponsored']} sponsored){cached}"
            )

            if comp_count == 0:
                step_label.text = "No competitors found."
                log_area.push(f"[{ts()}] WARNING: Search returned 0 competitors.")
                log_area.push(f"[{ts()}] Try adjusting the search query or Amazon department.")
                progress.value = 1.0
                close_btn.visible = True
                close_btn.on_click(lambda: (dlg.close(), rerun_btn.enable()))
                return

            # Step 2: Competition analysis
            step_label.text = f"Analyzing {comp_count} competitors..."
            progress.value = 0.35
            log_area.push(f"[{ts()}] Running competition analysis...")

            analysis = analyzer.analyze(results["competitors"])
            log_area.push(
                f"[{ts()}] Analysis: avg price ${analysis['price_mean']:.2f},"
                f" avg rating {analysis['avg_rating']:.1f},"
                f" avg reviews {analysis['avg_reviews']:.0f}"
            )

            # Step 3: Match scoring
            step_label.text = "Computing match scores..."
            progress.value = 0.50
            log_area.push(f"[{ts()}] Computing match scores vs \"{_product_name}\"...")

            scored = score_matches(_product_name, [dict(c) for c in results["competitors"]])
            top_score = scored[0].get("match_score", 0) if scored else 0
            log_area.push(f"[{ts()}] Top match score: {top_score:.0f}%")

            # Step 4: SP-API brand enrichment (optional)
            brand_data: dict[str, dict] = {}
            if SP_API_REFRESH_TOKEN:
                try:
                    step_label.text = "Enriching brand data via SP-API..."
                    progress.value = 0.65
                    unique_asins = list({c.get("asin") for c in results["competitors"] if c.get("asin")})
                    log_area.push(f"[{ts()}] Enriching brands for {len(unique_asins)} ASINs...")
                    sp_client = SPAPIClient()
                    brand_data = await asyncio.get_event_loop().run_in_executor(
                        None, sp_client.enrich_asins, unique_asins,
                    )
                    log_area.push(f"[{ts()}] Brand data enriched for {len(brand_data)} ASINs")
                except Exception as exc:
                    logger.warning("SP-API enrichment failed: %s", exc)
                    log_area.push(f"[{ts()}] SP-API enrichment skipped: {exc}")

            # Step 5: Store in database
            step_label.text = "Saving results to database..."
            progress.value = 0.80
            log_area.push(f"[{ts()}] Storing search session and competitors...")

            db = get_session()
            try:
                new_session = SearchSession(
                    product_id=pid,
                    search_query=query,
                    amazon_domain=_selected_domain,
                    total_results=results.get("total_results_across_pages", comp_count),
                    organic_results=results["total_organic"],
                    sponsored_results=results["total_sponsored"],
                    avg_price=analysis["price_mean"],
                    avg_rating=analysis["avg_rating"],
                    avg_reviews=analysis["avg_reviews"],
                )
                db.add(new_session)
                db.flush()

                seen_asins: set[str] = set()
                score_by_asin = {}
                for s in scored:
                    a = s.get("asin")
                    if a:
                        score_by_asin[a] = s.get("match_score")

                added_count = 0
                for comp in results["competitors"]:
                    asin = comp.get("asin", "")
                    if asin and asin in seen_asins:
                        continue
                    if asin:
                        seen_asins.add(asin)
                    amazon_comp = AmazonCompetitor(
                        product_id=pid,
                        search_session_id=new_session.id,
                        asin=asin,
                        title=comp.get("title"),
                        price=comp.get("price"),
                        rating=comp.get("rating"),
                        review_count=comp.get("review_count"),
                        bought_last_month=comp.get("bought_last_month"),
                        is_prime=comp.get("is_prime", False),
                        badge=comp.get("badge"),
                        thumbnail_url=comp.get("thumbnail_url"),
                        amazon_url=comp.get("amazon_url"),
                        is_sponsored=comp.get("is_sponsored", False),
                        position=comp.get("position"),
                        match_score=score_by_asin.get(asin),
                        brand=brand_data.get(asin, {}).get("brand"),
                        manufacturer=brand_data.get(asin, {}).get("manufacturer"),
                    )
                    db.add(amazon_comp)
                    added_count += 1

                # Auto-update product status to "researched"
                p_obj = db.query(Product).filter(Product.id == pid).first()
                if p_obj and p_obj.status == "imported":
                    p_obj.status = "researched"
                    log_entries = json.loads(p_obj.decision_log or "[]")
                    log_entries.append({
                        "date": datetime.utcnow().isoformat(),
                        "action": "status_changed",
                        "detail": "Imported -> Researched (auto: Amazon research)",
                    })
                    p_obj.decision_log = json.dumps(log_entries)

                db.commit()
                log_area.push(
                    f"[{ts()}] Saved {added_count} competitors to session #{new_session.id}"
                )
            finally:
                db.close()

            # Done
            progress.value = 1.0
            step_label.text = f"Research complete! {added_count} competitors found."
            log_area.push(
                f"[{ts()}] Done! Opportunity: {analysis['opportunity_score']:.0f}/100,"
                f" Competition: {analysis['competition_score']:.0f}/100"
            )
            ui.notify(
                f"Research complete! Found {added_count} competitors{dept_label}.",
                type="positive",
            )

            # Auto-close dialog and reload page after a short delay
            async def _close_and_reload():
                await asyncio.sleep(1.5)
                dlg.close()
                ui.run_javascript("location.reload()")
            asyncio.ensure_future(_close_and_reload())

        except AmazonSearchError as exc:
            progress.value = 1.0
            step_label.text = f"Error: {exc}"
            log_area.push(f"[{ts()}] ERROR: {exc}")
            close_btn.visible = True
            close_btn.on_click(lambda: (dlg.close(), rerun_btn.enable()))
            ui.notify(f"Research failed: {exc}", type="negative")
        except Exception as exc:
            progress.value = 1.0
            step_label.text = f"Unexpected error: {exc}"
            log_area.push(f"[{ts()}] UNEXPECTED ERROR: {exc}")
            logger.exception("Unexpected error in _rerun_research")
            close_btn.visible = True
            close_btn.on_click(lambda: (dlg.close(), rerun_btn.enable()))
            ui.notify(f"Research failed: {exc}", type="negative")

    # --- No research data yet ---
    if not latest_session:
        with ui.card().classes("w-full p-5"):
            section_header("Amazon Competition Analysis", icon="groups")
            ui.label(
                "No research data yet. Run Amazon Research or import a Helium 10 Xray file."
            ).classes("text-body2 text-secondary")
            with ui.row().classes("gap-2 flex-wrap items-center"):
                _mp_options = {d: info["label"] for d, info in AMAZON_MARKETPLACES.items()}
                marketplace_select = ui.select(
                    options=_mp_options,
                    value="amazon.com",
                    label="Marketplace",
                ).props("outlined dense").classes("w-56")
                rerun_btn = ui.button(
                    "Run Research", icon="search",
                    on_click=_rerun_research,
                ).props("color=positive")
                rerun_status = ui.label("").classes(
                    "text-caption text-secondary self-center"
                )

                # Xray import (creates a new session on the fly)
                async def _handle_xray_no_session(e):
                    try:
                        file_content = await e.file.read()
                        filename = e.file.name
                        ui.notify(f"Read {len(file_content)} bytes from {filename}", type="info")
                        importer = XrayImporter()
                        parsed = await asyncio.get_event_loop().run_in_executor(
                            None, importer.parse_xray_file, file_content, filename,
                        )
                        if not parsed:
                            ui.notify(f"No valid ASIN rows found in {filename}. Check column names.", type="warning")
                            return
                        ui.notify(f"Parsed {len(parsed)} competitors from Xray", type="info")
                        # Create a new search session for the Xray import
                        db = get_session()
                        try:
                            new_sess = SearchSession(
                                product_id=product.id,
                                search_query=f"Xray import: {filename}",
                                amazon_domain="amazon.com",
                                total_results=len(parsed),
                            )
                            db.add(new_sess)
                            db.flush()
                            sid = new_sess.id
                            db.commit()
                        finally:
                            db.close()
                        result = await asyncio.get_event_loop().run_in_executor(
                            None, importer.import_xray, product.id, sid, parsed,
                        )
                        enriched = result.get("enriched", 0)
                        added = result.get("added", 0)
                        ui.notify(
                            f"Xray imported: {enriched} enriched, {added} new competitors",
                            type="positive",
                        )
                        # Update product status
                        db = get_session()
                        try:
                            p = db.query(Product).filter(Product.id == product.id).first()
                            if p and p.status == "imported":
                                p.status = "researched"
                                log_entries = json.loads(p.decision_log or "[]")
                                log_entries.append({
                                    "date": datetime.utcnow().isoformat(),
                                    "action": "status_changed",
                                    "detail": "Imported -> Researched (auto: Xray import)",
                                })
                                p.decision_log = json.dumps(log_entries)
                                db.commit()
                        finally:
                            db.close()
                        ui.navigate.to(f"/products/{product.id}")
                    except Exception as exc:
                        ui.notify(f"Xray import failed: {exc}", type="negative")

                ui.upload(
                    label="Import Xray",
                    auto_upload=True,
                    on_upload=_handle_xray_no_session,
                ).props(
                    'accept=".xlsx,.xls,.csv" max-file-size=10485760 flat dense color=accent'
                ).classes("w-40").style("font-size:12px")
        return

    # --- Has research data ---
    session_id = latest_session.id
    _saved_pagination = [None]  # mutable container to preserve pagination across refreshes

    # Metrics header with re-research + Xray upload buttons
    with ui.row().classes("items-center gap-4 w-full"):
        ui.icon("groups").classes("text-accent")
        ui.label("Amazon Competition Analysis").classes("text-subtitle1 font-bold")
        _mp_options = {d: info["label"] for d, info in AMAZON_MARKETPLACES.items()}
        marketplace_select = ui.select(
            options=_mp_options,
            value="amazon.com",
            label="Marketplace",
        ).props("outlined dense").classes("w-56")
        rerun_btn = ui.button(
            "Re-run Research", icon="refresh",
            on_click=_rerun_research,
        ).props("flat dense color=primary size=sm")
        rerun_status = ui.label("").classes(
            "text-caption text-secondary"
        )

        # --- Xray import button ---
        async def _handle_xray_upload(e):
            """Handle Helium 10 Xray Excel upload."""
            try:
                file_content = await e.file.read()
                filename = e.file.name
                xray_status.text = f"Importing {filename}..."

                importer = XrayImporter()
                parsed = await asyncio.get_event_loop().run_in_executor(
                    None, importer.parse_xray_file, file_content, filename,
                )

                if not parsed:
                    xray_status.text = "No valid rows found."
                    ui.notify("Xray file had no valid ASIN rows.", type="warning")
                    return

                result = await asyncio.get_event_loop().run_in_executor(
                    None, importer.import_xray, product.id, session_id, parsed,
                )

                enriched = result.get("enriched", 0)
                added = result.get("added", 0)
                skipped = result.get("skipped", 0)
                errors = result.get("errors", [])

                msg = f"Xray import: {enriched} enriched, {added} new, {skipped} skipped"
                xray_status.text = msg
                ui.notify(msg, type="positive")

                if errors:
                    for err in errors[:3]:
                        ui.notify(err, type="warning")

                _competition_section.refresh()

            except Exception as exc:
                xray_status.text = f"Error: {exc}"
                ui.notify(f"Xray import failed: {exc}", type="negative")

        ui.space()
        with ui.row().classes("items-center gap-2"):
            ui.upload(
                label="Import Xray",
                auto_upload=True,
                on_upload=_handle_xray_upload,
            ).props(
                'accept=".xlsx,.xls,.csv" max-file-size=10485760 flat dense color=accent'
            ).classes("w-40").style("font-size:12px")
            xray_status = ui.label("").classes("text-caption text-secondary")

    ui.label(
        f"Last researched: "
        f"{latest_session.created_at.strftime('%Y-%m-%d %H:%M') if latest_session.created_at else 'N/A'}"
    ).classes("text-caption text-secondary mb-2")

    @ui.refreshable
    def _competition_section():
        """Render stats + competitor table (refreshable on delete)."""
        db = get_session()
        try:
            sess = db.query(SearchSession).filter(SearchSession.id == session_id).first()
            comps = (
                db.query(AmazonCompetitor)
                .filter(AmazonCompetitor.search_session_id == session_id)
                .order_by(AmazonCompetitor.position)
                .all()
            )

            # Build stats from live competitor data
            prices = [c.price for c in comps if c.price is not None]
            ratings = [c.rating for c in comps if c.rating is not None]
            reviews = [c.review_count for c in comps if c.review_count is not None]
            n_comps = len(comps)
            avg_price = _stats.mean(prices) if prices else None
            avg_rating = _stats.mean(ratings) if ratings else None
            avg_reviews = int(_stats.mean(reviews)) if reviews else 0

            # Compute trend data (compare with previous session)
            _trend_data = None
            try:
                _trend_data = compute_trends(product_id)
            except Exception:
                pass
            _deltas = _trend_data.get("deltas", {}) if _trend_data else {}

            def _delta_badge(value, fmt="num", invert=False):
                """Render a small delta badge next to a stats card."""
                if value is None or value == 0:
                    return
                is_positive = value > 0
                # For price: up is bad (red), down is good (green)
                # For rating: up is good, down is bad
                if invert:
                    color = "red" if is_positive else "green"
                    icon = "trending_up" if is_positive else "trending_down"
                else:
                    color = "green" if is_positive else "red"
                    icon = "trending_up" if is_positive else "trending_down"
                sign = "+" if is_positive else ""
                if fmt == "price":
                    text = f"{sign}${value:.2f}"
                elif fmt == "float":
                    text = f"{sign}{value:.1f}"
                else:
                    text = f"{sign}{value}"
                with ui.row().classes("items-center gap-0"):
                    ui.icon(icon, size="14px").style(f"color: {color}")
                    ui.label(text).classes("text-caption font-bold").style(f"color: {color}")

            with ui.row().classes("gap-4 flex-wrap"):
                with ui.column().classes("gap-0"):
                    stats_card("Competitors", str(n_comps), "groups", "primary")
                    _delta_badge(_deltas.get("competitor_count_change"))
                with ui.column().classes("gap-0"):
                    stats_card(
                        "Avg Price",
                        f"${avg_price:.2f}" if avg_price else "N/A",
                        "attach_money", "positive",
                    )
                    _delta_badge(_deltas.get("avg_price_change"), fmt="price", invert=True)
                with ui.column().classes("gap-0"):
                    stats_card(
                        "Avg Rating",
                        f"{avg_rating:.1f}" if avg_rating else "N/A",
                        "star", "accent",
                    )
                    _delta_badge(_deltas.get("avg_rating_change"), fmt="float")
                stats_card(
                    "Avg Reviews",
                    str(avg_reviews),
                    "reviews", "secondary",
                )

            if comps:
                comp_data = [
                    {
                        "position": c.position,
                        "title": c.title,
                        "asin": c.asin,
                        "brand": c.brand,
                        "price": c.price,
                        "rating": c.rating,
                        "review_count": c.review_count,
                        "bought_last_month": c.bought_last_month,
                        "badge": c.badge,
                        "is_prime": c.is_prime,
                        "is_sponsored": c.is_sponsored,
                        "amazon_url": c.amazon_url,
                        "thumbnail_url": c.thumbnail_url,
                        "match_score": c.match_score,
                        "reviewed": c.reviewed,
                        # Xray / Helium 10 fields
                        "monthly_sales": c.monthly_sales,
                        "monthly_revenue": c.monthly_revenue,
                        "seller": c.seller,
                        "fulfillment": c.fulfillment,
                        "fba_fees": c.fba_fees,
                        "weight": c.weight,
                    }
                    for c in comps
                ]

                def _recalc_session_stats(db_sess):
                    """Recalculate session stats from remaining competitors."""
                    remaining = (
                        db_sess.query(AmazonCompetitor)
                        .filter(AmazonCompetitor.search_session_id == session_id)
                        .all()
                    )
                    r_prices = [c.price for c in remaining if c.price is not None]
                    r_ratings = [c.rating for c in remaining if c.rating is not None]
                    r_reviews = [c.review_count for c in remaining if c.review_count is not None]

                    sess_obj = db_sess.query(SearchSession).filter(SearchSession.id == session_id).first()
                    if sess_obj:
                        sess_obj.organic_results = len(remaining)
                        sess_obj.avg_price = _stats.mean(r_prices) if r_prices else None
                        sess_obj.avg_rating = _stats.mean(r_ratings) if r_ratings else None
                        sess_obj.avg_reviews = int(_stats.mean(r_reviews)) if r_reviews else None

                def _delete_competitor(asin: str):
                    """Delete a competitor by ASIN and recalculate session stats."""
                    db2 = get_session()
                    try:
                        comp = (
                            db2.query(AmazonCompetitor)
                            .filter(
                                AmazonCompetitor.search_session_id == session_id,
                                AmazonCompetitor.asin == asin,
                            )
                            .first()
                        )
                        if comp:
                            db2.delete(comp)
                            db2.flush()
                            _recalc_session_stats(db2)
                            db2.commit()
                            ui.notify(f"Removed competitor {asin}", type="positive")
                        else:
                            ui.notify(f"Competitor {asin} not found", type="warning")
                    finally:
                        db2.close()
                    _competition_section.refresh()

                def _bulk_delete_competitors(asins: list[str]):
                    """Delete multiple competitors and recalculate stats once."""
                    db2 = get_session()
                    try:
                        deleted = 0
                        for asin in asins:
                            comp = (
                                db2.query(AmazonCompetitor)
                                .filter(
                                    AmazonCompetitor.search_session_id == session_id,
                                    AmazonCompetitor.asin == asin,
                                )
                                .first()
                            )
                            if comp:
                                db2.delete(comp)
                                deleted += 1
                        if deleted:
                            db2.flush()
                            _recalc_session_stats(db2)
                            db2.commit()
                            ui.notify(
                                f"Removed {deleted} competitor{'s' if deleted != 1 else ''}",
                                type="positive",
                            )
                    finally:
                        db2.close()
                    _competition_section.refresh()

                def _update_score(asin: str, new_score: float):
                    """Update a competitor's relevance score in the DB."""
                    db3 = get_session()
                    try:
                        comp = (
                            db3.query(AmazonCompetitor)
                            .filter(
                                AmazonCompetitor.search_session_id == session_id,
                                AmazonCompetitor.asin == asin,
                            )
                            .first()
                        )
                        if comp:
                            comp.match_score = new_score
                            db3.commit()
                            ui.notify(f"Relevance for {asin} set to {new_score:.0f}", type="info")
                    finally:
                        db3.close()

                def _toggle_reviewed(asin: str, checked: bool):
                    """Mark a competitor as seen/unseen in the DB."""
                    db4 = get_session()
                    try:
                        comp = (
                            db4.query(AmazonCompetitor)
                            .filter(
                                AmazonCompetitor.search_session_id == session_id,
                                AmazonCompetitor.asin == asin,
                            )
                            .first()
                        )
                        if comp:
                            comp.reviewed = checked
                            db4.commit()
                    finally:
                        db4.close()

                def _update_competitor_field(asin: str, field_name: str, raw_value):
                    """Update any field on a competitor by ASIN, recalculate stats."""
                    _FIELD_MAP = {
                        "price": ("price", float),
                        "brand": ("brand", str),
                        "seller": ("seller", str),
                        "fulfillment": ("fulfillment", str),
                        "rating": ("rating", float),
                        "review_count": ("review_count", int),
                        "bought_last_month": ("bought_last_month", str),
                        "monthly_sales": ("monthly_sales", int),
                        "monthly_revenue": ("monthly_revenue", float),
                        "fba_fees": ("fba_fees", float),
                        "is_prime": ("is_prime", bool),
                        "weight": ("weight", float),
                    }
                    mapping = _FIELD_MAP.get(field_name)
                    if not mapping:
                        return
                    col_name, cast_fn = mapping
                    try:
                        if raw_value is None or str(raw_value).strip() == "":
                            typed_value = None
                        elif cast_fn == bool:
                            typed_value = raw_value in (True, "true", "True", "Yes", 1)
                        else:
                            typed_value = cast_fn(raw_value)
                    except (ValueError, TypeError):
                        ui.notify(f"Invalid value for {field_name}", type="warning")
                        return
                    db5 = get_session()
                    try:
                        comp = (
                            db5.query(AmazonCompetitor)
                            .filter(
                                AmazonCompetitor.product_id == product_id,
                                AmazonCompetitor.asin == asin,
                            )
                            .first()
                        )
                        if comp:
                            setattr(comp, col_name, typed_value)
                            db5.flush()
                            # Recalculate session-level stats when numeric fields change
                            if field_name in ("price", "rating", "review_count"):
                                _recalc_session_stats(db5)
                            db5.commit()
                    finally:
                        db5.close()
                    # Refresh stats dynamically
                    _competition_section.refresh()

                # Reviewed progress summary
                _reviewed_count = sum(1 for c in comp_data if c.get("reviewed"))
                _total_comps = len(comp_data)
                _review_pct = _reviewed_count / _total_comps if _total_comps > 0 else 0
                with ui.row().classes("w-full items-center gap-3 mt-2 mb-1"):
                    ui.icon("fact_check", size="sm").classes("text-secondary")
                    ui.label(
                        f"Reviewed {_reviewed_count} of {_total_comps} competitors"
                    ).classes("text-caption text-secondary")
                    ui.linear_progress(
                        value=_review_pct,
                        color="accent" if _review_pct < 1 else "positive",
                    ).classes("flex-1").props("rounded size=6px")
                    if _review_pct >= 1.0:
                        ui.icon("check_circle", size="sm").classes("text-positive")

                competitor_table(
                    comp_data,
                    on_delete=_delete_competitor,
                    on_bulk_delete=_bulk_delete_competitors,
                    on_score_change=_update_score,
                    on_review_toggle=_toggle_reviewed,
                    on_field_change=_update_competitor_field,
                    pagination_state=_saved_pagination[0],
                    on_pagination_change=lambda p: _saved_pagination.__setitem__(0, p),
                    trend_data=_trend_data,
                )

        finally:
            db.close()

    _competition_section()


def _render_analysis_tab(product, latest_session):
    """Render the Analysis tab: VVS banner, brand landscape, profit analysis, AI insights."""
    _product_thumbnail(product)
    if not latest_session:
        with ui.card().classes("w-full p-5"):
            ui.icon("analytics").classes("text-secondary text-h4")
            ui.label("No research data yet.").classes("text-subtitle1 font-bold mt-2")
            ui.label(
                "Run Amazon Research from the Competitors tab first to unlock analysis."
            ).classes("text-body2 text-secondary")
        return

    session_id = latest_session.id
    db = get_session()
    try:
        comps = (
            db.query(AmazonCompetitor)
            .filter(AmazonCompetitor.search_session_id == session_id)
            .order_by(AmazonCompetitor.position)
            .all()
        )

        # --- VVS Verdict Banner + Dimension Breakdown ---
        if comps:
            _vvs_comp_data = [
                {
                    "price": c.price, "rating": c.rating,
                    "review_count": c.review_count,
                    "bought_last_month": c.bought_last_month,
                    "badge": c.badge, "is_prime": c.is_prime,
                    "is_sponsored": c.is_sponsored,
                    "position": c.position,
                    "brand": c.brand, "manufacturer": c.manufacturer,
                    "seller": c.seller, "seller_country": c.seller_country,
                    "monthly_revenue": c.monthly_revenue,
                }
                for c in comps
            ]
            _alibaba_cost = product.alibaba_price_min if product.alibaba_price_min is not None else None
            _render_vvs_banner(product, _vvs_comp_data, _alibaba_cost)

        # --- Brand Landscape card ---
        if comps:
            comp_data = [
                {
                    "position": c.position, "title": c.title, "asin": c.asin,
                    "brand": c.brand, "price": c.price, "rating": c.rating,
                    "review_count": c.review_count,
                    "bought_last_month": c.bought_last_month,
                    "badge": c.badge, "is_prime": c.is_prime,
                    "is_sponsored": c.is_sponsored,
                    "amazon_url": c.amazon_url, "thumbnail_url": c.thumbnail_url,
                    "match_score": c.match_score,
                    "monthly_sales": c.monthly_sales,
                    "monthly_revenue": c.monthly_revenue,
                    "manufacturer": c.manufacturer,
                    "seller": c.seller, "seller_country": c.seller_country,
                }
                for c in comps
            ]
            _render_brand_landscape(comp_data)

        # --- Brand Concentration (Moat Detector) ---
        if comps:
            _render_brand_concentration(comp_data)

        # --- AI Insights card ---
        _render_ai_insights(product, comps if comps else [])

        # --- PPC Keyword Intelligence ---
        if comps:
            _render_ppc_keywords(product, product.id, comp_data)
    finally:
        db.close()


def _render_history_tab(all_sessions, product_id, product=None):
    """Render the History tab: timeline chart + session list."""
    if product:
        _product_thumbnail(product)
    if not all_sessions:
        with ui.card().classes("w-full p-5"):
            ui.icon("history").classes("text-secondary text-h4")
            ui.label("No research sessions yet.").classes("text-subtitle1 font-bold mt-2")
            ui.label(
                "Research sessions will appear here after you run Amazon Research or import Xray data."
            ).classes("text-body2 text-secondary")
        return

    # --- Trend timeline chart (if 2+ sessions) ---
    trend_data = None
    try:
        trend_data = compute_trends(product_id)
    except Exception:
        pass

    if trend_data and trend_data.get("timeline") and len(trend_data["timeline"]) >= 2:
        timeline = trend_data["timeline"]
        dates = [t["date"][:10] if t.get("date") else "N/A" for t in timeline]
        prices = [round(t["avg_price"], 2) if t.get("avg_price") else None for t in timeline]
        comps = [t["competitor_count"] for t in timeline]
        ratings = [round(t["avg_rating"], 1) if t.get("avg_rating") else None for t in timeline]

        with ui.card().classes("w-full p-5"):
            section_header("Trend Over Time", icon="show_chart")
            ui.echart({
                "tooltip": {"trigger": "axis"},
                "legend": {"data": ["Avg Price ($)", "Competitors", "Avg Rating"], "bottom": 0},
                "xAxis": {"type": "category", "data": dates, "axisLabel": {"rotate": 30}},
                "yAxis": [
                    {"type": "value", "name": "Price ($)", "position": "left"},
                    {"type": "value", "name": "Count / Rating", "position": "right"},
                ],
                "series": [
                    {"name": "Avg Price ($)", "data": prices, "type": "line",
                     "color": "#A08968", "smooth": True, "symbol": "circle", "symbolSize": 8},
                    {"name": "Competitors", "data": comps, "type": "bar",
                     "yAxisIndex": 1, "color": "#68839E", "barWidth": "30%", "opacity": 0.6},
                    {"name": "Avg Rating", "data": ratings, "type": "line",
                     "yAxisIndex": 1, "color": "#6B8E68", "smooth": True,
                     "symbol": "diamond", "symbolSize": 8},
                ],
                "grid": {"bottom": 70, "top": 30},
            }).classes("w-full h-72")

        # --- Trend delta summary ---
        deltas = trend_data.get("deltas", {})
        ct = trend_data.get("competitor_trends", {})
        new_count = sum(1 for v in ct.values() if v.get("status") == "new")
        gone_count = sum(1 for v in ct.values() if v.get("status") == "gone")

        if any([deltas.get("avg_price_change"), deltas.get("competitor_count_change"),
                new_count, gone_count]):
            with ui.row().classes("gap-3 flex-wrap mb-4"):
                if deltas.get("competitor_count_change") and deltas["competitor_count_change"] != 0:
                    val = deltas["competitor_count_change"]
                    sign = "+" if val > 0 else ""
                    ui.chip(f"{sign}{val} competitors", icon="groups",
                            color="blue" if val > 0 else "orange").props("dense outline")
                if new_count:
                    ui.chip(f"{new_count} NEW", icon="fiber_new", color="green").props("dense")
                if gone_count:
                    ui.chip(f"{gone_count} GONE", icon="remove_circle", color="red").props("dense")
                if deltas.get("avg_price_change") and deltas["avg_price_change"] != 0:
                    val = deltas["avg_price_change"]
                    sign = "+" if val > 0 else ""
                    color = "red" if val > 0 else "green"
                    ui.chip(f"{sign}${val:.2f} avg price", icon="attach_money",
                            color=color).props("dense outline")

    ui.label(f"{len(all_sessions)} research session{'s' if len(all_sessions) != 1 else ''}").classes(
        "text-subtitle1 font-bold mb-2"
    )

    for i, sess in enumerate(all_sessions):
        is_latest = i == 0
        created = sess.created_at.strftime("%b %d, %Y %H:%M") if sess.created_at else "N/A"

        with ui.card().classes("w-full p-5" + (" border-l-4" if is_latest else "")).style(
            "border-left-color: #A08968" if is_latest else ""
        ):
            with ui.row().classes("items-center gap-3 w-full"):
                ui.icon("science" if not sess.search_query.startswith("Xray") else "upload_file").classes(
                    "text-primary" if is_latest else "text-secondary"
                )
                with ui.column().classes("flex-1 gap-0"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label(sess.search_query or "Unknown query").classes(
                            "text-body1 font-medium"
                        )
                        if is_latest:
                            ui.badge("Latest", color="accent").props("dense")
                    ui.label(created).classes("text-caption text-grey-6")

                # Stats chips
                with ui.row().classes("gap-2 flex-wrap"):
                    if sess.organic_results is not None:
                        ui.chip(
                            f"{sess.organic_results} competitors",
                            icon="groups",
                        ).props("dense outline size=sm")
                    if sess.avg_price is not None:
                        ui.chip(
                            f"${sess.avg_price:.2f} avg",
                            icon="attach_money",
                        ).props("dense outline size=sm")
                    if sess.avg_rating is not None:
                        ui.chip(
                            f"{sess.avg_rating:.1f} rating",
                            icon="star",
                        ).props("dense outline size=sm")
                    if sess.avg_reviews is not None:
                        ui.chip(
                            f"{sess.avg_reviews} reviews",
                            icon="reviews",
                        ).props("dense outline size=sm")


# ====================================================================
# Helper rendering functions (unchanged)
# ====================================================================

def _render_vvs_banner(product, comp_data: list[dict], alibaba_cost):
    """Render the VVS verdict banner and dimension breakdown."""
    try:
        vvs = calculate_vvs(product, comp_data, alibaba_cost=alibaba_cost)
    except Exception:
        return

    score = vvs.get("vvs_score", 0)
    verdict = vvs.get("verdict", "N/A")
    verdict_color = vvs.get("verdict_color", "grey")
    recommendation = vvs.get("recommendation", "")
    dimensions = vvs.get("dimensions", {})

    if score == 0 and not dimensions:
        return

    # Color mapping for banner background
    _color_map = {
        "green": "#2E7D32",
        "yellow": "#F9A825",
        "orange": "#EF6C00",
        "red": "#C62828",
    }
    _text_color_map = {
        "green": "white",
        "yellow": "#333",
        "orange": "white",
        "red": "white",
    }
    bg = _color_map.get(verdict_color, "#616161")
    fg = _text_color_map.get(verdict_color, "white")

    # Verdict Banner
    with ui.card().classes("w-full p-0 mt-4 overflow-hidden").style("border: none"):
        with ui.row().classes(
            "w-full items-center gap-4 px-6 py-4"
        ).style(f"background: {bg}; color: {fg}"):
            # Large VVS score number
            with ui.column().classes("items-center").style("min-width: 80px"):
                ui.label(f"{score}").classes("text-h3 font-bold").style(f"color: {fg}; line-height: 1")
                ui.label("/ 10").classes("text-caption").style(f"color: {fg}; opacity: 0.8")

            # Verdict text and recommendation
            with ui.column().classes("flex-1 gap-1"):
                ui.label(verdict).classes("text-h6 font-bold").style(f"color: {fg}")
                if recommendation:
                    ui.label(recommendation).classes("text-body2").style(f"color: {fg}; opacity: 0.9")

            # VVS badge
            ui.label("VVS").classes("text-h6 font-bold").style(
                f"color: {fg}; opacity: 0.4; letter-spacing: 4px"
            )

        # Dimension breakdown below the banner
        if dimensions:
            with ui.row().classes("w-full gap-4 flex-wrap px-4 py-3").style(
                "background: #fafafa"
            ):
                _dim_labels = {
                    "demand": ("Demand", "trending_up"),
                    "competition": ("Competition", "groups"),
                    "profitability": ("Profitability", "attach_money"),
                    "market_quality": ("Mkt Quality", "assessment"),
                    "differentiation": ("Differtn.", "lightbulb"),
                    "brand_moat": ("Brand Moat", "shield"),
                }
                for dim_key in ("demand", "competition", "profitability", "market_quality", "differentiation", "brand_moat"):
                    dim = dimensions.get(dim_key)
                    if not dim:
                        continue
                    label, icon_name = _dim_labels.get(dim_key, (dim_key, "circle"))
                    dim_score = dim["score"]
                    # Color the bar based on score
                    if dim_score >= 7:
                        bar_color = "positive"
                    elif dim_score >= 4:
                        bar_color = "warning"
                    else:
                        bar_color = "negative"

                    with ui.column().classes("items-center gap-1").style("min-width: 100px; flex: 1"):
                        with ui.row().classes("items-center gap-1"):
                            ui.icon(icon_name, size="xs").classes(f"text-{bar_color}")
                            ui.label(label).classes("text-caption font-medium")
                        ui.linear_progress(
                            value=dim_score / 10.0, color=bar_color,
                        ).classes("w-full").props("rounded size=8px")
                        ui.label(f"{dim_score}/10").classes("text-caption text-secondary")
                        if dim.get("details"):
                            ui.tooltip(dim["details"])


def _render_brand_landscape(comp_data: list[dict]):
    """Render the Brand Landscape card aggregating competitor brands."""
    # Aggregate brands from comp_data
    brand_agg: dict[str, dict] = {}
    for c in comp_data:
        brand = c.get("brand") or None
        if not brand:
            brand = "Unknown"
        if brand not in brand_agg:
            brand_agg[brand] = {
                "count": 0,
                "prices": [],
                "ratings": [],
                "total_revenue": 0.0,
            }
        agg = brand_agg[brand]
        agg["count"] += 1
        if c.get("price") is not None:
            agg["prices"].append(c["price"])
        if c.get("rating") is not None:
            agg["ratings"].append(c["rating"])
        # Revenue estimate: price * bought
        price = c.get("price")
        bought = parse_bought(c.get("bought_last_month"))
        if price is not None and bought is not None and bought > 0:
            agg["total_revenue"] += price * bought

    if not brand_agg:
        return

    # Compute total revenue for market share
    total_revenue = sum(a["total_revenue"] for a in brand_agg.values())

    # Build sorted brand rows (by total revenue desc)
    brand_rows = []
    for brand_name, agg in brand_agg.items():
        avg_price = _stats.mean(agg["prices"]) if agg["prices"] else None
        avg_rating = _stats.mean(agg["ratings"]) if agg["ratings"] else None
        market_share = (agg["total_revenue"] / total_revenue * 100) if total_revenue > 0 else 0
        brand_rows.append({
            "brand": brand_name,
            "count": agg["count"],
            "avg_price": avg_price,
            "avg_rating": avg_rating,
            "total_revenue": agg["total_revenue"],
            "market_share": market_share,
        })

    brand_rows.sort(key=lambda r: r["total_revenue"], reverse=True)

    with ui.card().classes("w-full p-5 mt-4"):
        with ui.row().classes("items-center gap-2 mb-3"):
            ui.icon("business").classes("text-accent")
            ui.label("Brand Landscape").classes("text-subtitle1 font-bold")

        # High concentration warning
        if brand_rows and brand_rows[0]["market_share"] > 40:
            with ui.row().classes("items-center gap-2 mb-3 px-3 py-2").style(
                "background: #FFF3E0; border-radius: 8px"
            ):
                ui.icon("warning").classes("text-warning")
                ui.label(
                    f"High brand concentration - \"{brand_rows[0]['brand']}\" holds "
                    f"{brand_rows[0]['market_share']:.0f}% market share"
                ).classes("text-body2 text-warning")

        # Brand table
        brand_columns = [
            {"name": "brand", "label": "Brand", "field": "brand", "sortable": True, "align": "left"},
            {"name": "count", "label": "Products", "field": "count", "sortable": True, "align": "center"},
            {"name": "avg_price", "label": "Avg Price", "field": "avg_price_raw", "sortable": True, "align": "right"},
            {"name": "avg_rating", "label": "Avg Rating", "field": "avg_rating_raw", "sortable": True, "align": "center"},
            {"name": "total_revenue", "label": "Est. Revenue/Mo", "field": "total_revenue_raw", "sortable": True, "align": "right"},
            {"name": "market_share", "label": "Market Share", "field": "market_share_raw", "sortable": True, "align": "right"},
        ]

        table_rows = []
        for i, br in enumerate(brand_rows):
            table_rows.append({
                "brand": br["brand"],
                "count": br["count"],
                "avg_price_raw": br["avg_price"],
                "avg_rating_raw": br["avg_rating"],
                "total_revenue_raw": br["total_revenue"],
                "market_share_raw": br["market_share"],
                "_is_top": i == 0 and br["market_share"] > 0,
            })

        brand_table = ui.table(
            columns=brand_columns,
            rows=table_rows,
            row_key="brand",
            pagination={"rowsPerPage": 10, "sortBy": "total_revenue", "descending": True},
        ).classes("w-full")
        brand_table.props("flat bordered dense")

        # Format cells
        brand_table.add_slot('body-cell-brand', r'''
            <q-td :props="props">
                <span :style="props.row._is_top ? 'font-weight:bold; color:#2E7D32' : ''">
                    {{ props.row.brand }}
                </span>
                <q-icon v-if="props.row._is_top" name="emoji_events" size="14px"
                        style="color:#F9A825; margin-left:4px" />
            </q-td>
        ''')

        brand_table.add_slot('body-cell-avg_price', r'''
            <q-td :props="props">
                <span v-if="props.row.avg_price_raw != null">
                    ${{ props.row.avg_price_raw.toFixed(2) }}
                </span>
                <span v-else style="color:#999">-</span>
            </q-td>
        ''')

        brand_table.add_slot('body-cell-avg_rating', r'''
            <q-td :props="props">
                <span v-if="props.row.avg_rating_raw != null">
                    {{ props.row.avg_rating_raw.toFixed(1) }}
                </span>
                <span v-else style="color:#999">-</span>
            </q-td>
        ''')

        brand_table.add_slot('body-cell-total_revenue', r'''
            <q-td :props="props">
                <span v-if="props.row.total_revenue_raw > 0"
                      :style="{
                          color: props.row.total_revenue_raw >= 10000 ? '#2e7d32' :
                                 props.row.total_revenue_raw >= 3000 ? '#f57f17' : '#666',
                          fontWeight: props.row.total_revenue_raw >= 3000 ? 'bold' : 'normal'
                      }">
                    ${{ props.row.total_revenue_raw.toLocaleString(undefined, {maximumFractionDigits: 0}) }}
                </span>
                <span v-else style="color:#999">-</span>
            </q-td>
        ''')

        brand_table.add_slot('body-cell-market_share', r'''
            <q-td :props="props">
                <span v-if="props.row.market_share_raw > 0"
                      :style="{
                          color: props.row.market_share_raw > 40 ? '#c62828' :
                                 props.row.market_share_raw > 20 ? '#f57f17' : '#666',
                          fontWeight: props.row.market_share_raw > 20 ? 'bold' : 'normal'
                      }">
                    {{ props.row.market_share_raw.toFixed(1) }}%
                </span>
                <span v-else style="color:#999">-</span>
            </q-td>
        ''')


def _render_brand_concentration(comp_data: list[dict]):
    """Render the Brand Concentration / Moat Detector card with pie chart and risk flags."""
    conc = compute_brand_concentration(comp_data)
    if not conc or not conc.get("seller_type_distribution"):
        return

    moat_score = conc["brand_moat_score"]
    hhi = conc["hhi_score"]
    level = conc["concentration_level"]

    # Score color
    if moat_score >= 65:
        score_color = "#2E7D32"
        score_label = "Strong Opportunity"
    elif moat_score >= 40:
        score_color = "#F57F17"
        score_label = "Moderate"
    else:
        score_color = "#C62828"
        score_label = "High Risk"

    _type_colors = {
        "Amazon 1P": "#FF6F00",
        "Established Brand": "#1565C0",
        "Private Label": "#2E7D32",
        "Chinese Commodity": "#C62828",
        "Unknown": "#757575",
    }

    pie_data = []
    for item in conc["seller_type_distribution"]:
        pie_data.append({
            "name": item["name"],
            "value": item["value"],
            "itemStyle": {"color": _type_colors.get(item["name"], "#999")},
        })

    with ui.card().classes("w-full p-5 mt-4"):
        with ui.row().classes("items-center gap-2 mb-3"):
            ui.icon("shield").classes("text-accent")
            ui.label("Brand Moat Detector").classes("text-subtitle1 font-bold")
            ui.badge(
                f"Score: {moat_score}/100",
                color="green" if moat_score >= 65 else "orange" if moat_score >= 40 else "red",
            ).props("dense")

        with ui.row().classes("w-full gap-4 flex-wrap"):
            # Pie chart column
            with ui.column().classes("flex-1").style("min-width: 280px"):
                ui.label("Seller Type Distribution").classes("text-caption font-medium mb-1")
                ui.echart({
                    "tooltip": {
                        "trigger": "item",
                        "formatter": "{b}: {c} ({d}%)",
                    },
                    "series": [{
                        "type": "pie",
                        "radius": ["35%", "65%"],
                        "center": ["50%", "50%"],
                        "data": pie_data,
                        "label": {
                            "formatter": "{b}\n{d}%",
                            "fontSize": 11,
                        },
                        "emphasis": {
                            "itemStyle": {
                                "shadowBlur": 10,
                                "shadowOffsetX": 0,
                                "shadowColor": "rgba(0,0,0,0.3)",
                            }
                        },
                    }],
                }).classes("w-full").style("height: 240px")

            # Metrics + risk flags column
            with ui.column().classes("flex-1 gap-3").style("min-width: 250px"):
                # Moat score badge
                with ui.row().classes("items-center gap-3 px-3 py-2").style(
                    f"background: {score_color}11; border-radius: 8px; border-left: 4px solid {score_color}"
                ):
                    ui.label(f"{moat_score}").classes("text-h5 font-bold").style(f"color: {score_color}")
                    with ui.column().classes("gap-0"):
                        ui.label("Brand Moat Score").classes("text-caption font-medium")
                        ui.label(score_label).classes("text-caption").style(f"color: {score_color}")

                # HHI metric
                with ui.row().classes("items-center gap-2"):
                    ui.icon("analytics", size="sm").classes("text-secondary")
                    ui.label(f"HHI: {hhi:.0f}").classes("text-body2 font-medium")
                    level_color = {"high": "red", "medium": "orange", "low": "green"}.get(level, "grey")
                    ui.badge(level.upper(), color=level_color).props("dense outline")

                # Seller type counts
                with ui.column().classes("gap-1"):
                    _type_icons = {
                        "amazon_1p": ("storefront", "Amazon 1P"),
                        "established_brand": ("verified", "Established Brands"),
                        "private_label": ("inventory_2", "Private Labels"),
                        "chinese_commodity": ("public", "Chinese Commodity"),
                        "unknown": ("help_outline", "Unknown"),
                    }
                    for key, (icon, label) in _type_icons.items():
                        count = conc.get(f"{key}_count", 0)
                        if count > 0:
                            with ui.row().classes("items-center gap-2"):
                                ui.icon(icon, size="xs").classes("text-secondary")
                                ui.label(f"{label}: {count}").classes("text-caption")

                # Risk flags
                risk_flags = []
                if conc["has_amazon_1p"]:
                    risk_flags.append(("warning", "Amazon sells in this category", "#FF6F00"))
                if level == "high":
                    risk_flags.append(("error", "High brand concentration (dominant player)", "#C62828"))
                if conc["chinese_commodity_count"] > len(comp_data) * 0.3:
                    risk_flags.append(("info", "Many Chinese commodity sellers (easy to outcompete)", "#2E7D32"))

                if risk_flags:
                    ui.separator().classes("my-1")
                    for icon, text, color in risk_flags:
                        with ui.row().classes("items-center gap-2"):
                            ui.icon(icon, size="xs").style(f"color: {color}")
                            ui.label(text).classes("text-caption").style(f"color: {color}")


def _render_profitability_tab(product, latest_session):
    """Render the Profitability tab: interactive Helium-10-style calculator."""
    _product_thumbnail(product)
    from src.ui.components.profitability_calculator import profitability_calculator
    from src.services.fee_calculator import available_categories

    # Gather competitor data for pre-population
    competitors = []
    if latest_session:
        db = get_session()
        try:
            competitors = (
                db.query(AmazonCompetitor)
                .filter(AmazonCompetitor.search_session_id == latest_session.id)
                .order_by(AmazonCompetitor.position)
                .all()
            )
        finally:
            db.close()

    comp_prices = []
    comp_weights = []
    first_dimensions = None
    first_size_tier = None

    for c in competitors:
        if c.price and c.price > 0:
            comp_prices.append(c.price)
        if c.weight and c.weight > 0:
            comp_weights.append(c.weight)
        if c.dimensions and first_dimensions is None:
            first_dimensions = c.dimensions
        if c.size_tier and first_size_tier is None:
            first_size_tier = c.size_tier

    median_price = sorted(comp_prices)[len(comp_prices) // 2] if comp_prices else None
    median_weight = sorted(comp_weights)[len(comp_weights) // 2] if comp_weights else None

    alibaba_cost = product.alibaba_price_min if product.alibaba_price_min is not None else None

    category_slug = "toys-and-games"
    if hasattr(product, "category") and product.category:
        cat_name = product.category.name.lower().replace(" ", "-").replace("&", "and")
        cats = available_categories()
        if cat_name in cats:
            category_slug = cat_name

    profitability_calculator(
        product_id=product.id,
        initial_price=median_price,
        initial_cost=alibaba_cost,
        initial_dimensions=first_dimensions,
        initial_weight=median_weight,
        initial_size_tier=first_size_tier,
        initial_category=category_slug,
    )


def _render_ai_insights(product, competitors: list):
    """Render the AI Insights card if ML services are available."""
    try:
        from src.services.match_scorer import score_matches
        from src.services.price_recommender import recommend_pricing
        from src.services.demand_estimator import estimate_demand
    except ImportError:
        return  # ML services not available yet

    if not competitors:
        return

    comp_data = []
    for c in competitors:
        if isinstance(c, dict):
            comp_data.append(c)
        else:
            # ORM object -> dict
            try:
                comp_data.append({
                    "asin": c.asin, "title": c.title, "price": c.price,
                    "rating": c.rating, "review_count": c.review_count,
                    "bought_last_month": c.bought_last_month,
                    "badge": c.badge, "is_prime": c.is_prime,
                    "is_sponsored": c.is_sponsored,
                })
            except Exception:
                continue

    try:
        match_results = score_matches(product.name, comp_data)
        alibaba_cost = product.alibaba_price_min if product.alibaba_price_min is not None else None
        pricing = recommend_pricing(
            competitors=comp_data,
            alibaba_cost=alibaba_cost,
        )
        demand = estimate_demand(comp_data)
    except Exception:
        return  # Silently skip if ML fails

    with ui.card().classes("w-full p-5 mt-4"):
        with ui.row().classes("items-center gap-2 mb-3"):
            ui.icon("auto_awesome").classes("text-accent")
            ui.label("AI Insights").classes("text-subtitle1 font-bold")

        # Price strategy cards
        strategies = pricing.get("strategies") if pricing else {}
        if strategies:
            ui.label("Price Recommendations").classes("text-subtitle2 font-medium mb-2")
            strategy_labels = {
                "budget": "Budget",
                "competitive": "Competitive",
                "premium": "Premium",
            }
            with ui.row().classes("gap-4 flex-wrap mb-4"):
                for key in ("budget", "competitive", "premium"):
                    strategy = strategies.get(key)
                    if not strategy:
                        continue
                    with ui.card().classes("p-3").style("min-width:200px"):
                        ui.label(strategy_labels.get(key, key)).classes(
                            "text-caption font-bold text-uppercase"
                        )
                        ui.label(
                            f"${strategy['price']:.2f}" if strategy.get("price") else "N/A"
                        ).classes("text-h6 text-positive font-bold")
                        if strategy.get("rationale"):
                            ui.label(strategy["rationale"]).classes(
                                "text-caption text-secondary"
                            )

        # Demand estimation
        if demand:
            ui.label("Demand Estimation").classes("text-subtitle2 font-medium mb-2")
            with ui.row().classes("gap-4 flex-wrap mb-4"):
                if demand.get("tam") is not None:
                    stats_card(
                        "Total Addressable Market",
                        f"${demand['tam']:,.0f}",
                        "trending_up", "primary",
                    )
                if demand.get("avg_revenue_per_seller") is not None:
                    stats_card(
                        "Avg Revenue / Seller",
                        f"${demand['avg_revenue_per_seller']:,.0f}",
                        "payments", "positive",
                    )

        # Match relevance summary
        if match_results:
            direct_matches = sum(
                1 for m in match_results if m.get("is_direct_match", False)
            )
            total = len(match_results)
            ui.label("Match Relevance").classes("text-subtitle2 font-medium mb-2")
            ui.label(
                f"{direct_matches} of {total} competitors are direct matches"
            ).classes("text-body2 text-secondary")


def _info_row(label: str, value: str, is_link: bool = False):
    ui.label(label).classes("text-caption text-secondary font-medium")
    if is_link:
        display = value[:80] + "..." if len(value) > 80 else value
        ui.link(display, value, new_tab=True).classes("text-primary text-body2")
    else:
        ui.label(value).classes("text-body2")


# ====================================================================
# Reviews Tab
# ====================================================================

def _render_reviews_tab(product, product_id, latest_session):
    """Render the Reviews / Pain Map tab."""
    _product_thumbnail(product)
    if not latest_session:
        with ui.card().classes("w-full p-8 text-center"):
            ui.icon("science", size="xl").classes("text-grey-5 mb-4")
            ui.label("Run Amazon Research first").classes("text-h6 text-grey-5")
            ui.label("Reviews mining requires competitor data from a search session.").classes(
                "text-body2 text-grey"
            )
        return

    results_container = ui.column().classes("w-full gap-4")

    # Check for existing analysis
    existing = get_review_analysis(product_id)
    if existing:
        _render_review_results(results_container, existing)

    async def on_mine():
        btn.set_visibility(False)
        spinner.set_visibility(True)
        status_label.set_text("Mining competitor reviews via SerpAPI...")
        status_label.set_visibility(True)
        try:
            result = await asyncio.get_event_loop().run_in_executor(None, mine_reviews, product_id)
            spinner.set_visibility(False)
            if result["errors"]:
                for err in result["errors"]:
                    ui.notify(err, type="warning")
            if result["mined_count"] == 0:
                status_label.set_text("No review data could be mined.")
                btn.set_visibility(True)
                return
            status_label.set_text(
                f"Mined reviews from {result['mined_count']} competitors, "
                f"{len(result['aspects'])} aspects found."
            )
            # Re-fetch stored data and render
            analysis = get_review_analysis(product_id)
            if analysis:
                results_container.clear()
                _render_review_results(results_container, analysis)
        except Exception as exc:
            spinner.set_visibility(False)
            status_label.set_text(f"Error: {exc}")
            btn.set_visibility(True)

    with ui.row().classes("w-full items-center gap-4"):
        btn = ui.button("Mine Reviews", icon="psychology", on_click=on_mine).props("color=accent")
        spinner = ui.spinner("dots", size="lg")
        spinner.set_visibility(False)
        status_label = ui.label("")
        status_label.set_visibility(False)


def _render_review_results(container, analysis: dict):
    """Render review analysis results into the given container."""
    aspects = analysis.get("aggregated_aspects", [])
    synthesis_json = analysis.get("product_synthesis")
    competitors = analysis.get("competitors", [])

    with container:
        # --- Heatmap Chart ---
        if aspects:
            _render_heatmap(aspects[:12])

        # --- AI Synthesis ---
        if synthesis_json:
            try:
                synthesis = json.loads(synthesis_json) if isinstance(synthesis_json, str) else synthesis_json
            except (json.JSONDecodeError, TypeError):
                synthesis = None

            if synthesis:
                _render_synthesis(synthesis)

        # --- Per-Competitor Accordion ---
        if competitors:
            ui.label("Per-Competitor Breakdown").classes("text-h6 font-medium mt-4")
            for comp in competitors:
                with ui.expansion(
                    f"{comp.get('title', 'Unknown')[:60]} ({comp.get('asin', '?')})",
                    icon="storefront",
                ).classes("w-full"):
                    with ui.row().classes("gap-4 mb-2"):
                        if comp.get("rating"):
                            ui.badge(f"Rating: {comp['rating']}", color="amber").props("outline")
                        if comp.get("total_reviews"):
                            ui.badge(f"{comp['total_reviews']} reviews", color="blue").props("outline")
                    comp_aspects = comp.get("aspects", [])
                    if comp_aspects:
                        for asp in comp_aspects:
                            with ui.row().classes("w-full items-start gap-2 py-1"):
                                ui.label(asp.get("title", "")).classes("font-medium text-body2")
                                pos = asp.get("mentions_positive", 0)
                                neg = asp.get("mentions_negative", 0)
                                total = asp.get("mentions_total", 0)
                                ui.badge(f"+{pos}", color="green").props("dense")
                                ui.badge(f"-{neg}", color="red").props("dense")
                                ui.badge(f"={total}", color="grey").props("dense")
                            if asp.get("examples"):
                                for ex in asp["examples"][:2]:
                                    ui.label(f'"{ex}"').classes(
                                        "text-caption text-grey-7 pl-4 italic"
                                    )
                    else:
                        ui.label("No review aspects found.").classes("text-body2 text-grey")


def _render_heatmap(aspects: list):
    """Render an ECharts heatmap of review aspects by sentiment."""
    y_labels = [a["title"] for a in aspects]
    x_labels = ["Positive", "Neutral", "Negative"]

    data = []
    for y_idx, asp in enumerate(aspects):
        pos = asp.get("mentions_positive", 0)
        neg = asp.get("mentions_negative", 0)
        total = asp.get("mentions_total", 0)
        neutral = max(0, total - pos - neg)
        data.append([0, y_idx, pos])
        data.append([1, y_idx, neutral])
        data.append([2, y_idx, neg])

    max_val = max((d[2] for d in data), default=1) or 1

    ui.echart({
        "tooltip": {"position": "top"},
        "grid": {"left": "20%", "right": "10%", "top": "5%", "bottom": "15%"},
        "xAxis": {"type": "category", "data": x_labels, "splitArea": {"show": True}},
        "yAxis": {"type": "category", "data": y_labels, "splitArea": {"show": True}},
        "visualMap": {
            "min": 0,
            "max": int(max_val),
            "calculable": True,
            "orient": "horizontal",
            "left": "center",
            "bottom": "0%",
            "inRange": {
                "color": ["#f5f5f5", "#c8e6c9", "#a5d6a7", "#66bb6a",
                           "#ffcc80", "#ef9a9a", "#e57373", "#ef5350"],
            },
        },
        "series": [{
            "name": "Mentions",
            "type": "heatmap",
            "data": data,
            "label": {"show": True},
            "emphasis": {"itemStyle": {"shadowBlur": 10, "shadowColor": "rgba(0,0,0,0.5)"}},
        }],
    }).classes("w-full").style("height: 300px")


def _render_synthesis(synthesis: dict):
    """Render the AI synthesis section."""
    with ui.card().classes("w-full p-5 mt-4"):
        ui.label("AI Review Synthesis").classes("text-h6 font-medium mb-2")

        # Summary
        if synthesis.get("summary"):
            with ui.card().classes("w-full bg-blue-1 p-3 mb-3"):
                ui.label(synthesis["summary"]).classes("text-body1")

        # Top Pain Points
        pain_points = synthesis.get("top_pain_points", [])
        if pain_points:
            ui.label("Top Pain Points").classes("text-subtitle1 font-medium mb-2")
            for pp in pain_points:
                with ui.card().classes("w-full p-3 mb-2"):
                    with ui.row().classes("items-center gap-2 mb-1"):
                        ui.label(pp.get("aspect", "")).classes("text-subtitle2 font-bold")
                        if pp.get("frequency"):
                            ui.badge(f"{pp['frequency']} mentions", color="orange").props("outline")
                    if pp.get("insight"):
                        ui.label(pp["insight"]).classes("text-body2 mb-1")
                    if pp.get("product_opportunity"):
                        ui.label(pp["product_opportunity"]).classes(
                            "text-body2 text-green-8 font-medium"
                        )

        # Product Recommendations
        recs = synthesis.get("product_recommendations", [])
        if recs:
            ui.label("Product Recommendations").classes("text-subtitle1 font-medium mt-3 mb-2")
            with ui.column().classes("gap-1"):
                for rec in recs:
                    with ui.row().classes("items-start gap-2"):
                        ui.icon("check_circle", size="sm").classes("text-green-7 mt-1")
                        ui.label(rec).classes("text-body2")

        # Competitive Advantages
        advantages = synthesis.get("competitive_advantages", [])
        if advantages:
            ui.label("Competitive Advantages").classes("text-subtitle1 font-medium mt-3 mb-2")
            with ui.row().classes("gap-2 flex-wrap"):
                for adv in advantages:
                    ui.badge(adv, color="teal").props("outline")


# ====================================================================
# PPC Keyword Intelligence
# ====================================================================

def _render_ppc_keywords(product, product_id, comp_data):
    """Render PPC Keyword Intelligence section in Analysis tab."""
    with ui.card().classes("w-full p-5 mt-4"):
        with ui.row().classes("items-center gap-2 mb-3"):
            ui.icon("campaign").classes("text-accent")
            ui.label("PPC Keyword Intelligence").classes("text-subtitle1 font-bold")

        ppc_container = ui.column().classes("w-full gap-3")

        with ui.row().classes("items-center gap-2"):
            ppc_btn = ui.button(
                "Generate Keywords", icon="auto_awesome",
            ).props("outlined color=primary")
            ppc_spinner = ui.spinner("dots", size="lg")
            ppc_spinner.set_visibility(False)

        async def _generate_keywords():
            ppc_btn.disable()
            ppc_spinner.set_visibility(True)
            try:
                from src.services.keyword_intel import generate_ppc_campaign
                result = await asyncio.get_event_loop().run_in_executor(
                    None, generate_ppc_campaign, product_id,
                )
                ppc_container.clear()
                with ppc_container:
                    _render_ppc_content(result, product_id)
            except Exception as exc:
                logger.exception("PPC keyword generation failed")
                ui.notify(f"Keyword generation failed: {exc}", type="negative")
            finally:
                ppc_btn.enable()
                ppc_spinner.set_visibility(False)

        ppc_btn.on_click(_generate_keywords)


def _render_ppc_content(result, product_id):
    """Render the PPC campaign results inside the PPC section."""
    # Campaign Summary
    summary = result.get("summary", "")
    if summary:
        with ui.card().classes("w-full bg-blue-1 p-3"):
            ui.label("Campaign Summary").classes("text-subtitle2 font-bold mb-1")
            ui.label(summary).classes("text-body2")
            total = result.get("total_keywords", 0)
            if total:
                ui.label(f"Total unique keywords: {total}").classes("text-caption text-secondary mt-1")

    # Keyword Frequency Chart
    kf = result.get("keyword_frequency", [])[:15]
    if kf:
        keywords = [k["keyword"] for k in reversed(kf)]
        counts = [k["count"] for k in reversed(kf)]
        with ui.card().classes("w-full p-3"):
            ui.label("Keyword Frequency in Competitor Titles").classes("text-subtitle2 font-bold mb-2")
            ui.echart({
                "tooltip": {"trigger": "axis"},
                "xAxis": {"type": "value"},
                "yAxis": {"type": "category", "data": keywords},
                "series": [{"type": "bar", "data": counts, "itemStyle": {"color": "#A08968"}}],
                "grid": {"left": 150, "right": 20, "bottom": 20, "top": 10},
            }).classes("w-full").style("height: 400px")

    # Auto Campaign Seeds
    auto_rows = [
        {"keyword": k["keyword"], "match": k.get("match_type", "broad"),
         "relevance": k.get("relevance", ""), "rationale": k.get("rationale", "")}
        for k in result.get("auto_seeds", [])
    ]
    if auto_rows:
        auto_columns = [
            {"name": "keyword", "label": "Keyword", "field": "keyword", "align": "left"},
            {"name": "match", "label": "Match Type", "field": "match", "align": "center"},
            {"name": "relevance", "label": "Relevance", "field": "relevance", "align": "center"},
            {"name": "rationale", "label": "Rationale", "field": "rationale", "align": "left"},
        ]
        with ui.card().classes("w-full"):
            ui.label("Auto Campaign Seeds").classes("text-subtitle2 font-bold text-positive")
            ui.table(columns=auto_columns, rows=auto_rows).classes("w-full")

    # Manual Exact Match
    manual_rows = [
        {"keyword": k["keyword"], "match": k.get("match_type", "exact"),
         "relevance": k.get("relevance", ""), "rationale": k.get("rationale", "")}
        for k in result.get("manual_exact", [])
    ]
    if manual_rows:
        manual_columns = [
            {"name": "keyword", "label": "Keyword", "field": "keyword", "align": "left"},
            {"name": "match", "label": "Match Type", "field": "match", "align": "center"},
            {"name": "relevance", "label": "Relevance", "field": "relevance", "align": "center"},
            {"name": "rationale", "label": "Rationale", "field": "rationale", "align": "left"},
        ]
        with ui.card().classes("w-full"):
            ui.label("Manual Exact Match").classes("text-subtitle2 font-bold text-primary")
            ui.table(columns=manual_columns, rows=manual_rows).classes("w-full")

    # Negative Keywords
    neg_rows = [
        {"keyword": k["keyword"], "reason": k.get("reason", "")}
        for k in result.get("negative_keywords", [])
    ]
    if neg_rows:
        neg_columns = [
            {"name": "keyword", "label": "Keyword", "field": "keyword", "align": "left"},
            {"name": "reason", "label": "Reason", "field": "reason", "align": "left"},
        ]
        with ui.card().classes("w-full"):
            ui.label("Negative Keywords").classes("text-subtitle2 font-bold text-negative")
            ui.table(columns=neg_columns, rows=neg_rows).classes("w-full")

    # Export CSV button
    def _export_csv():
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Campaign Type", "Keyword", "Match Type", "Relevance", "Rationale/Reason"])
        for kw in result.get("auto_seeds", []):
            writer.writerow(["Auto", kw["keyword"], kw.get("match_type", "broad"),
                             kw.get("relevance", ""), kw.get("rationale", "")])
        for kw in result.get("manual_exact", []):
            writer.writerow(["Manual", kw["keyword"], kw.get("match_type", "exact"),
                             kw.get("relevance", ""), kw.get("rationale", "")])
        for kw in result.get("negative_keywords", []):
            writer.writerow(["Negative", kw["keyword"], "negative", "", kw.get("reason", "")])
        ui.download(output.getvalue().encode(), f"ppc_keywords_{product_id}.csv")

    ui.button("Export CSV", icon="download", on_click=_export_csv).props("color=accent outline")


# ---------------------------------------------------------------------------
# Seasonal Demand Forecast
# ---------------------------------------------------------------------------

def _render_seasonal_forecast(product, product_id):
    """Render the Best Launch Window card with seasonal demand forecast."""
    with ui.expansion(
        "Best Launch Window", icon="calendar_month",
    ).classes("w-full").props("dense header-class='text-subtitle1 font-bold'"):

        forecast_container = ui.column().classes("w-full gap-2")

        with ui.row().classes("items-center gap-2"):
            forecast_btn = ui.button(
                "Analyze Seasonality", icon="trending_up",
            ).props("outlined color=primary")
            forecast_spinner = ui.spinner("dots", size="lg")
            forecast_spinner.set_visibility(False)

        async def _run_forecast():
            forecast_btn.disable()
            forecast_spinner.set_visibility(True)
            try:
                from src.services.season_forecaster import forecast_demand
                result = await asyncio.get_event_loop().run_in_executor(
                    None, forecast_demand, product_id,
                )
                forecast_container.clear()
                with forecast_container:
                    _render_forecast_content(result)
            except Exception as exc:
                logger.exception("Seasonal forecast failed")
                ui.notify(f"Forecast failed: {exc}", type="negative")
            finally:
                forecast_btn.enable()
                forecast_spinner.set_visibility(False)

        forecast_btn.on_click(_run_forecast)


def _render_forecast_content(result: dict):
    """Render the forecast result inside the container."""

    # 1. Trends availability warning
    if not result["trends_available"]:
        ui.chip(
            "Google Trends unavailable -- using BSR history only",
            icon="warning", color="amber",
        ).props("outline")

    # 2. Recommendation banner
    with ui.card().classes("w-full bg-green-1 q-pa-sm"):
        with ui.row().classes("items-center gap-2 no-wrap"):
            ui.icon("calendar_month").classes("text-green text-h6")
            ui.label(result["launch_recommendation"]).classes(
                "text-body1 font-bold text-green-9"
            )

    # 3. Seasonality strength badge
    strength = result["seasonality_strength"]
    if strength >= 0.5:
        badge_color, badge_label = "green", "Strong Seasonality"
    elif strength >= 0.25:
        badge_color, badge_label = "orange", "Moderate Seasonality"
    else:
        badge_color, badge_label = "grey", "Weak Seasonality"
    ui.badge(f"{badge_label} ({strength:.0%})", color=badge_color).props("outline")

    # 4. 12-Month Demand Forecast chart
    forecast_12m = result.get("forecast_12m", [])
    if forecast_12m:
        ui.label("12-Month Demand Forecast").classes("text-subtitle2 font-medium mt-2")
        months = [f["month"] for f in forecast_12m]
        values = [round(f["predicted_index"], 1) for f in forecast_12m]

        ui.echart({
            "tooltip": {"trigger": "axis"},
            "xAxis": {
                "type": "category",
                "data": months,
                "axisLabel": {"rotate": 45},
            },
            "yAxis": {"type": "value", "name": "Demand Index", "min": 0},
            "series": [{
                "type": "line",
                "data": values,
                "smooth": True,
                "areaStyle": {"opacity": 0.15},
                "lineStyle": {"width": 3},
                "itemStyle": {"color": "#A08968"},
                "markLine": {
                    "data": [{"type": "average", "name": "Avg"}],
                    "lineStyle": {"type": "dashed"},
                },
            }],
            "grid": {"left": 50, "right": 20, "bottom": 60, "top": 30},
        }).classes("w-full").style("height: 300px")

    # 5. Monthly Demand Index table
    mdi = result.get("monthly_demand_index", [])
    if mdi:
        ui.label("Monthly Demand Index").classes("text-subtitle2 font-medium mt-2")
        columns = [
            {"name": "month", "label": "Month", "field": "month", "align": "left"},
            {"name": "index", "label": "Index", "field": "index", "align": "right"},
            {"name": "peak", "label": "Peak", "field": "peak", "align": "center"},
        ]
        rows = [
            {
                "month": e["month"],
                "index": e["index"],
                "peak": "Yes" if e["is_peak"] else "",
            }
            for e in mdi
        ]
        ui.table(columns=columns, rows=rows).classes("w-full").props(
            "dense flat bordered"
        )

    # 6. BSR History mini-chart
    bsr = result.get("bsr_history", [])
    if bsr:
        ui.label("BSR History").classes("text-subtitle2 font-medium mt-2")
        bsr_dates = [b["date"] for b in bsr]
        bsr_vals = [b["avg_bsr"] for b in bsr]

        ui.echart({
            "tooltip": {"trigger": "axis"},
            "xAxis": {
                "type": "category",
                "data": bsr_dates,
                "axisLabel": {"rotate": 45},
            },
            "yAxis": {"type": "value", "name": "Avg BSR", "inverse": True},
            "series": [{
                "type": "line",
                "data": bsr_vals,
                "smooth": True,
                "lineStyle": {"width": 2, "color": "#5470C6"},
                "itemStyle": {"color": "#5470C6"},
            }],
            "grid": {"left": 60, "right": 20, "bottom": 60, "top": 30},
        }).classes("w-full").style("height: 200px")
