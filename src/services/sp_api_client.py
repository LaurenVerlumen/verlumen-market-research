"""Amazon SP-API client for catalog data enrichment."""
import logging
import time

from sp_api.api import CatalogItems
from sp_api.base import Marketplaces

from config import (
    SP_API_REFRESH_TOKEN,
    SP_API_LWA_APP_ID,
    SP_API_LWA_CLIENT_SECRET,
    SP_API_AWS_ACCESS_KEY,
    SP_API_AWS_SECRET_KEY,
    SP_API_ROLE_ARN,
)

logger = logging.getLogger(__name__)

# US marketplace
_MARKETPLACE_ID = "ATVPDKIKX0DER"


class SPAPIClient:
    """Wrapper around python-amazon-sp-api for catalog enrichment."""

    _RATE_LIMIT_DELAY = 0.6  # seconds between requests (2 req/s limit)
    _RETRY_MAX_ATTEMPTS = 3
    _RETRY_DELAYS = [1, 2, 4]  # exponential backoff for 429s

    def __init__(self, credentials: dict | None = None):
        self.credentials = credentials or self._default_credentials()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_credentials(self) -> bool:
        """Test SP-API connection with a known ASIN.

        Returns True if credentials work, False otherwise.
        """
        try:
            catalog = CatalogItems(credentials=self.credentials, marketplace=Marketplaces.US)
            catalog.get_item(
                asin="B000FQ9QNI",
                marketplaceIds=[_MARKETPLACE_ID],
                includedData=["summaries"],
            )
            return True
        except Exception as exc:
            logger.warning("SP-API credential validation failed: %s", exc)
            return False

    def enrich_asins(self, asins: list[str]) -> dict[str, dict]:
        """Fetch brand/manufacturer for a list of ASINs.

        Parameters
        ----------
        asins : list[str]
            ASINs to look up.

        Returns
        -------
        dict mapping ASIN -> {"brand": str | None, "manufacturer": str | None}
        """
        results: dict[str, dict] = {}
        catalog = CatalogItems(credentials=self.credentials, marketplace=Marketplaces.US)

        for i, asin in enumerate(asins):
            if i > 0:
                time.sleep(self._RATE_LIMIT_DELAY)

            data = self._fetch_item(catalog, asin)
            if data is not None:
                results[asin] = data

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_item(self, catalog: CatalogItems, asin: str) -> dict | None:
        """Fetch a single ASIN with retry on 429 errors."""
        for attempt in range(self._RETRY_MAX_ATTEMPTS):
            try:
                response = catalog.get_item(
                    asin=asin,
                    marketplaceIds=[_MARKETPLACE_ID],
                    includedData=["summaries"],
                )
                summaries = response.payload.get("summaries", [])
                if not summaries:
                    return {"brand": None, "manufacturer": None}

                summary = summaries[0]
                return {
                    "brand": summary.get("brand"),
                    "manufacturer": summary.get("manufacturer"),
                }
            except Exception as exc:
                exc_str = str(exc)
                is_throttle = "429" in exc_str or "QuotaExceeded" in exc_str
                if is_throttle and attempt < self._RETRY_MAX_ATTEMPTS - 1:
                    delay = self._RETRY_DELAYS[attempt]
                    logger.warning(
                        "SP-API throttled for ASIN %s (attempt %d/%d), retrying in %ds",
                        asin, attempt + 1, self._RETRY_MAX_ATTEMPTS, delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error("SP-API error for ASIN %s: %s", asin, exc)
                    return None
        return None

    @staticmethod
    def _default_credentials() -> dict:
        """Build credentials dict from config env vars."""
        return {
            "refresh_token": SP_API_REFRESH_TOKEN,
            "lwa_app_id": SP_API_LWA_APP_ID,
            "lwa_client_secret": SP_API_LWA_CLIENT_SECRET,
            "aws_access_key": SP_API_AWS_ACCESS_KEY,
            "aws_secret_key": SP_API_AWS_SECRET_KEY,
            "role_arn": SP_API_ROLE_ARN,
        }
