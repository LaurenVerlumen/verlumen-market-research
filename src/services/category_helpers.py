"""Category helper utilities for search context resolution."""
import re

from config import AMAZON_DEPARTMENT_DEFAULT


def get_search_context(category) -> dict:
    """Return search context dict from a Category object.

    Returns:
        {"department": "toys-and-games", "query_suffix": "Arts Crafts"}
    """
    if category is None:
        return {"department": AMAZON_DEPARTMENT_DEFAULT, "query_suffix": ""}

    department = category.resolve_department()

    # Use the leaf category name as query suffix, stripping special chars
    raw = category.name
    suffix = re.sub(r"[^a-zA-Z0-9\s]", "", raw).strip()
    # Collapse multiple spaces
    suffix = re.sub(r"\s+", " ", suffix)

    return {"department": department, "query_suffix": suffix}
