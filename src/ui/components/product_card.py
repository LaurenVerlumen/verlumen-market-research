"""Product summary card component."""
from nicegui import ui


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


def product_card(product: dict, on_search=None):
    """Render a card for a single product with basic info and action buttons.

    Args:
        product: Dict with keys name, category (str), alibaba_url,
                 alibaba_price_min, alibaba_price_max, alibaba_image_url,
                 competitor_count (int).
        on_search: Optional callback(product) for the Search Amazon button.
    """
    price = _format_price(product.get("alibaba_price_min"), product.get("alibaba_price_max"))
    comp_count = product.get("competitor_count", 0)
    name = product.get("name", "Unnamed")

    with ui.card().classes("w-full p-4"):
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


def _format_price(pmin, pmax) -> str:
    if pmin is not None and pmax is not None:
        return f"${pmin:.2f} - ${pmax:.2f}"
    if pmin is not None:
        return f"${pmin:.2f}"
    if pmax is not None:
        return f"${pmax:.2f}"
    return ""
