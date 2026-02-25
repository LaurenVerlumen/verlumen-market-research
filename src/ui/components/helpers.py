"""Shared UI helper functions and design tokens for product display."""

from nicegui import ui


# ─── Design Tokens ────────────────────────────────────────────────────────────

# Card & layout
CARD_CLASSES = "w-full p-5"
INPUT_PROPS = "outlined dense"
HOVER_BG = "hover:bg-[#F5F0EB]"

# Nav active-state tokens (centralized hex values used in layout.py JS)
NAV_ACTIVE_BG = "#E8E0D6"
NAV_ACTIVE_BORDER = "#A08968"
NAV_ACTIVE_TEXT = "#4A4443"

# Action widget colors (dashboard)
ACTION_COLORS = {
    "need_research": {
        "bg": "#FFF3E0", "border": "#FF9800", "text": "#E65100",
    },
    "awaiting_review": {
        "bg": "#F5F0EB", "border": "#A08968", "text": "#5C4A32",
    },
    "approved": {
        "bg": "#E8F5E9", "border": "#4CAF50", "text": "#1B5E20",
    },
}


def page_header(title: str, subtitle: str | None = None, icon: str | None = None):
    """Render a consistent page title with optional icon + subtitle."""
    with ui.row().classes("items-center gap-3"):
        if icon:
            ui.icon(icon, size="sm").classes("text-accent")
        ui.label(title).classes("text-h5 font-bold")
    if subtitle:
        ui.label(subtitle).classes("text-body2 text-secondary")


def section_header(title: str, icon: str | None = None, subtitle: str | None = None):
    """Render a consistent card section header with accent-colored icon."""
    with ui.row().classes("items-center gap-2 mb-2"):
        if icon:
            ui.icon(icon).classes("text-accent")
        ui.label(title).classes("text-subtitle1 font-bold")
    if subtitle:
        ui.label(subtitle).classes("text-caption text-secondary")


# ─── Status Badges ────────────────────────────────────────────────────────────

# Product status badge colors and labels (shared across pages)
STATUS_COLORS = {
    "imported": "grey-5",
    "researched": "blue",
    "under_review": "warning",
    "approved": "positive",
    "rejected": "negative",
}
STATUS_LABELS = {
    "imported": "Imported",
    "researched": "Researched",
    "under_review": "Under Review",
    "approved": "Approved",
    "rejected": "Rejected",
}


# Predefined palette for letter-avatar backgrounds
AVATAR_COLORS = [
    "#E57373", "#F06292", "#BA68C8", "#9575CD", "#7986CB",
    "#64B5F6", "#4FC3F7", "#4DD0E1", "#4DB6AC", "#81C784",
    "#AED581", "#DCE775", "#FFD54F", "#FFB74D", "#FF8A65",
    "#A1887F", "#90A4AE",
]


def avatar_color(name: str) -> str:
    """Return a deterministic color based on the first letter of *name*."""
    idx = ord(name[0].upper()) % len(AVATAR_COLORS) if name else 0
    return AVATAR_COLORS[idx]


def product_thumbnail(product, size: int = 48) -> None:
    """Render a compact product thumbnail with fallback to letter avatar.

    Designed for use at the top of tab panels to provide product context.
    """
    name = getattr(product, "name", None) or (
        product.get("name") if isinstance(product, dict) else "?"
    )
    img_src = product_image_src(product)
    with ui.row().classes("items-center gap-3 mb-3"):
        if img_src:
            ui.image(img_src).classes("rounded-lg object-cover").style(
                f"width: {size}px; height: {size}px; flex-shrink: 0"
            )
        else:
            letter = name[0].upper() if name else "?"
            bg = avatar_color(name or "?")
            ui.avatar(
                letter, color=bg, text_color="white",
                size=f"{size}px", font_size=f"{size // 3}px",
            ).classes("rounded-lg")
        ui.label(name or "Unknown Product").classes(
            "text-subtitle2 font-medium text-secondary"
        )


def product_image_src(product) -> str | None:
    """Return the best image source URL for a product (local preferred).

    Works with both ORM Product objects and dicts with
    'local_image_path' / 'alibaba_image_url' keys.
    """
    local = getattr(product, "local_image_path", None) or (
        product.get("local_image_path") if isinstance(product, dict) else None
    )
    if local:
        return f"/images/{local}"
    remote = getattr(product, "alibaba_image_url", None) or (
        product.get("alibaba_image_url") if isinstance(product, dict) else None
    )
    if remote:
        return remote
    return None


def format_price(pmin, pmax, na_text: str = "-") -> str:
    """Format a min/max price range into a display string."""
    if pmin is not None and pmax is not None:
        return f"${pmin:.2f} - ${pmax:.2f}"
    if pmin is not None:
        return f"${pmin:.2f}"
    if pmax is not None:
        return f"${pmax:.2f}"
    return na_text
