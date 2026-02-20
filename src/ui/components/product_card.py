"""Product summary card component."""
from nicegui import ui


def product_card(product: dict, on_search=None):
    """Render a card for a single product with basic info and action buttons.

    Args:
        product: Dict with keys name, category (str), alibaba_url,
                 alibaba_price_min, alibaba_price_max, competitor_count (int).
        on_search: Optional callback(product) for the Search Amazon button.
    """
    price = _format_price(product.get("alibaba_price_min"), product.get("alibaba_price_max"))
    comp_count = product.get("competitor_count", 0)

    with ui.card().classes("w-full p-4"):
        with ui.row().classes("items-start justify-between w-full"):
            with ui.column().classes("gap-1 flex-1"):
                ui.label(product.get("name", "Unnamed")).classes("text-subtitle1 font-bold")
                with ui.row().classes("gap-2 items-center"):
                    ui.badge(product.get("category", ""), color="blue-2").props("outline")
                    if price:
                        ui.label(price).classes("text-body2 text-positive")
                ui.label(f"{comp_count} Amazon competitors found").classes(
                    "text-caption text-secondary"
                )
            with ui.column().classes("gap-2 items-end"):
                if product.get("alibaba_url"):
                    ui.link("Alibaba", target=product["alibaba_url"]).classes(
                        "text-caption"
                    ).props('target="_blank"')
                if on_search:
                    ui.button(
                        "Search Amazon", icon="search", on_click=lambda p=product: on_search(p)
                    ).props("flat dense color=primary")


def _format_price(pmin, pmax) -> str:
    if pmin is not None and pmax is not None:
        return f"${pmin:.2f} - ${pmax:.2f}"
    if pmin is not None:
        return f"${pmin:.2f}"
    if pmax is not None:
        return f"${pmax:.2f}"
    return ""
