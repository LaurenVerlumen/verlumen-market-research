"""Product detail page - Alibaba info + Amazon competition analysis."""
from nicegui import ui

from src.models import get_session, Product, AmazonCompetitor, SearchSession
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

            # Header
            with ui.row().classes("items-center gap-2"):
                ui.button(
                    icon="arrow_back", on_click=lambda: ui.navigate.to("/products"),
                ).props("flat round")
                ui.label(product.name).classes("text-h5 font-bold")

            # Product info card
            with ui.card().classes("w-full p-4"):
                ui.label("Product Information").classes("text-subtitle1 font-bold mb-2")
                with ui.grid(columns=2).classes("gap-x-8 gap-y-2"):
                    _info_row("Category", product.category.name if product.category else "N/A")
                    _info_row("Alibaba Product ID", product.alibaba_product_id or "N/A")
                    _info_row("Alibaba URL", product.alibaba_url, is_link=True)
                    _info_row("Amazon Search Query", product.amazon_search_query or product.name)
                    if product.alibaba_price_min or product.alibaba_price_max:
                        _info_row("Alibaba Price", _format_price(
                            product.alibaba_price_min, product.alibaba_price_max
                        ))
                    if product.alibaba_supplier:
                        _info_row("Supplier", product.alibaba_supplier)
                    if product.alibaba_moq:
                        _info_row("MOQ", str(product.alibaba_moq))
                    if product.notes:
                        _info_row("Notes", product.notes)

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
                    ui.button(
                        "Run Research", icon="search",
                        on_click=lambda: ui.navigate.to("/research"),
                    ).props("color=positive")
                return

            # Metrics
            ui.label("Amazon Competition Analysis").classes("text-subtitle1 font-bold")
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
        finally:
            session.close()


def _info_row(label: str, value: str, is_link: bool = False):
    ui.label(label).classes("text-caption text-secondary font-medium")
    if is_link:
        display = value[:80] + "..." if len(value) > 80 else value
        ui.link(display, value, new_tab=True).classes("text-primary text-body2")
    else:
        ui.label(value).classes("text-body2")


def _format_price(pmin, pmax) -> str:
    if pmin and pmax:
        return f"${pmin:.2f} - ${pmax:.2f}"
    if pmin:
        return f"${pmin:.2f}"
    if pmax:
        return f"${pmax:.2f}"
    return "N/A"
