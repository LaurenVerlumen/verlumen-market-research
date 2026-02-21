"""Product detail page - Alibaba info + Amazon competition analysis."""
import asyncio
import json
import logging
import statistics as _stats
from datetime import datetime

from nicegui import ui

from config import SERPAPI_KEY, SP_API_REFRESH_TOKEN, AMAZON_MARKETPLACES
from src.models import get_session, Product, AmazonCompetitor, SearchSession
from src.models.category import Category
from config import AMAZON_DEPARTMENT_MAP, AMAZON_DEPARTMENT_DEFAULT
from src.services import (
    ImageFetcher, download_image, save_uploaded_image,
    AmazonSearchService, AmazonSearchError, CompetitionAnalyzer,
)
from src.services.sp_api_client import SPAPIClient
from src.services.xray_importer import XrayImporter
from src.services.match_scorer import score_matches
from src.services.utils import parse_bought
from src.ui.components.helpers import (
    avatar_color as _avatar_color, product_image_src as _product_image_src,
    format_price as _format_price, STATUS_COLORS as _STATUS_COLORS, STATUS_LABELS as _STATUS_LABELS,
)
from src.services.viability_scorer import calculate_vvs
from src.services.trend_tracker import compute_trends
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

            # --- Eagerly resolve department while session is still open ---
            _product_dept = AMAZON_DEPARTMENT_DEFAULT
            if product.category:
                _cat_lower = product.category.name.lower()
                _product_dept = AMAZON_DEPARTMENT_MAP.get(_cat_lower, AMAZON_DEPARTMENT_DEFAULT)
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
                analysis_tab = ui.tab("Analysis", icon="analytics")
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
                        _product_dept, _product_name,
                    )

                # ============================================================
                # ANALYSIS TAB
                # ============================================================
                with ui.tab_panel(analysis_tab):
                    _render_analysis_tab(product, latest_session)

                # ============================================================
                # HISTORY TAB
                # ============================================================
                with ui.tab_panel(history_tab):
                    _render_history_tab(all_sessions, product_id)

        finally:
            session.close()


# ====================================================================
# Tab renderers
# ====================================================================

def _render_overview_tab(product, product_id, session,
                         _has_query_optimizer, _suggest_queries_fn):
    """Render the Overview tab: product info card + decision log."""

    # Product info card with image
    with ui.card().classes("w-full p-4"):
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
                                    "clickable outline color=primary"
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

    # --- Decision Log ---
    _decision_log_entries = json.loads(product.decision_log or "[]")

    with ui.card().classes("w-full p-4"):
        with ui.row().classes("items-center gap-2 w-full"):
            ui.icon("history").classes("text-primary text-h6")
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


def _render_competitors_tab(product, product_id, session, latest_session,
                            _product_dept, _product_name):
    """Render the Competitors tab: research controls, stats, competitor table."""

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
        with ui.card().classes("w-full p-4"):
            ui.label("Amazon Competition Analysis").classes("text-subtitle1 font-bold mb-2")
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
    if not latest_session:
        with ui.card().classes("w-full p-4"):
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
                }
                for c in comps
            ]
            _render_brand_landscape(comp_data)

        # --- Profit Analysis card ---
        _render_profit_analysis(product, comps if comps else [])

        # --- AI Insights card ---
        _render_ai_insights(product, comps if comps else [])
    finally:
        db.close()


def _render_history_tab(all_sessions, product_id):
    """Render the History tab: timeline chart + session list."""
    if not all_sessions:
        with ui.card().classes("w-full p-4"):
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

        with ui.card().classes("w-full p-4 mb-4"):
            ui.label("Trend Over Time").classes("text-subtitle1 font-bold mb-2")
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

        with ui.card().classes("w-full p-4 mb-2" + (" border-l-4" if is_latest else "")).style(
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
                }
                for dim_key in ("demand", "competition", "profitability", "market_quality", "differentiation"):
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

    with ui.card().classes("w-full p-4 mt-4"):
        with ui.row().classes("items-center gap-2 mb-3"):
            ui.icon("business").classes("text-primary")
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


