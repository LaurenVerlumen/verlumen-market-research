"""Scheduled research -- auto-research products on a configurable schedule."""
import json
import logging
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import SERPAPI_KEY, DATA_DIR

logger = logging.getLogger(__name__)

_SCHEDULE_FILE = DATA_DIR / "schedule_config.json"
_scheduler: BackgroundScheduler | None = None


def _default_config() -> dict:
    return {
        "enabled": False,
        "frequency": "weekly",  # "daily", "weekly", "monthly"
        "hour": 2,  # run at 2 AM
        "day_of_week": "mon",  # for weekly
        "last_run": None,
        "products_researched": 0,
    }


def load_config() -> dict:
    """Load schedule config from JSON file."""
    if _SCHEDULE_FILE.exists():
        try:
            with open(_SCHEDULE_FILE, "r") as f:
                cfg = json.load(f)
            # Merge with defaults for any missing keys
            defaults = _default_config()
            defaults.update(cfg)
            return defaults
        except (json.JSONDecodeError, OSError):
            pass
    return _default_config()


def save_config(config: dict) -> None:
    """Save schedule config to JSON file."""
    try:
        with open(_SCHEDULE_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except OSError:
        logger.exception("Failed to save schedule config")


def _build_trigger(config: dict):
    """Build an APScheduler trigger from config."""
    freq = config.get("frequency", "weekly")
    hour = config.get("hour", 2)

    if freq == "daily":
        return CronTrigger(hour=hour, minute=0)
    elif freq == "weekly":
        dow = config.get("day_of_week", "mon")
        return CronTrigger(day_of_week=dow, hour=hour, minute=0)
    elif freq == "monthly":
        return CronTrigger(day=1, hour=hour, minute=0)
    return CronTrigger(day_of_week="mon", hour=hour, minute=0)


def _run_scheduled_research():
    """Execute scheduled research for all products that need it."""
    if not SERPAPI_KEY:
        logger.warning("Scheduled research skipped: no SERPAPI_KEY configured")
        return

    from src.models import get_session, Product, SearchSession, AmazonCompetitor
    from src.services import AmazonSearchService, CompetitionAnalyzer
    from src.services.match_scorer import score_matches
    from src.services.category_helpers import get_search_context

    logger.info("Starting scheduled research run...")

    db = get_session()
    try:
        # Find products with status "imported" or "researched" that have search queries
        products = (
            db.query(Product)
            .filter(Product.status.in_(["imported", "researched"]))
            .all()
        )

        if not products:
            logger.info("No products need research")
            return

        search_service = AmazonSearchService(api_key=SERPAPI_KEY)
        analyzer = CompetitionAnalyzer()
        researched_count = 0

        for product in products:
            query = product.amazon_search_query or product.name
            if not query:
                continue

            try:
                # Resolve department + query suffix from category hierarchy
                ctx = get_search_context(product.category)
                dept = ctx["department"]
                if ctx["query_suffix"] and ctx["query_suffix"].lower() not in query.lower():
                    query = f"{query} {ctx['query_suffix']}"

                logger.info(f"Researching: {product.name} (query: {query})")

                results = search_service.search(query, department=dept)
                competitors = results.get("organic_results", [])

                if not competitors:
                    continue

                # Analyze
                analysis = analyzer.analyze(competitors)

                # Score matches
                scored = score_matches(product.name, competitors)

                # Create session
                session_obj = SearchSession(
                    product_id=product.id,
                    search_query=query,
                    amazon_domain=search_service.amazon_domain,
                    total_results=len(scored),
                    organic_results=len([c for c in scored if not c.get("is_sponsored")]),
                    sponsored_results=len([c for c in scored if c.get("is_sponsored")]),
                    avg_price=analysis.get("avg_price"),
                    avg_rating=analysis.get("avg_rating"),
                    avg_reviews=int(analysis.get("avg_reviews", 0)),
                )
                db.add(session_obj)
                db.flush()

                # Save competitors
                for comp in scored:
                    db_comp = AmazonCompetitor(
                        product_id=product.id,
                        search_session_id=session_obj.id,
                        asin=comp.get("asin", ""),
                        title=comp.get("title"),
                        price=comp.get("price"),
                        rating=comp.get("rating"),
                        review_count=comp.get("review_count"),
                        bought_last_month=comp.get("bought_last_month"),
                        is_prime=comp.get("is_prime", False),
                        badge=comp.get("badge"),
                        amazon_url=comp.get("amazon_url"),
                        thumbnail_url=comp.get("thumbnail_url"),
                        is_sponsored=comp.get("is_sponsored", False),
                        position=comp.get("position"),
                        match_score=comp.get("match_score"),
                    )
                    db.add(db_comp)

                product.status = "researched"
                db.commit()
                researched_count += 1
                logger.info(f"  -> Found {len(scored)} competitors")

            except Exception as exc:
                logger.exception(f"Failed to research {product.name}: {exc}")
                db.rollback()
                continue

        # Update config with last run info
        config = load_config()
        config["last_run"] = datetime.utcnow().isoformat()
        config["products_researched"] = researched_count
        save_config(config)

        logger.info(f"Scheduled research complete: {researched_count} products researched")

    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler | None:
    """Start the background scheduler if enabled in config."""
    global _scheduler

    config = load_config()
    if not config.get("enabled"):
        logger.info("Scheduled research is disabled")
        return None

    _scheduler = BackgroundScheduler()
    trigger = _build_trigger(config)
    _scheduler.add_job(
        _run_scheduled_research,
        trigger=trigger,
        id="scheduled_research",
        name="Verlumen Scheduled Research",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(f"Scheduler started: {config['frequency']} at {config.get('hour', 2)}:00")
    return _scheduler


def stop_scheduler():
    """Stop the scheduler if running."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def restart_scheduler():
    """Restart the scheduler with current config."""
    stop_scheduler()
    return start_scheduler()


def run_now():
    """Trigger an immediate research run (for manual 'Run Now' button)."""
    _run_scheduled_research()


def get_scheduler_status() -> dict:
    """Return current scheduler status for UI display."""
    config = load_config()
    return {
        "enabled": config.get("enabled", False),
        "frequency": config.get("frequency", "weekly"),
        "hour": config.get("hour", 2),
        "day_of_week": config.get("day_of_week", "mon"),
        "last_run": config.get("last_run"),
        "products_researched": config.get("products_researched", 0),
        "running": _scheduler is not None and _scheduler.running,
    }
