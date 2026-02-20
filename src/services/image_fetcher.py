"""Fetch product images via SerpAPI Google Images search."""
import logging
import mimetypes
import time
from pathlib import Path

import requests

from config import IMAGES_DIR

logger = logging.getLogger(__name__)


def download_image(url: str, product_id: int) -> str | None:
    """Download an image from *url* and save to data/images/.

    Returns the filename (e.g. ``product_42.jpg``) on success, or None.
    """
    try:
        resp = requests.get(url, timeout=15, stream=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Failed to download image for product %d: %s", product_id, exc)
        return None

    # Determine extension from content-type or URL
    content_type = resp.headers.get("Content-Type", "")
    ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ""
    if not ext or ext == ".bin":
        # Fallback: guess from URL path
        url_path = url.split("?")[0]
        if "." in url_path.rsplit("/", 1)[-1]:
            ext = "." + url_path.rsplit(".", 1)[-1].lower()
        else:
            ext = ".jpg"
    # Normalize jpeg
    if ext in (".jpeg", ".jpe"):
        ext = ".jpg"

    filename = f"product_{product_id}{ext}"
    filepath = IMAGES_DIR / filename

    try:
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
    except OSError as exc:
        logger.warning("Failed to save image for product %d: %s", product_id, exc)
        return None

    logger.info("Saved image for product %d: %s", product_id, filename)
    return filename


def save_uploaded_image(content: bytes, product_id: int, original_name: str) -> str:
    """Save a user-uploaded image for a product.

    Returns the filename (e.g. ``product_42_manual.png``).
    """
    ext = Path(original_name).suffix.lower() or ".jpg"
    filename = f"product_{product_id}_manual{ext}"
    filepath = IMAGES_DIR / filename

    with open(filepath, "wb") as f:
        f.write(content)

    logger.info("Saved uploaded image for product %d: %s", product_id, filename)
    return filename


class ImageFetcher:
    """Fetches product images from SerpAPI Google Images."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def fetch_product_image(self, product_name: str) -> str | None:
        """Fetch a product image URL using SerpAPI Google Images.

        Searches for the product name + context keywords to find
        an Alibaba product image.

        Returns the image URL (original resolution) or None.
        """
        query = f"{product_name} product alibaba"

        params = {
            "engine": "google_images",
            "q": query,
            "num": 5,
            "api_key": self.api_key,
        }

        try:
            resp = requests.get(
                "https://serpapi.com/search", params=params, timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            logger.warning("SerpAPI request failed for %r: %s", product_name, exc)
            return None

        images = data.get("images_results", [])
        if not images:
            logger.info("No image results for %r", product_name)
            return None

        # Prefer Alibaba CDN images
        for img in images:
            original = img.get("original", "")
            if "alicdn.com" in original or "alibaba.com" in original:
                return original

        # Fallback: first result
        return images[0].get("original")

    def fetch_and_save(self, product_name: str, product_id: int) -> tuple[str | None, str | None]:
        """Fetch image URL via SerpAPI and download it locally.

        Returns (image_url, local_filename) — either can be None.
        """
        url = self.fetch_product_image(product_name)
        if not url:
            return None, None

        filename = download_image(url, product_id)
        return url, filename

    def fetch_images_batch(
        self,
        products: list[dict],
        on_progress=None,
    ) -> dict:
        """Fetch images for multiple products.

        Args:
            products: list of dicts with 'id' and 'name' keys.
            on_progress: optional callback(current, total, product_name).

        Returns:
            dict mapping product_id -> (image_url, local_filename).
        """
        results: dict[int, tuple[str | None, str | None]] = {}
        total = len(products)

        for idx, prod in enumerate(products, start=1):
            pid = prod["id"]
            name = prod["name"]

            if on_progress:
                on_progress(idx, total, name)

            url, filename = self.fetch_and_save(name, pid)
            if url:
                results[pid] = (url, filename)

            # Rate-limit: pause between requests (skip after last)
            if idx < total:
                time.sleep(1.5)

        return results