def _render_profit_analysis(product, competitors: list):
    """Render the Profit Analysis card if alibaba prices are set."""
    if product.alibaba_price_min is None:
        # Show gentle prompt for entering Alibaba cost
        with ui.card().classes("w-full p-4 mt-4").style(
            "border: 1px dashed #A08968; background: #faf8f5"
        ):
            with ui.row().classes("items-center gap-3"):
                ui.icon("info_outline").classes("text-accent text-2xl")
                with ui.column().classes("flex-1 gap-1"):
                    ui.label("Enter your Alibaba cost to unlock profit analysis").classes(
                        "text-subtitle2 font-medium"
                    )
                    ui.label(
                        "Set the Alibaba price above to see profit analysis and VVS profitability score."
                    ).classes("text-caption text-secondary")
                with ui.row().classes("items-end gap-2"):
                    _cost_input = ui.number(
                        label="Alibaba Cost ($)", format="%.2f",
                        min=0.01, step=0.01,
                    ).props("outlined dense").classes("w-32")

                    def _save_cost():
                        val = _cost_input.value
                        if val is not None and val > 0:
                            db = get_session()
                            try:
                                p = db.query(Product).filter(Product.id == product.id).first()
                                if p:
                                    p.alibaba_price_min = float(val)
                                    db.commit()
                                    ui.notify("Alibaba cost saved! Refreshing...", type="positive")
                                    ui.navigate.to(f"/products/{product.id}")
                            finally:
                                db.close()
                        else:
                            ui.notify("Please enter a valid cost.", type="warning")

                    ui.button("Save", icon="save", on_click=_save_cost).props(
                        "color=accent size=sm"
                    )
        return

    try:
        from src.services.profit_calculator import calculate_profit
    except ImportError:
        return

    if not competitors:
        return

    comp_data = []
    for c in competitors:
        if isinstance(c, dict):
            comp_data.append(c)
        else:
            try:
                comp_data.append({
                    "price": c.price,
                    "bought_last_month": c.bought_last_month,
                })
            except Exception:
                continue

    try:
        profit = calculate_profit(
            alibaba_price_min=product.alibaba_price_min,
            alibaba_price_max=product.alibaba_price_max or product.alibaba_price_min,
            amazon_competitors=comp_data,
        )
    except Exception:
        return

    strategies = profit.get("strategies") or {}
    if not strategies:
        return

    with ui.card().classes("w-full p-4 mt-4"):
        with ui.row().classes("items-center gap-2 mb-3"):
            ui.icon("account_balance").classes("text-primary")
            ui.label("Profit Analysis").classes("text-subtitle1 font-bold")

        # Landed cost
        ui.label(
            f"Landed Cost: ${profit.get('landed_cost', 0):.2f}/unit"
        ).classes("text-body2 text-secondary mb-2")

        # Strategy cards
        with ui.row().classes("gap-4 flex-wrap mb-4"):
            strategy_labels = {
                "budget": ("Budget", "#4DB6AC"),
                "competitive": ("Competitive", "#A08968"),
                "premium": ("Premium", "#9575CD"),
            }
            for key in ("budget", "competitive", "premium"):
                s = strategies.get(key)
                if not s:
                    continue
                label, color = strategy_labels[key]
                be = profit.get("break_even_units", {}).get(key, 0)
                monthly = profit.get("monthly_profit_estimate", {}).get(key, {})

                with ui.card().classes("p-3").style(
                    f"min-width:200px; border-left: 4px solid {color}"
                ):
                    ui.label(label).classes("text-caption font-bold text-uppercase")
                    ui.label(
                        f"${s['selling_price']:.2f}"
                    ).classes("text-h6 font-bold").style(f"color: {color}")

                    margin = s.get("profit_margin_pct", 0)
                    margin_color = (
                        "#006100" if margin > 30
                        else "#9C5700" if margin >= 15
                        else "#9C0006"
                    )

                    with ui.column().classes("gap-1 mt-2"):
                        ui.label(
                            f"Profit/unit: ${s['net_profit']:.2f}"
                        ).classes("text-caption")
                        ui.label(
                            f"Margin: {margin:.1f}%"
                        ).classes("text-caption font-bold").style(
                            f"color: {margin_color}"
                        )
                        ui.label(
                            f"ROI: {s.get('roi_pct', 0):.1f}%"
                        ).classes("text-caption")
                        if be > 0:
                            ui.label(
                                f"Break-even: {be} units"
                            ).classes("text-caption text-secondary")
                        est_monthly = monthly.get("monthly_profit", 0)
                        if est_monthly > 0:
                            ui.label(
                                f"Est. monthly: ${est_monthly:,.0f}"
                            ).classes("text-caption text-secondary")


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

    with ui.card().classes("w-full p-4 mt-4"):
        with ui.row().classes("items-center gap-2 mb-3"):
            ui.icon("auto_awesome").classes("text-primary")
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
