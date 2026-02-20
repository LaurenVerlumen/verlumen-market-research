"""Amazon product search via SerpAPI."""
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class AmazonSearchError(Exception):
    """Raised when an Amazon search request fails."""


class AmazonSearchService:
    """SerpAPI wrapper for Amazon product search."""

    SERPAPI_URL = "https://serpapi.com/search"

    def __init__(self, api_key: str, amazon_domain: str = "amazon.com"):
        self.api_key = api_key
        self.amazon_domain = amazon_domain

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_api_key(self) -> bool:
        """Validate that the API key works by making a minimal request.

        Returns True if valid, False otherwise.
        """
        try:
            resp = requests.get(
                self.SERPAPI_URL,
                params={
                    "engine": "amazon",
                    "amazon_domain": self.amazon_domain,
                    "k": "test",
                    "page": 1,
                    "api_key": self.api_key,
                },
                timeout=15,
            )
            if resp.status_code == 401:
                return False
            resp.raise_for_status()
            return True
        except requests.RequestException:
            return False

    def get_remaining_searches(self) -> Optional[int]:
        """Return remaining API searches if the account endpoint is available."""
        try:
            resp = requests.get(
                "https://serpapi.com/account",
                params={"api_key": self.api_key},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("total_searches_left")
        except requests.RequestException:
            return None

    def search_products(self, query: str, page: int = 1) -> dict:
        """Search Amazon via SerpAPI and return structured results.

        Parameters
        ----------
        query : str
            The search term to look up on Amazon.
        page : int
            Result page number (1-based).

        Returns
        -------
        dict with keys: query, total_organic, total_sponsored, competitors
        """
        params = {
            "engine": "amazon",
            "amazon_domain": self.amazon_domain,
            "k": query,
            "page": page,
            "api_key": self.api_key,
        }

        try:
            resp = requests.get(self.SERPAPI_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise AmazonSearchError(f"SerpAPI request failed: {exc}") from exc

        if "error" in data:
            raise AmazonSearchError(f"SerpAPI error: {data['error']}")

        organic = data.get("organic_results", [])
        sponsored = data.get("sponsored_results", [])

        competitors: list[dict] = []

        for pos, item in enumerate(organic, start=1):
            competitors.append(self._parse_result(item, position=pos, is_sponsored=False))

        for pos, item in enumerate(sponsored, start=len(organic) + 1):
            competitors.append(self._parse_result(item, position=pos, is_sponsored=True))

        return {
            "query": query,
            "total_organic": len(organic),
            "total_sponsored": len(sponsored),
            "competitors": competitors,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_price(item: dict) -> Optional[float]:
        """Extract a float price from various SerpAPI formats."""
        price = item.get("price")
        if price is None:
            # Some results nest pricing under "price_info" or "extracted_price"
            price = item.get("extracted_price")
        if price is None:
            return None
        if isinstance(price, dict):
            value = price.get("value") or price.get("current_price")
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None
            raw = price.get("raw", "")
            return AmazonSearchService._price_from_string(raw)
        if isinstance(price, (int, float)):
            return float(price)
        if isinstance(price, str):
            return AmazonSearchService._price_from_string(price)
        return None

    @staticmethod
    def _price_from_string(raw: str) -> Optional[float]:
        """Parse '$12.99' style strings into a float."""
        cleaned = raw.replace("$", "").replace(",", "").strip()
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    @staticmethod
    def _parse_rating(item: dict) -> Optional[float]:
        rating = item.get("rating")
        if rating is not None:
            try:
                return float(rating)
            except (TypeError, ValueError):
                return None
        return None

    @staticmethod
    def _parse_reviews(item: dict) -> Optional[int]:
        for key in ("reviews", "ratings_total", "reviews_total"):
            val = item.get(key)
            if val is not None:
                try:
                    if isinstance(val, str):
                        val = val.replace(",", "")
                    return int(val)
                except (TypeError, ValueError):
                    continue
        return None

    @staticmethod
    def _parse_badge(item: dict) -> Optional[str]:
        badge = item.get("badge")
        if badge:
            return str(badge)
        # SerpAPI sometimes puts it under amazons_choice or best_seller
        if item.get("amazons_choice"):
            return "Amazon's Choice"
        if item.get("best_seller"):
            return "Best Seller"
        return None

    def _parse_result(self, item: dict, *, position: int, is_sponsored: bool) -> dict:
        return {
            "asin": item.get("asin"),
            "title": item.get("title", ""),
            "price": self._parse_price(item),
            "rating": self._parse_rating(item),
            "review_count": self._parse_reviews(item),
            "bought_last_month": item.get("bought_last_month") or item.get("bought_past_month"),
            "is_prime": bool(item.get("is_prime", False)),
            "badge": self._parse_badge(item),
            "thumbnail_url": item.get("thumbnail"),
            "amazon_url": item.get("link"),
            "is_sponsored": is_sponsored,
            "position": position,
        }
