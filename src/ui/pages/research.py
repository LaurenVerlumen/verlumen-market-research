"""Research page - run Amazon competition analysis."""
import asyncio
from datetime import datetime

from nicegui import ui, app
from sqlalchemy.orm import joinedload

from config import SERPAPI_KEY, AMAZON_DEPARTMENT_MAP, AMAZON_DEPARTMENT_DEFAULT, SP_API_REFRESH_TOKEN
import logging

from src.models import get_session, Category, Product, SearchSession, AmazonCompetitor
from src.services import AmazonSearchService, AmazonSearchError, CompetitionAnalyzer
from src.services.sp_api_client import SPAPIClient
from src.services.query_optimizer import optimize_query
from src.services.match_scorer import score_matches
from src.ui.components.helpers import avatar_color as _avatar_color, product_image_src as _product_image_src
from src.ui.layout import build_layout

logger = logging.getLogger(__name__)


def research_page():
    """Render the research page."""
    content = build_layout()

    with content:
        ui.label("Amazon Research").classes("text-h5 font-bold")
        ui.label("Select products and run Amazon competition analysis.").classes(
            "text-body2 text-secondary mb-2"
        )

        if not SERPAPI_KEY:
            with ui.card().classes("w-full p-4"):
                ui.icon("warning").classes("text-warning text-4xl")
                ui.label("SerpAPI key not configured").classes("text-subtitle1 font-bold")
                ui.label(
                    "Please configure your SerpAPI key in Settings before running research."
                ).classes("text-body2 text-secondary")
                ui.button(
                    "Go to Settings", icon="settings",
                    on_click=lambda: ui.navigate.to("/settings"),
                ).props("color=warning")
            return

        # Load products with relationships
        session = get_session()
        try:
            products = (
                session.query(Product)
                .options(
                    joinedload(Product.category),
                    joinedload(Product.search_sessions),
                )
                .order_by(Product.category_id, Product.name)
                .all()
            )
            # Materialise data while session open
            product_data = []
            category_names = set()
            for p in products:
                cat_name = p.category.name if p.category else "Uncategorised"
                category_names.add(cat_name)
                sessions_list = list(p.search_sessions)
                last_researched = None
                if sessions_list:
                    last_researched = max(s.created_at for s in sessions_list)
                product_data.append({
                    "id": p.id,
                    "name": p.name,
                    "category": cat_name,
                    "image_src": _product_image_src(p),
                    "avatar_letter": p.name[0].upper() if p.name else "?",
                    "avatar_color": _avatar_color(p.name) if p.name else "#90A4AE",
                    "is_researched": len(sessions_list) > 0,
                    "session_count": len(sessions_list),
                    "last_researched": last_researched,
                })
            category_names = sorted(category_names)
        finally:
            session.close()

        if not product_data:
            ui.label("No products imported yet.").classes("text-body2 text-secondary")
            ui.button(
                "Import Excel", icon="upload_file",
                on_click=lambda: ui.navigate.to("/import"),
            ).props("color=primary")
            return

        # --- State ---
        selected_ids: set[int] = set()  # start with 0 selected
        pages_per_search = {"value": 1}

        # Pre-select products from URL query parameter ?ids=1,2,3
        # Uses app.storage.browser to check, but the canonical approach
        # is to parse from the client URL via JavaScript after page load.
        _valid_ids = {p["id"] for p in product_data}

        async def _preselect_from_url():
            try:
                raw = await ui.run_javascript(
                    'new URLSearchParams(window.location.search).get("ids")'
                )
                if raw:
                    for part in str(raw).split(","):
                        part = part.strip()
                        if part.isdigit():
                            pid = int(part)
                            if pid in _valid_ids:
                                selected_ids.add(pid)
                    if selected_ids:
                        _render_grid()
                        _update_summary()
            except RuntimeError:
                pass

        ui.timer(0.1, _preselect_from_url, once=True)

        # --- Filters ---
        with ui.card().classes("w-full p-4"):
            ui.label("Filter Products").classes("text-subtitle2 font-bold mb-2")
            with ui.row().classes("w-full items-center gap-4 flex-wrap"):
                search_input = ui.input(
                    label="Search by name",
                    placeholder="Type to filter...",
                ).props('clearable outlined dense prepend-inner-icon="search"').classes("w-64")

                cat_filter = ui.select(
                    options=["All"] + category_names,
                    value="All",
                    label="Category",
                ).props("outlined dense").classes("w-48")

                status_filter = ui.select(
                    options=["All", "Unresearched", "Researched"],
                    value="All",
                    label="Research Status",
                ).props("outlined dense").classes("w-48")

        # --- Quick Selection Buttons ---
        with ui.row().classes("w-full items-center gap-2 flex-wrap"):
            select_all_btn = ui.button("Select All", icon="select_all").props(
                "flat dense color=primary size=sm"
            )
            deselect_all_btn = ui.button("Deselect All", icon="deselect").props(
                "flat dense color=grey size=sm"
            )
            select_unresearched_btn = ui.button(
                "Select Unresearched", icon="pending_actions"
            ).props("flat dense color=accent size=sm")

            # Select by category quick button
            cat_quick = ui.select(
                options=[""] + category_names,
                value="",
                label="Select Category",
            ).props("outlined dense").classes("w-48")

        # --- Selection Summary Bar ---
        with ui.card().classes("w-full p-3").style(
            "background: #f5f0eb; border-left: 4px solid #A08968"
        ):
            with ui.row().classes("w-full items-center gap-4"):
                selection_label = ui.label("0 products selected").classes(
                    "text-subtitle2 font-bold"
                )
                credits_label = ui.label("").classes("text-caption text-secondary")
                ui.space()
                pages_select = ui.select(
                    options={1: "1 page", 2: "2 pages", 3: "3 pages"},
                    value=1,
                    label="Pages per search",
                ).props("outlined dense").classes("w-40")

        # --- Product Browser Grid ---
        grid_container = ui.column().classes("w-full gap-0")

        # Checkbox references keyed by product id
        checkboxes: dict[int, ui.checkbox] = {}

        def _get_filtered_products():
            """Return filtered product_data based on current filter state."""
            filtered = list(product_data)
            search_term = (search_input.value or "").strip().lower()
            if search_term:
                filtered = [p for p in filtered if search_term in p["name"].lower()]
            if cat_filter.value != "All":
                filtered = [p for p in filtered if p["category"] == cat_filter.value]
            if status_filter.value == "Unresearched":
                filtered = [p for p in filtered if not p["is_researched"]]
            elif status_filter.value == "Researched":
                filtered = [p for p in filtered if p["is_researched"]]
            return filtered

        def _update_summary():
            count = len(selected_ids)
            selection_label.text = f"{count} product{'s' if count != 1 else ''} selected"
            pps = pages_select.value or 1
            pages_per_search["value"] = pps
            total_searches = count * pps
            credits_label.text = f"Estimated API calls: {total_searches}"

        def _on_checkbox_change(pid: int, checked: bool):
            if checked:
                selected_ids.add(pid)
            else:
                selected_ids.discard(pid)
            _update_summary()

        def _render_grid():
            checkboxes.clear()
            grid_container.clear()
            filtered = _get_filtered_products()

            with grid_container:
                if not filtered:
                    ui.label("No products match your filters.").classes(
                        "text-body2 text-secondary py-4"
                    )
                    return

                with ui.element("div").classes("w-full grid gap-3").style(
                    "grid-template-columns: repeat(auto-fill, minmax(300px, 1fr))"
                ):
                    for p in filtered:
                        pid = p["id"]
                        is_selected = pid in selected_ids

                        with ui.card().classes("p-3").style(
                            f"border: 2px solid {'#A08968' if is_selected else 'transparent'}; "
                            "transition: border-color 0.2s"
                        ):
                            with ui.row().classes("items-start w-full gap-3"):
                                # Checkbox
                                cb = ui.checkbox(
                                    value=is_selected,
                                    on_change=lambda e, _pid=pid: _on_checkbox_change(
                                        _pid, e.value
                                    ),
                                )
                                checkboxes[pid] = cb

                                # Thumbnail / avatar
                                if p["image_src"]:
                                    ui.image(p["image_src"]).classes(
                                        "w-14 h-14 rounded object-cover"
                                    ).style("min-width:56px")
                                else:
                                    ui.avatar(
                                        p["avatar_letter"],
                                        color=p["avatar_color"],
                                        text_color="white",
                                        size="56px",
                                    )

                                # Info
                                with ui.column().classes("flex-1 gap-1"):
                                    ui.label(p["name"]).classes(
                                        "text-subtitle2 font-bold"
                                    ).style("line-height:1.3")
                                    with ui.row().classes("gap-2 items-center flex-wrap"):
                                        ui.badge(
                                            p["category"], color="blue-2"
                                        ).props("outline")
                                        if p["is_researched"]:
                                            ui.badge(
                                                "Researched", color="positive"
                                            )
                                        else:
                                            ui.badge("Pending", color="grey-5")

                                    # Last researched date
                                    if p["last_researched"]:
                                        ui.label(
                                            f"Last: {p['last_researched'].strftime('%Y-%m-%d %H:%M')}"
                                        ).classes("text-caption text-secondary")
                                    elif p["session_count"] == 0:
                                        ui.label("Never researched").classes(
                                            "text-caption text-secondary"
                                        )

        def _select_all():
            filtered = _get_filtered_products()
            for p in filtered:
                selected_ids.add(p["id"])
            _render_grid()
            _update_summary()

        def _deselect_all():
            selected_ids.clear()
            _render_grid()
            _update_summary()

        def _select_unresearched():
            for p in product_data:
                if not p["is_researched"]:
                    selected_ids.add(p["id"])
            _render_grid()
            _update_summary()

        def _select_category(e):
            cat_name = cat_quick.value
            if not cat_name:
                return
            for p in product_data:
                if p["category"] == cat_name:
                    selected_ids.add(p["id"])
            cat_quick.value = ""
            _render_grid()
            _update_summary()

        select_all_btn.on_click(lambda: _select_all())
        deselect_all_btn.on_click(lambda: _deselect_all())
        select_unresearched_btn.on_click(lambda: _select_unresearched())
        cat_quick.on_value_change(_select_category)

        # Wire filters to re-render
        search_input.on("input", lambda _: _render_grid())
        cat_filter.on_value_change(lambda _: _render_grid())
        status_filter.on_value_change(lambda _: _render_grid())
        pages_select.on_value_change(lambda _: _update_summary())

        # Initial render
        _render_grid()
        _update_summary()

        # --- Run button row (placed BEFORE progress area) ---
        with ui.row().classes("gap-3 mt-2 items-center"):
            run_btn = ui.button(
                "Run Research for Selected", icon="search",
            ).props("color=positive")

            remaining_label = ui.label("").classes("text-caption text-secondary")

            async def check_remaining():
                service = AmazonSearchService(api_key=SERPAPI_KEY)
                remaining = await asyncio.get_event_loop().run_in_executor(
                    None, service.get_remaining_searches,
                )
                if remaining is not None:
                    remaining_label.text = f"SerpAPI searches remaining: {remaining}"
                else:
                    remaining_label.text = "Could not check remaining searches."

            ui.button(
                "Check API Credits", icon="info", on_click=check_remaining,
            ).props("flat color=grey")

        # --- Progress area (hidden until research starts) ---
        progress_card = ui.card().classes("w-full p-4 mt-4")
        progress_card.visible = False

        with progress_card:
            ui.label("Research Progress").classes("text-subtitle2 font-bold mb-2")
            progress_container = ui.column().classes("w-full")
            log_area = ui.log(max_lines=100).classes("w-full h-64")

        async def run_research():
            """Run Amazon search for selected products."""
            ids = list(selected_ids)
            if not ids:
                ui.notify("Please select at least one product.", type="warning")
                return

            pps = pages_per_search["value"]
            search_service = AmazonSearchService(api_key=SERPAPI_KEY)
            analyzer = CompetitionAnalyzer()

            try:
                # Show progress area and give immediate feedback
                progress_card.visible = True
                run_btn.disable()
                log_area.clear()

                progress_container.clear()
                with progress_container:
                    progress = ui.linear_progress(value=0, show_value=False).classes(
                        "w-full"
                    )
                    with ui.row().classes("items-center gap-3 mt-1"):
                        current_thumb = ui.element("div").classes("w-10 h-10")
                        status_label = ui.label(
                            f"Starting research for {len(ids)} products..."
                        ).classes("text-body2 text-secondary")

                log_area.push(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"Starting research for {len(ids)} product(s), "
                    f"{pps} page(s) per search..."
                )

                total = len(ids)
                completed = 0
                errors = 0
                total_competitors_found = 0
                cache_hits = 0

                results = {}
                for pid in ids:
                    db = get_session()
                    try:
                        product = (
                            db.query(Product)
                            .options(joinedload(Product.category))
                            .filter(Product.id == pid)
                            .first()
                        )
                        if not product:
                            continue

                        query = product.amazon_search_query or optimize_query(product.name) or product.name

                        # Auto-detect Amazon department from category
                        dept = AMAZON_DEPARTMENT_DEFAULT
                        if product.category:
                            cat_lower = product.category.name.lower()
                            dept = AMAZON_DEPARTMENT_MAP.get(cat_lower, AMAZON_DEPARTMENT_DEFAULT)

                        # Update current product display
                        current_thumb.clear()
                        with current_thumb:
                            img_src = _product_image_src(product)
                            if img_src:
                                ui.image(img_src).classes(
                                    "w-10 h-10 rounded object-cover"
                                )
                            else:
                                letter = product.name[0].upper() if product.name else "?"
                                ui.avatar(
                                    letter,
                                    color=_avatar_color(product.name),
                                    text_color="white",
                                    size="40px",
                                )

                        status_label.text = f"Searching ({completed + 1}/{total}): {product.name}"
                        dept_label = f" [dept: {dept}]" if dept else ""
                        log_area.push(
                            f"[{datetime.now().strftime('%H:%M:%S')}] "
                            f"Searching ({completed + 1}/{total}): {product.name}{dept_label}"
                        )

                        try:
                            # Use the multi-page search with built-in caching, dedup, and department filter
                            results = search_service.search_products(
                                query, max_pages=pps, amazon_department=dept,
                            )
                            all_competitors = results["competitors"]
                            analysis = analyzer.analyze(all_competitors)

                            # Compute match scores
                            scored = score_matches(product.name, [dict(c) for c in all_competitors])
                            score_by_asin: dict[str, float | None] = {}
                            for s in scored:
                                a = s.get("asin")
                                if a:
                                    score_by_asin[a] = s.get("match_score")

                            # SP-API brand enrichment (optional)
                            brand_data: dict[str, dict] = {}
                            if SP_API_REFRESH_TOKEN:
                                try:
                                    status_label.text = f"Enriching brand data ({completed + 1}/{total}): {product.name}"
                                    sp_client = SPAPIClient()
                                    unique_asins = list({c.get("asin") for c in all_competitors if c.get("asin")})
                                    brand_data = await asyncio.get_event_loop().run_in_executor(
                                        None, sp_client.enrich_asins, unique_asins,
                                    )
                                    log_area.push(f"  -> Brand data enriched for {len(brand_data)} ASINs")
                                except Exception as exc:
                                    logger.warning("SP-API enrichment failed: %s", exc)
                                    log_area.push(f"  -> SP-API enrichment skipped: {exc}")

                            if results.get("cache_hit"):
                                cache_hits += 1
                                log_area.push("  -> (cached result)")

                            comp_count = len(all_competitors)
                            total_competitors_found += comp_count
                            pages_info = f" ({results.get('pages_fetched', 1)} pages)" if pps > 1 else ""

                            search_session = SearchSession(
                                product_id=product.id,
                                search_query=query,
                                amazon_domain="amazon.com",
                                total_results=results.get("total_results_across_pages", comp_count),
                                organic_results=results["total_organic"],
                                sponsored_results=results["total_sponsored"],
                                avg_price=analysis["price_mean"],
                                avg_rating=analysis["avg_rating"],
                                avg_reviews=analysis["avg_reviews"],
                            )
                            db.add(search_session)
                            db.flush()

                            seen_asins_in_session: set[str] = set()
                            for comp in all_competitors:
                                asin = comp.get("asin", "")
                                # Skip duplicates within the same session
                                if asin and asin in seen_asins_in_session:
                                    continue
                                if asin:
                                    exists = (
                                        db.query(AmazonCompetitor.id)
                                        .filter(
                                            AmazonCompetitor.product_id == product.id,
                                            AmazonCompetitor.asin == asin,
                                            AmazonCompetitor.search_session_id == search_session.id,
                                        )
                                        .first()
                                    )
                                    if exists:
                                        continue
                                    seen_asins_in_session.add(asin)
                                amazon_comp = AmazonCompetitor(
                                    product_id=product.id,
                                    search_session_id=search_session.id,
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

                            # Auto-update product status to "researched"
                            if product.status == "imported":
                                product.status = "researched"

                            db.commit()

                            log_area.push(
                                f"  -> Found {comp_count} competitors{pages_info}. "
                                f"Opportunity: {analysis['opportunity_score']:.0f}/100, "
                                f"Competition: {analysis['competition_score']:.0f}/100"
                            )

                        except (AmazonSearchError, Exception) as e:
                            errors += 1
                            logger.error("Research failed for product %d: %s", pid, e)
                            log_area.push(f"  -> ERROR: {e}")
                            db.rollback()

                    finally:
                        db.close()

                    completed += 1
                    progress.value = completed / total

                    # Short sleep between products (cache hits don't need long waits)
                    if not results.get("cache_hit"):
                        await asyncio.sleep(0.5)

                # --- Research summary ---
                successful = completed - errors
                avg_comps = total_competitors_found / successful if successful > 0 else 0

                summary_text = (
                    f"Research complete! {successful}/{total} products analyzed. "
                    f"Total competitors: {total_competitors_found}, "
                    f"avg per product: {avg_comps:.0f}"
                )
                if cache_hits:
                    summary_text += f", cache hits: {cache_hits}"
                if errors:
                    summary_text += f" ({errors} errors)"

                status_label.text = summary_text

                log_area.push(
                    f"\n[{datetime.now().strftime('%H:%M:%S')}] {summary_text}"
                )
                ui.notify(
                    f"Research complete! {successful}/{total} products analyzed.",
                    type="positive",
                )
            except RuntimeError:
                return
            finally:
                try:
                    run_btn.enable()
                except RuntimeError:
                    pass

        run_btn.on_click(run_research)
