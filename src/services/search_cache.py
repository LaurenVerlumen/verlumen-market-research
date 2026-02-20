"""SQLite-based search result cache for Amazon searches."""
import hashlib
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import func

from src.models.database import get_session
from src.models.search_cache_model import SearchCacheEntry

logger = logging.getLogger(__name__)

# Cache TTL: 24 hours (competitor data changes slowly)
CACHE_TTL_HOURS = 24


class SearchCache:
    """Cache layer for Amazon search results using SQLite."""

    @staticmethod
    def _query_hash(query: str, domain: str, max_pages: int) -> str:
        """Generate a SHA256 hash for cache key."""
        key = f"{query.strip().lower()}|{domain}|{max_pages}"
        return hashlib.sha256(key.encode()).hexdigest()

    def get_cached_results(self, query: str, domain: str, max_pages: int) -> dict | None:
        """Return cached search results or None if not found / expired."""
        q_hash = self._query_hash(query, domain, max_pages)
        session = get_session()
        try:
            entry = (
                session.query(SearchCacheEntry)
                .filter_by(query_hash=q_hash)
                .first()
            )
            if entry is None:
                return None
            if entry.expires_at < datetime.utcnow():
                session.delete(entry)
                session.commit()
                return None
            # Update hit count
            entry.hit_count = (entry.hit_count or 0) + 1
            session.commit()
            return json.loads(entry.response_json)
        except Exception:
            logger.exception("Error reading search cache")
            return None
        finally:
            session.close()

    def cache_results(self, query: str, domain: str, max_pages: int, response: dict) -> None:
        """Store search results in cache."""
        q_hash = self._query_hash(query, domain, max_pages)
        now = datetime.utcnow()
        session = get_session()
        try:
            # Upsert: delete existing then insert
            existing = (
                session.query(SearchCacheEntry)
                .filter_by(query_hash=q_hash)
                .first()
            )
            if existing:
                session.delete(existing)
                session.flush()

            entry = SearchCacheEntry(
                query_hash=q_hash,
                query=query,
                domain=domain,
                max_pages=max_pages,
                response_json=json.dumps(response),
                created_at=now,
                expires_at=now + timedelta(hours=CACHE_TTL_HOURS),
                hit_count=0,
            )
            session.add(entry)
            session.commit()
        except Exception:
            logger.exception("Error writing search cache")
            session.rollback()
        finally:
            session.close()

    def clear_expired_cache(self) -> int:
        """Remove expired cache entries. Returns count of entries cleared."""
        session = get_session()
        try:
            now = datetime.utcnow()
            count = (
                session.query(SearchCacheEntry)
                .filter(SearchCacheEntry.expires_at < now)
                .delete()
            )
            session.commit()
            return count
        except Exception:
            logger.exception("Error clearing expired cache")
            session.rollback()
            return 0
        finally:
            session.close()

    def get_stats(self) -> dict:
        """Return cache statistics."""
        session = get_session()
        try:
            now = datetime.utcnow()
            total = session.query(SearchCacheEntry).count()
            expired = (
                session.query(SearchCacheEntry)
                .filter(SearchCacheEntry.expires_at < now)
                .count()
            )
            active = total - expired
            total_hits = (
                session.query(func.coalesce(func.sum(SearchCacheEntry.hit_count), 0))
                .scalar()
            )
            return {
                "total_entries": total,
                "active_entries": active,
                "expired_entries": expired,
                "total_hits": int(total_hits),
            }
        except Exception:
            logger.exception("Error getting cache stats")
            return {
                "total_entries": 0,
                "active_entries": 0,
                "expired_entries": 0,
                "total_hits": 0,
            }
        finally:
            session.close()
