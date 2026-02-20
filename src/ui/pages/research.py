"""Research page - run Amazon competition analysis."""
import asyncio
from datetime import datetime

from nicegui import ui
from sqlalchemy.orm import joinedload

from config import SERPAPI_KEY
from src.models import get_session, Product, SearchSession, AmazonCompetitor
from src.services import AmazonSearchService, AmazonSearchError, CompetitionAnalyzer
from src.ui.layout import build_layout


def research_page():
    """Render the research page."""
    content = build_layout()

    with content:
        ui.label("Run Amazon Research").classes("text-h5 font-bold")
        ui.label("Search Amazon for competing products.").classes("text-body2 text-secondary mb-2")

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

        # Load products (eagerly load category to avoid DetachedInstanceError)
        session = get_session()
        try:
            products = (
                session.query(Product)
                .options(joinedload(Product.category))
                .order_by(Product.category_id, Product.name)
                .all()
            )
            # Build options while session is still open
            product_options = {
                p.id: f"{p.name} ({p.category.name if p.category else 'N/A'})"
                for p in products
            }
        finally:
            session.close()

        if not product_options:
            ui.label("No products imported yet.").classes("text-body2 text-secondary")
            ui.button(
                "Import Excel", icon="upload_file",
                on_click=lambda: ui.navigate.to("/import"),
            ).props("color=primary")
            return

        # Product selection
        ui.label("Select products to research:").classes("text-subtitle2 mb-1")
        selected_ids = ui.select(
            options=product_options,
            multiple=True,
            label="Products",
            value=list(product_options.keys()),
        ).classes("w-full mb-4").props("use-chips")

        # Progress area
        progress_container = ui.column().classes("w-full")
        log_area = ui.log(max_lines=50).classes("w-full h-64 mt-4")

        async def run_research():
            """Run Amazon search for selected products."""
            ids = selected_ids.value
            if not ids:
                ui.notify("Please select at least one product.", type="warning")
                return

            search_service = AmazonSearchService(api_key=SERPAPI_KEY)
            analyzer = CompetitionAnalyzer()

            progress_container.clear()
            with progress_container:
                progress = ui.linear_progress(value=0, show_value=False).classes("w-full")
                status_label = ui.label("Starting research...").classes("text-body2 text-secondary")

            total = len(ids)
            completed = 0
            errors = 0

            for pid in ids:
                session = get_session()
                try:
                    product = session.query(Product).filter(Product.id == pid).first()
                    if not product:
                        continue

                    query = product.amazon_search_query or product.name
                    status_label.text = f"Searching Amazon for: {query}"
                    log_area.push(f"[{datetime.now().strftime('%H:%M:%S')}] Searching: {query}")

                    try:
                        results = search_service.search_products(query)
                        analysis = analyzer.analyze(results["competitors"])

                        search_session = SearchSession(
                            product_id=product.id,
                            search_query=query,
                            amazon_domain="amazon.com",
                            total_results=results["total_organic"] + results["total_sponsored"],
                            organic_results=results["total_organic"],
                            sponsored_results=results["total_sponsored"],
                            avg_price=analysis["price_mean"],
                            avg_rating=analysis["avg_rating"],
                            avg_reviews=analysis["avg_reviews"],
                        )
                        session.add(search_session)
                        session.flush()

                        for comp in results["competitors"]:
                            amazon_comp = AmazonCompetitor(
                                product_id=product.id,
                                search_session_id=search_session.id,
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
                            session.add(amazon_comp)

                        session.commit()

                        log_area.push(
                            f"  -> Found {results['total_organic']} organic results. "
                            f"Opportunity: {analysis['opportunity_score']:.0f}/100, "
                            f"Competition: {analysis['competition_score']:.0f}/100"
                        )

                    except AmazonSearchError as e:
                        errors += 1
                        log_area.push(f"  -> ERROR: {e}")
                        session.rollback()

                finally:
                    session.close()

                completed += 1
                progress.value = completed / total
                await asyncio.sleep(1.5)

            status_label.text = f"Research complete! {completed - errors}/{total} products analyzed."
            if errors:
                status_label.text += f" ({errors} errors)"

            log_area.push(
                f"\n[{datetime.now().strftime('%H:%M:%S')}] Done! "
                f"{completed - errors} successful, {errors} errors."
            )
            ui.notify(
                f"Research complete! {completed - errors}/{total} products analyzed.",
                type="positive",
            )

        with ui.row().classes("gap-3 mt-2"):
            ui.button(
                "Run Research for Selected", icon="search", on_click=run_research,
            ).props("color=positive")

            remaining_label = ui.label("").classes("text-caption text-secondary self-center")

            async def check_remaining():
                service = AmazonSearchService(api_key=SERPAPI_KEY)
                remaining = service.get_remaining_searches()
                if remaining is not None:
                    remaining_label.text = f"SerpAPI searches remaining: {remaining}"
                else:
                    remaining_label.text = "Could not check remaining searches."

            ui.button(
                "Check API Credits", icon="info", on_click=check_remaining,
            ).props("flat color=grey")
