"""Import Helium 10 Xray Excel exports into the database."""
from __future__ import annotations

import io
import logging
import math
import statistics
from pathlib import Path
from typing import Union

import pandas as pd

from src.models.database import get_session
from src.models.amazon_competitor import AmazonCompetitor
from src.models.search_session import SearchSession

logger = logging.getLogger(__name__)

# Mapping from Xray Excel column names to our field names.
# Note: some Xray columns have double spaces (e.g. "Price  $").
_COLUMN_MAP = {
    "ASIN": "asin",
    "Product Details": "title",
    "URL": "amazon_url",
    "Image URL": "thumbnail_url",
    "Brand": "brand",
    "Price  $": "price",
    "ASIN Sales": "monthly_sales",
    "ASIN Revenue": "monthly_revenue",
    "Recent Purchases": "bought_last_month",
    "BSR": "bsr_rank",
    "Category": "bsr_category",
    "Seller Country/Region": "seller_country",
    "Fees  $": "fba_fees",
    "Active Sellers": "active_sellers",
    "Ratings": "rating",
    "Review Count": "review_count",
    "Review velocity": "review_velocity",
    "Buy Box": "buy_box_owner",
    "Size Tier": "size_tier",
    "Fulfillment": "fulfillment",
    "Dimensions": "dimensions",
    "Weight": "weight",
    "Creation Date": "listing_created_at",
    "Seller Age (mo)": "seller_age_months",
    "Seller": "seller",
    "Best Seller": "badge",
    "Sponsored": "is_sponsored",
    "Display Order": "position",
}

# Fields that should be parsed as comma-separated integers.
_INT_FIELDS = {
    "monthly_sales", "bsr_rank", "review_count", "active_sellers",
    "seller_age_months", "position",
}

# Fields that should be parsed as comma-separated floats.
_FLOAT_FIELDS = {
    "price", "monthly_revenue", "fba_fees", "rating", "review_velocity", "weight",
}


def _parse_comma_number(value) -> float | None:
    """Parse a number that may contain commas: '2,733' -> 2733.0, '86,158.96' -> 86158.96."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if math.isnan(value):
            return None
        return float(value)
    s = str(value).strip().replace(",", "")
    if not s or s.lower() == "nan":
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _safe_int(value) -> int | None:
    """Parse a value to int, handling commas and NaN."""
    f = _parse_comma_number(value)
    if f is None:
        return None
    return int(f)


def _safe_float(value) -> float | None:
    """Parse a value to float, handling commas and NaN."""
    return _parse_comma_number(value)


def _is_empty(value) -> bool:
    """Check if a value is NaN, None, or empty string."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


