"""Parse Alibaba product URLs and fetch full product names via Google."""
import logging
import re
import time
from urllib.parse import urlparse

import requests

from config import SERPAPI_KEY

logger = logging.getLogger(__name__)


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


def fetch_full_name(slug_name: str, product_id: str | None = None) -> str | None:
    """Fetch the full product name from Google's index of Alibaba.

    The URL slug is often truncated. Google caches the full title.
    Costs 1 SerpAPI credit per call.

    Returns:
        Full product name or None if not found.
    """
    if not SERPAPI_KEY:
        return None

    try:
        params = {
            "engine": "google",
            "q": f'intitle:"{slug_name}" alibaba',
            "api_key": SERPAPI_KEY,
            "num": 3,
            "hl": "en",
            "gl": "us",
        }
        resp = requests.get(
            "https://serpapi.com/search", params=params, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()

        for result in data.get("organic_results", []):
            link = result.get("link", "")
            title = result.get("title", "")
            # Match our specific product if we have the ID
            if product_id and product_id in link:
                return _clean_google_title(title)
            # Otherwise take the first alibaba.com result
            if "alibaba.com/product-detail/" in link and title:
                return _clean_google_title(title)
    except Exception as e:
        logger.warning("Failed to fetch full name for '%s': %s", slug_name, e)

    return None


def fetch_full_names_batch(
    products: list[dict], on_progress=None
) -> dict[int, str]:
    """Fetch full names for multiple products.

    Args:
        products: List of dicts with keys: id, name, product_id
        on_progress: Optional callback(current, total, product_name)

    Returns:
        Dict mapping product_id (int) to full name (str).
    """
    results = {}
    for i, prod in enumerate(products):
        if on_progress:
            on_progress(i + 1, len(products), prod.get("name", ""))

        full_name = fetch_full_name(prod["name"], prod.get("product_id"))
        if full_name and full_name != prod["name"]:
            results[prod["id"]] = full_name

        # Rate limit: 1.5s between requests
        if i < len(products) - 1:
            time.sleep(1.5)

    return results


def _clean_google_title(title: str) -> str:
    """Clean a Google search result title.

    Removes common suffixes like ' - Alibaba.com', '| Alibaba', etc.
    """
    # Remove trailing platform indicators
    title = re.sub(r"\s*[-|]\s*(Alibaba\.com|Alibaba|alibaba).*$", "", title)
    # Remove trailing ellipsis artifacts
    title = re.sub(r"\s*\.{3}\s*$", "", title)
    return title.strip()


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
