"""Fetch product images via SerpAPI Google Images search."""
import logging
import time

import requests

logger = logging.getLogger(__name__)


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
        query = f"{product_name} wooden toy alibaba"

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
            dict mapping product_id -> image_url (only for successful fetches).
        """
        results: dict[int, str] = {}
        total = len(products)

        for idx, prod in enumerate(products, start=1):
            pid = prod["id"]
            name = prod["name"]

            if on_progress:
                on_progress(idx, total, name)

            url = self.fetch_product_image(name)
            if url:
                results[pid] = url

            # Rate-limit: pause between requests (skip after last)
            if idx < total:
                time.sleep(1.5)

        return results
