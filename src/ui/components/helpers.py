"""Shared UI helper functions for product display."""


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
