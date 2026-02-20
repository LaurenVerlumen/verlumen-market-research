"""Product detail page - Alibaba info + Amazon competition analysis."""
from nicegui import ui

from src.models import get_session, Product, AmazonCompetitor, SearchSession
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
                    if product.alibaba_image_url:
                        ui.image(product.alibaba_image_url).classes(
                            "w-32 h-32 rounded-lg object-cover"
                        ).style("flex-shrink:0")
                    else:
                        letter = product.name[0].upper() if product.name else "?"
                        bg = _avatar_color(product.name)
                        ui.avatar(
                            letter, color=bg, text_color="white", size="128px",
                            font_size="48px",
                        ).classes("rounded-lg")

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
                            _info_row(
                                "Amazon Search Query",
                                product.amazon_search_query or product.name,
                            )
                            if product.alibaba_price_min is not None or product.alibaba_price_max is not None:
                                _info_row(
                                    "Alibaba Price",
                                    _format_price(
                                        product.alibaba_price_min,
                                        product.alibaba_price_max,
                                    ),
                                )
                            if product.alibaba_supplier:
                                _info_row("Supplier", product.alibaba_supplier)
                            if product.alibaba_moq:
                                _info_row("MOQ", str(product.alibaba_moq))
                            if product.notes:
                                _info_row("Notes", product.notes)

                        # Prominent Alibaba link button
                        if product.alibaba_url:
                            with ui.link(
                                target=product.alibaba_url, new_tab=True,
                            ).classes("no-underline mt-2"):
                                ui.button(
                                    "View on Alibaba", icon="open_in_new",
                                ).props("color=accent")

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
    if pmin is not None and pmax is not None:
        return f"${pmin:.2f} - ${pmax:.2f}"
    if pmin is not None:
        return f"${pmin:.2f}"
    if pmax is not None:
        return f"${pmax:.2f}"
    return "N/A"