class XrayImporter:
    """Parse Helium 10 Xray Excel exports and import into the database."""

    def parse_xray_file(self, file_path_or_bytes: Union[str, Path, bytes], filename: str = "") -> list[dict]:
        """Parse Xray Excel file into list of competitor dicts.

        Args:
            file_path_or_bytes: File path (str/Path) or raw file bytes.
            filename: Original filename (used for logging).

        Returns:
            List of dicts with our field names, one per row.
        """
        if isinstance(file_path_or_bytes, bytes):
            df = pd.read_excel(io.BytesIO(file_path_or_bytes))
        else:
            df = pd.read_excel(str(file_path_or_bytes))

        logger.info(
            "Parsing Xray file %s: %d rows, columns: %s",
            filename or "(bytes)", len(df), list(df.columns),
        )

        # Build a flexible column map: normalize file columns to match our expected names
        # This handles whitespace differences, extra spaces, etc.
        self._resolved_col_map = self._resolve_columns(df.columns)
        logger.info("Resolved column mapping: %s", self._resolved_col_map)

        parsed_rows: list[dict] = []
        for _, row in df.iterrows():
            record = self._map_row(row)
            if not record.get("asin"):
                continue
            parsed_rows.append(record)

        logger.info("Parsed %d valid rows from Xray file", len(parsed_rows))
        return parsed_rows

    def _resolve_columns(self, file_columns) -> dict[str, str]:
        """Build a map from actual file column names to our field names.

        Handles variations in whitespace, casing, and minor naming differences
        across Helium 10 Xray export versions.
        """
        resolved: dict[str, str] = {}

        def _normalize(s: str) -> str:
            """Collapse whitespace, lowercase, strip."""
            return " ".join(s.lower().split())

        # Build normalized lookup from our expected columns
        expected_norm = {_normalize(xray_col): our_field for xray_col, our_field in _COLUMN_MAP.items()}

        for file_col in file_columns:
            norm = _normalize(str(file_col))
            if norm in expected_norm:
                resolved[str(file_col)] = expected_norm[norm]

        return resolved

    def import_xray(self, product_id: int, session_id: int, parsed_data: list[dict]) -> dict:
        """Import Xray data into DB, cross-referencing existing competitors.

        Looks up existing competitors by product_id + ASIN across ALL sessions
        so that Xray data enriches SerpAPI results instead of creating duplicates.

        Args:
            product_id: The product ID to associate competitors with.
            session_id: The search session ID for genuinely new competitors.
            parsed_data: List of dicts from parse_xray_file().

        Returns:
            {"enriched": int, "added": int, "skipped": int, "errors": list[str]}
        """
        db = get_session()
        enriched = 0
        added = 0
        skipped = 0
        errors: list[str] = []

        try:
            for record in parsed_data:
                asin = record.get("asin")
                if not asin:
                    skipped += 1
                    continue

                try:
                    # Look across ALL sessions for this product to avoid duplicates
                    existing = (
                        db.query(AmazonCompetitor)
                        .filter(
                            AmazonCompetitor.product_id == product_id,
                            AmazonCompetitor.asin == asin,
                        )
                        .first()
                    )

                    if existing:
                        self._enrich_competitor(existing, record)
                        enriched += 1
                    else:
                        comp = AmazonCompetitor(
                            product_id=product_id,
                            search_session_id=session_id,
                            asin=asin,
                        )
                        self._set_all_fields(comp, record)
                        db.add(comp)
                        added += 1

                except Exception as exc:
                    errors.append(f"ASIN {asin}: {exc}")
                    logger.warning("Error importing ASIN %s: %s", asin, exc)

            # Recalculate stats for the xray session and any sessions that got enriched
            affected_session_ids = {session_id}
            for record in parsed_data:
                asin = record.get("asin")
                if asin:
                    comp = (
                        db.query(AmazonCompetitor)
                        .filter(
                            AmazonCompetitor.product_id == product_id,
                            AmazonCompetitor.asin == asin,
                        )
                        .first()
                    )
                    if comp and comp.search_session_id:
                        affected_session_ids.add(comp.search_session_id)
            for sid in affected_session_ids:
                self._recalculate_session_stats(db, sid)

            db.commit()
        except Exception as exc:
            db.rollback()
            errors.append(f"Transaction error: {exc}")
            logger.error("Xray import transaction failed: %s", exc)
        finally:
            db.close()

        return {
            "enriched": enriched,
            "added": added,
            "skipped": skipped,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _map_row(self, row) -> dict:
        """Map a single pandas row to our field names with proper type parsing."""
        record: dict = {}

        col_map = getattr(self, "_resolved_col_map", None) or _COLUMN_MAP
        for xray_col, our_field in col_map.items():
            raw = row.get(xray_col)
            if _is_empty(raw):
                continue

            if our_field in _INT_FIELDS:
                record[our_field] = _safe_int(raw)
            elif our_field in _FLOAT_FIELDS:
                record[our_field] = _safe_float(raw)
            elif our_field == "badge":
                # "Best Seller" column: if "Yes", set badge to "Best Seller"
                if str(raw).strip().lower() == "yes":
                    record[our_field] = "Best Seller"
            elif our_field == "is_sponsored":
                # If value is not empty/NaN, it's sponsored
                record[our_field] = True
            elif our_field == "bought_last_month":
                # Store as string with commas stripped
                parsed = _safe_int(raw)
                record[our_field] = str(parsed) if parsed is not None else None
            else:
                record[our_field] = str(raw).strip()

        return record

    def _enrich_competitor(self, comp: AmazonCompetitor, record: dict) -> None:
        """Update an existing competitor with Xray data.

        Xray-specific fields (monthly_sales, monthly_revenue, seller, fba_fees, etc.)
        always overwrite. Other fields only fill in if currently missing.
        """
        # Fields that Xray always overwrites (Xray data is more accurate)
        _overwrite_fields = {
            "monthly_sales", "monthly_revenue", "seller", "seller_country",
            "fba_fees", "review_velocity", "fulfillment", "active_sellers",
            "listing_created_at", "seller_age_months", "buy_box_owner",
            "size_tier", "dimensions", "weight", "brand", "bsr_rank",
            "bsr_category",
        }

        for field, value in record.items():
            if field == "asin" or value is None:
                continue

            if field in _overwrite_fields:
                setattr(comp, field, value)
            else:
                # Only fill in if currently missing
                current = getattr(comp, field, None)
                if current is None:
                    setattr(comp, field, value)

    def _set_all_fields(self, comp: AmazonCompetitor, record: dict) -> None:
        """Set all fields on a new competitor from parsed Xray data."""
        for field, value in record.items():
            if field == "asin":
                continue
            if value is not None:
                setattr(comp, field, value)

    def _recalculate_session_stats(self, db, session_id: int) -> None:
        """Recalculate session aggregate stats from its competitors."""
        competitors = (
            db.query(AmazonCompetitor)
            .filter(AmazonCompetitor.search_session_id == session_id)
            .all()
        )

        if not competitors:
            return

        session = db.query(SearchSession).filter(SearchSession.id == session_id).first()
        if not session:
            return

        prices = [c.price for c in competitors if c.price is not None]
        ratings = [c.rating for c in competitors if c.rating is not None]
        reviews = [c.review_count for c in competitors if c.review_count is not None]
        organic_count = sum(1 for c in competitors if not c.is_sponsored)

        session.avg_price = round(statistics.mean(prices), 2) if prices else None
        session.avg_rating = round(statistics.mean(ratings), 2) if ratings else None
        session.avg_reviews = int(statistics.mean(reviews)) if reviews else None
        session.organic_results = organic_count
        session.total_results = len(competitors)
