"""Product summary card component."""
from nicegui import ui

from src.ui.components.helpers import avatar_color as _avatar_color, format_price as _format_price, CARD_CLASSES


def product_card(product: dict, on_search=None):
    """Render a card for a single product with basic info and action buttons.

    Args:
        product: Dict with keys name, category (str), alibaba_url,
                 alibaba_price_min, alibaba_price_max, alibaba_image_url,
                 competitor_count (int).
        on_search: Optional callback(product) for the Search Amazon button.
    """
    price = _format_price(product.get("alibaba_price_min"), product.get("alibaba_price_max"), na_text="")
    comp_count = product.get("competitor_count", 0)
    name = product.get("name", "Unnamed")

    with ui.card().classes(CARD_CLASSES):
        with ui.row().classes("items-start justify-between w-full gap-4"):
            # Thumbnail / avatar
            if product.get("alibaba_image_url"):
                ui.image(product["alibaba_image_url"]).classes(
                    "w-12 h-12 rounded object-cover"
                ).style("flex-shrink:0")
            else:
                letter = name[0].upper() if name else "?"
                bg = _avatar_color(name)
                ui.avatar(
                    letter, color=bg, text_color="white", size="48px",
                )

            with ui.column().classes("gap-1 flex-1"):
                ui.label(name).classes("text-subtitle1 font-bold")
                with ui.row().classes("gap-2 items-center"):
                    ui.badge(product.get("category", ""), color="blue-2").props("outline")
                    if price:
                        ui.label(price).classes("text-body2 text-positive")
                ui.label(f"{comp_count} Amazon competitors found").classes(
                    "text-caption text-secondary"
                )
            with ui.column().classes("gap-2 items-end"):
                if product.get("alibaba_url"):
                    with ui.link(
                        target=product["alibaba_url"], new_tab=True,
                    ).classes("no-underline"):
                        ui.button("Alibaba", icon="open_in_new").props(
                            "flat dense color=primary size=sm"
                        )
                if on_search:
                    ui.button(
                        "Search Amazon", icon="search", on_click=lambda p=product: on_search(p)
                    ).props("flat dense color=primary")
