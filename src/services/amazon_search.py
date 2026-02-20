"""Amazon product search via SerpAPI."""
import logging
import time
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
        self._cache = None  # Lazy-loaded SearchCache instance

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

    def search_products(
        self,
        query: str,
        max_pages: int = 2,
        amazon_department: str | None = None,
    ) -> dict:
        """Search Amazon via SerpAPI and return structured results.

        Parameters
        ----------
        query : str
            The search term to look up on Amazon.
        max_pages : int
            Number of result pages to fetch (1-3, default 2).
        amazon_department : str | None
            SerpAPI department filter (e.g. "toys-and-games", "baby-products").
            None or "aps" means all departments.

        Returns
        -------
        dict with keys: query, total_organic, total_sponsored, competitors,
             pages_fetched, cache_hit, amazon_department
        """
        max_pages = max(1, min(max_pages, 3))
        # Normalise: treat "aps" and empty as no filter
        dept = amazon_department if amazon_department and amazon_department != "aps" else None

        # Check cache first
        cache = self._get_cache()
        if cache is not None:
            cached = cache.get_cached_results(query, self.amazon_domain, max_pages)
            if cached is not None:
                cached["cache_hit"] = True
                return cached

        all_competitors: list[dict] = []
        seen_asins: set[str] = set()
        total_organic = 0
        total_sponsored = 0
        pages_fetched = 0

        for page_num in range(1, max_pages + 1):
            if page_num > 1:
                time.sleep(1.5)  # Rate limit between page requests

            page_result = self._fetch_single_page(query, page_num, department=dept)
            pages_fetched += 1

            total_organic += page_result["organic_count"]
            total_sponsored += page_result["sponsored_count"]

            # Dedup by ASIN, keep first occurrence position
            for comp in page_result["competitors"]:
                asin = comp.get("asin")
                if asin and asin in seen_asins:
                    continue
                if asin:
                    seen_asins.add(asin)
                all_competitors.append(comp)

        result = {
            "query": query,
            "total_organic": total_organic,
            "total_sponsored": total_sponsored,
            "competitors": all_competitors,
            "pages_fetched": pages_fetched,
            "total_results_across_pages": len(all_competitors),
            "cache_hit": False,
            "amazon_department": dept,
        }

        # Cache the result
        if cache is not None:
            cache.cache_results(query, self.amazon_domain, max_pages, result)

        return result

    _RETRY_MAX_ATTEMPTS = 3
    _RETRY_DELAYS = [2, 4, 8]  # Exponential backoff in seconds
    _RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
    _NON_RETRYABLE_STATUS_CODES = {401, 403}

    def _fetch_single_page(
        self, query: str, page: int, department: str | None = None,
    ) -> dict:
        """Fetch a single page of Amazon search results with retry logic."""
        params = {
            "engine": "amazon",
            "amazon_domain": self.amazon_domain,
            "k": query,
            "page": page,
            "api_key": self.api_key,
        }
        if department:
            params["amazon_department"] = department

        last_exc = None
        for attempt in range(self._RETRY_MAX_ATTEMPTS):
            try:
                resp = requests.get(self.SERPAPI_URL, params=params, timeout=30)
                if resp.status_code in self._NON_RETRYABLE_STATUS_CODES:
                    raise AmazonSearchError(
                        f"SerpAPI auth error (HTTP {resp.status_code})"
                    )
                if resp.status_code in self._RETRYABLE_STATUS_CODES:
                    raise requests.HTTPError(
                        f"HTTP {resp.status_code}", response=resp
                    )
                resp.raise_for_status()
                data = resp.json()
                break
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < self._RETRY_MAX_ATTEMPTS - 1:
                    delay = self._RETRY_DELAYS[attempt]
                    logger.warning(
                        "SerpAPI request failed (attempt %d/%d), retrying in %ds: %s",
                        attempt + 1, self._RETRY_MAX_ATTEMPTS, delay, exc,
                    )
                    time.sleep(delay)
                else:
                    raise AmazonSearchError(
                        f"SerpAPI request failed after {self._RETRY_MAX_ATTEMPTS} attempts: {exc}"
                    ) from exc

        if "error" in data:
            raise AmazonSearchError(f"SerpAPI error: {data['error']}")

        organic = data.get("organic_results", [])
        sponsored = data.get("sponsored_results", [])

        competitors: list[dict] = []
        offset = (page - 1) * 20  # Approximate position offset for multi-page

        for pos, item in enumerate(organic, start=offset + 1):
            competitors.append(self._parse_result(item, position=pos, is_sponsored=False))

        for pos, item in enumerate(sponsored, start=offset + len(organic) + 1):
            competitors.append(self._parse_result(item, position=pos, is_sponsored=True))

        return {
            "organic_count": len(organic),
            "sponsored_count": len(sponsored),
            "competitors": competitors,
        }

    def _get_cache(self):
        """Lazy-load the search cache service."""
        if self._cache is None:
            try:
                from src.services.search_cache import SearchCache
                self._cache = SearchCache()
            except Exception:
                self._cache = False  # Sentinel: tried but failed
        if self._cache is False:
            return None
        return self._cache

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
