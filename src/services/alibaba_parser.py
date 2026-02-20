"""Parse Alibaba product URLs to extract product info without HTTP requests."""
import re
from urllib.parse import urlparse


def parse_alibaba_url(url: str) -> dict:
    """Extract product name, ID, and clean URL from an Alibaba product-detail URL.

    Args:
        url: Full Alibaba URL, e.g.
            https://www.alibaba.com/product-detail/Mongolian-Children-s-Geometric-Game-Table_1600738304441.html?spm=...

    Returns:
        dict with keys: name, product_id, clean_url
    """
    parsed = urlparse(url)
    # Build a clean URL without query params
    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    # Extract the slug from the path: /product-detail/<slug>.html
    path = parsed.path.rstrip("/")
    slug = path.rsplit("/", 1)[-1]  # e.g. "Mongolian-Children-s-Geometric-Game-Table_1600738304441.html"

    # Remove .html suffix
    slug = re.sub(r"\.html$", "", slug)

    # Split slug into name part and product ID at the last underscore
    product_id = None
    name_slug = slug
    match = re.match(r"^(.+)_(\d+)$", slug)
    if match:
        name_slug = match.group(1)
        product_id = match.group(2)

    # Convert slug to human-readable name
    name = _clean_name(name_slug)

    return {
        "name": name,
        "product_id": product_id,
        "clean_url": clean_url,
    }


def _clean_name(slug: str) -> str:
    """Convert a URL slug into a clean product name.

    Handles:
    - Hyphens -> spaces
    - Dangling possessives: "Children s" -> "Children's", "Noah s" -> "Noah's"
    - Extra whitespace
    """
    name = slug.replace("-", " ")
    # Fix possessives: a word followed by a lone " s " (or at end)
    name = re.sub(r"(\w)\s+s\b", r"\1's", name)
    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name).strip()
    return name
