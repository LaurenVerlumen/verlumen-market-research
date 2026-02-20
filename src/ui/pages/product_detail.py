"""Product detail page - Alibaba info + Amazon competition analysis."""
import asyncio
import statistics as _stats
from datetime import datetime

from nicegui import ui

from config import SERPAPI_KEY
from src.models import get_session, Product, AmazonCompetitor, SearchSession
from src.models.category import Category
from config import AMAZON_DEPARTMENT_MAP, AMAZON_DEPARTMENT_DEFAULT
from src.services import (
    ImageFetcher, download_image, save_uploaded_image,
    AmazonSearchService, AmazonSearchError, CompetitionAnalyzer,
)
from src.services.match_scorer import score_matches
from src.ui.components.helpers import avatar_color as _avatar_color, product_image_src as _product_image_src, format_price as _format_price
from src.services.viability_scorer import calculate_vvs
from src.ui.layout import build_layout
from src.ui.components.stats_card import stats_card
from src.ui.components.competitor_table import competitor_table


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
                            file_content = e.content.read()
                            original_name = e.name
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

                            # --- Feature 1: Editable Amazon Search Query ---
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

                                # --- Feature 5: Query Optimizer button ---
                                try:
                                    from src.services.query_optimizer import suggest_queries as _suggest_queries_fn
                                    _has_query_optimizer = True
                                except ImportError:
                                    _has_query_optimizer = False

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

                        # --- Feature 2: Notes textarea ---
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

            # --- Feature 3: Re-research button helper ---
            def _get_department_for_product(prod):
                """Resolve Amazon department from product's category."""
                if prod.category:
                    cat_lower = prod.category.name.lower()
                    if cat_lower in AMAZON_DEPARTMENT_MAP:
                        return AMAZON_DEPARTMENT_MAP[cat_lower]
                return AMAZON_DEPARTMENT_DEFAULT

            async def _rerun_research(pid=product.id):
                """Run Amazon search + analysis for this single product."""
                if not SERPAPI_KEY:
                    ui.notify("SERPAPI_KEY not configured.", type="negative")
                    return

                rerun_btn.disable()
                rerun_status.text = "Searching Amazon..."

                search_service = AmazonSearchService(api_key=SERPAPI_KEY)
                analyzer = CompetitionAnalyzer()

                query = search_query_input.value.strip() or product.name
                dept = _get_department_for_product(product)

                try:
                    results = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: search_service.search_products(
                            query, amazon_department=dept,
                        ),
                    )
                    analysis = analyzer.analyze(results["competitors"])

                    # Compute match scores
                    scored = score_matches(product.name, [dict(c) for c in results["competitors"]])

                    db = get_session()
                    try:
                        new_session = SearchSession(
                            product_id=pid,
                            search_query=query,
                            amazon_domain="amazon.com",
                            total_results=results.get("total_results_across_pages", len(results["competitors"])),
                            organic_results=results["total_organic"],
                            sponsored_results=results["total_sponsored"],
                            avg_price=analysis["price_mean"],
                            avg_rating=analysis["avg_rating"],
                            avg_reviews=analysis["avg_reviews"],
                        )
                        db.add(new_session)
                        db.flush()

                        seen_asins: set[str] = set()
                        # Build score lookup
                        score_by_asin = {}
                        for s in scored:
                            a = s.get("asin")
                            if a:
                                score_by_asin[a] = s.get("match_score")

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
                            )
                            db.add(amazon_comp)

                        # Auto-update product status to "researched"
                        p_obj = db.query(Product).filter(Product.id == pid).first()
                        if p_obj and p_obj.status == "imported":
                            p_obj.status = "researched"

                        db.commit()
                    finally:
                        db.close()

                    dept_label = f" (dept: {dept})" if dept else ""
                    ui.notify(
                        f"Research complete! Found {len(results['competitors'])} competitors{dept_label}.",
                        type="positive",
                    )
                    ui.navigate.to(f"/products/{pid}")

                except AmazonSearchError as exc:
                    rerun_status.text = f"Error: {exc}"
                    rerun_btn.enable()
                    ui.notify(f"Research failed: {exc}", type="negative")

            # Amazon Competition Analysis
            latest_session = (
                session.query(SearchSession)
                .filter(SearchSession.product_id == product.id)
                .order_by(SearchSession.created_at.desc())
                .first()
            )

            if not latest_session:
                with ui.card().classes("w-full p-4"):
                    ui.label("Amazon Competition Analysis").classes("text-subtitle1 font-bold mb-2")
                    ui.label(
                        "No research data yet. Run Amazon Research to see competition analysis."
                    ).classes("text-body2 text-secondary")
                    with ui.row().classes("gap-2"):
                        ui.button(
                            "Run Research", icon="search",
                            on_click=lambda: ui.navigate.to("/research"),
                        ).props("color=positive")
                        rerun_btn = ui.button(
                            "Run for this product", icon="refresh",
                            on_click=_rerun_research,
                        ).props("color=primary outline")
                        rerun_status = ui.label("").classes(
                            "text-caption text-secondary self-center"
                        )
                return

            # Metrics header with re-research button
            with ui.row().classes("items-center gap-4 w-full"):
                ui.label("Amazon Competition Analysis").classes("text-subtitle1 font-bold")
                rerun_btn = ui.button(
                    "Re-run Research", icon="refresh",
                    on_click=_rerun_research,
                ).props("flat dense color=primary size=sm")
                rerun_status = ui.label("").classes(
                    "text-caption text-secondary"
                )

            ui.label(
                f"Last researched: "
                f"{latest_session.created_at.strftime('%Y-%m-%d %H:%M') if latest_session.created_at else 'N/A'}"
            ).classes("text-caption text-secondary mb-2")

            session_id = latest_session.id
            _saved_pagination = [None]  # mutable container to preserve pagination across refreshes

            @ui.refreshable
            def _competition_section():
                """Render stats + competitor table + profit/AI cards (refreshable on delete)."""
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

                    with ui.row().classes("gap-4 flex-wrap"):
                        stats_card("Competitors", str(n_comps), "groups", "primary")
                        stats_card(
                            "Avg Price",
                            f"${avg_price:.2f}" if avg_price else "N/A",
                            "attach_money", "positive",
                        )
                        stats_card(
                            "Avg Rating",
                            f"{avg_rating:.1f}" if avg_rating else "N/A",
                            "star", "accent",
                        )
                        stats_card(
                            "Avg Reviews",
                            str(avg_reviews),
                            "reviews", "secondary",
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

                    if comps:
                        comp_data = [
                            {
                                "position": c.position,
                                "title": c.title,
                                "asin": c.asin,
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
                            pagination_state=_saved_pagination[0],
                            on_pagination_change=lambda p: _saved_pagination.__setitem__(0, p),
                        )

                    # --- Profit Analysis card ---
                    _render_profit_analysis(product, comps if comps else [])

                    # --- Feature 4: AI Insights card ---
                    _render_ai_insights(product, comps if comps else [])
                finally:
                    db.close()

            _competition_section()

        finally:
            session.close()


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


