"""Product detail page - Alibaba info + Amazon competition analysis."""
import asyncio
from datetime import datetime

from nicegui import ui

from config import SERPAPI_KEY
from src.models import get_session, Product, AmazonCompetitor, SearchSession
from src.services import (
    ImageFetcher, download_image, save_uploaded_image,
    AmazonSearchService, AmazonSearchError, CompetitionAnalyzer,
)
from src.ui.layout import build_layout
from src.ui.components.stats_card import stats_card
from src.ui.components.competitor_table import competitor_table


# Predefined palette for letter-avatar backgrounds
_AVATAR_COLORS = [
    "#E57373", "#F06292", "#BA68C8", "#9575CD", "#7986CB",
    "#64B5F6", "#4FC3F7", "#4DD0E1", "#4DB6AC", "#81C784",
    "#AED581", "#DCE775", "#FFD54F", "#FFB74D", "#FF8A65",
    "#A1887F", "#90A4AE",
]


def _avatar_color(name: str) -> str:
    idx = ord(name[0].upper()) % len(_AVATAR_COLORS) if name else 0
    return _AVATAR_COLORS[idx]


def _product_image_src(product) -> str | None:
    """Return the best image source URL for a product (local preferred)."""
    if product.local_image_path:
        return f"/images/{product.local_image_path}"
    if product.alibaba_image_url:
        return product.alibaba_image_url
    return None


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

            # Header with back button, product name, and delete
            with ui.row().classes("items-center gap-2 w-full"):
                ui.button(
                    icon="arrow_back", on_click=lambda: ui.navigate.to("/products"),
                ).props("flat round")
                ui.label(product.name).classes("text-h5 font-bold flex-1")

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
                            _info_row(
                                "Category",
                                product.category.name if product.category else "N/A",
                            )
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

                try:
                    results = await asyncio.get_event_loop().run_in_executor(
                        None, search_service.search_products, query,
                    )
                    analysis = analyzer.analyze(results["competitors"])

                    db = get_session()
                    try:
                        new_session = SearchSession(
                            product_id=pid,
                            search_query=query,
                            amazon_domain="amazon.com",
                            total_results=results["total_organic"] + results["total_sponsored"],
                            organic_results=results["total_organic"],
                            sponsored_results=results["total_sponsored"],
                            avg_price=analysis["price_mean"],
                            avg_rating=analysis["avg_rating"],
                            avg_reviews=analysis["avg_reviews"],
                        )
                        db.add(new_session)
                        db.flush()

                        for comp in results["competitors"]:
                            amazon_comp = AmazonCompetitor(
                                product_id=pid,
                                search_session_id=new_session.id,
                                asin=comp.get("asin", ""),
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
                            )
                            db.add(amazon_comp)

                        db.commit()
                    finally:
                        db.close()

                    ui.notify(
                        f"Research complete! Found {results['total_organic']} organic results.",
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

            with ui.row().classes("gap-4 flex-wrap"):
                stats_card("Competitors", str(latest_session.organic_results or 0), "groups", "primary")
                stats_card(
                    "Avg Price",
                    f"${latest_session.avg_price:.2f}" if latest_session.avg_price else "N/A",
                    "attach_money", "positive",
                )
                stats_card(
                    "Avg Rating",
                    f"{latest_session.avg_rating:.1f}" if latest_session.avg_rating else "N/A",
                    "star", "accent",
                )
                stats_card(
                    "Avg Reviews",
                    str(latest_session.avg_reviews or 0),
                    "reviews", "secondary",
                )

            # Competitors table
            competitors = (
                session.query(AmazonCompetitor)
                .filter(AmazonCompetitor.search_session_id == latest_session.id)
                .order_by(AmazonCompetitor.position)
                .all()
            )

            if competitors:
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
                    }
                    for c in competitors
                ]
                competitor_table(comp_data)

            # --- Feature 4: AI Insights card ---
            _render_ai_insights(product, competitors if competitors else [])

        finally:
            session.close()


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
        if hasattr(c, "asin"):
            comp_data.append({
                "asin": c.asin, "title": c.title, "price": c.price,
                "rating": c.rating, "review_count": c.review_count,
                "bought_last_month": c.bought_last_month,
                "badge": c.badge, "is_prime": c.is_prime,
                "is_sponsored": c.is_sponsored,
            })
        elif isinstance(c, dict):
            comp_data = competitors
            break

    try:
        match_results = score_matches(product.name, comp_data)
        pricing = recommend_pricing(
            alibaba_min=product.alibaba_price_min,
            alibaba_max=product.alibaba_price_max,
            competitors=comp_data,
        )
        demand = estimate_demand(comp_data)
    except Exception:
        return  # Silently skip if ML fails

    with ui.card().classes("w-full p-4 mt-4"):
        with ui.row().classes("items-center gap-2 mb-3"):
            ui.icon("auto_awesome").classes("text-primary")
            ui.label("AI Insights").classes("text-subtitle1 font-bold")

        # Price strategy cards
        if pricing and pricing.get("strategies"):
            ui.label("Price Recommendations").classes("text-subtitle2 font-medium mb-2")
            with ui.row().classes("gap-4 flex-wrap mb-4"):
                for strategy in pricing["strategies"]:
                    with ui.card().classes("p-3").style("min-width:200px"):
                        ui.label(strategy.get("name", "Strategy")).classes(
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


def _format_price(pmin, pmax) -> str:
    if pmin is not None and pmax is not None:
        return f"${pmin:.2f} - ${pmax:.2f}"
    if pmin is not None:
        return f"${pmin:.2f}"
    if pmax is not None:
        return f"${pmax:.2f}"
    return "N/A"
