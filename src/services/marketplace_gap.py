"""Cross-Marketplace Gap Analyzer service.

Compares products and competitors across all supported Amazon marketplaces.
Identifies price arbitrage, competition differences, and whitespace opportunities.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from config import AMAZON_MARKETPLACES
from src.models.database import get_session
from src.models.product import Product
from src.models.search_session import SearchSession
from src.models.amazon_competitor import AmazonCompetitor


@dataclass
class MarketplaceSnapshot:
    """Summary of a product's competitive landscape in one marketplace."""
    domain: str
    currency: str
    session_count: int = 0
    competitor_count: int = 0
    avg_price: float | None = None
    min_price: float | None = None
    max_price: float | None = None
    avg_rating: float | None = None
    avg_reviews: float | None = None
    top_asins: list[str] = field(default_factory=list)


@dataclass
class ArbitrageAlert:
    """Flags significant price differences across marketplaces."""
    asin: str
    title: str | None
    prices: dict[str, float]  # domain -> price
    min_domain: str
    max_domain: str
    min_price: float
    max_price: float
    differential_pct: float


@dataclass
class MarketplaceGapResult:
    """Full gap analysis for a single product across marketplaces."""
    product_id: int
    product_name: str
    marketplace_count: int
    snapshots: dict[str, MarketplaceSnapshot]  # domain -> snapshot
    arbitrage_alerts: list[ArbitrageAlert]
    whitespace: list[dict]  # ASINs present in some marketplaces but not others
    opportunity_scores: dict[str, float]  # domain -> score (0-100)


def get_multi_marketplace_products() -> list[dict]:
    """Return products that have research in more than one marketplace.

    Returns list of dicts with keys: product_id, product_name, marketplace_count,
    marketplaces (list of domain strings).
    """
    db = get_session()
    try:
        # Find products with sessions in multiple distinct amazon_domains
        rows = (
            db.query(
                SearchSession.product_id,
                Product.name,
                func.count(func.distinct(SearchSession.amazon_domain)).label("mp_count"),
            )
            .join(Product, Product.id == SearchSession.product_id)
            .filter(Product.status != "deleted")
            .group_by(SearchSession.product_id, Product.name)
            .having(func.count(func.distinct(SearchSession.amazon_domain)) > 1)
            .order_by(func.count(func.distinct(SearchSession.amazon_domain)).desc())
            .all()
        )

        results = []
        for row in rows:
            # Fetch distinct domains for this product
            domains = [
                d[0] for d in
                db.query(func.distinct(SearchSession.amazon_domain))
                .filter(SearchSession.product_id == row.product_id)
                .all()
                if d[0]
            ]
            results.append({
                "product_id": row.product_id,
                "product_name": row.name,
                "marketplace_count": row.mp_count,
                "marketplaces": domains,
            })
        return results
    finally:
        db.close()


def get_all_products_with_research() -> list[dict]:
    """Return all products that have at least one search session, with marketplace info.

    Useful for showing single-marketplace products too.
    """
    db = get_session()
    try:
        rows = (
            db.query(
                SearchSession.product_id,
                Product.name,
                func.count(func.distinct(SearchSession.amazon_domain)).label("mp_count"),
            )
            .join(Product, Product.id == SearchSession.product_id)
            .filter(Product.status != "deleted")
            .group_by(SearchSession.product_id, Product.name)
            .order_by(func.count(func.distinct(SearchSession.amazon_domain)).desc())
            .all()
        )

        results = []
        for row in rows:
            domains = [
                d[0] for d in
                db.query(func.distinct(SearchSession.amazon_domain))
                .filter(SearchSession.product_id == row.product_id)
                .all()
                if d[0]
            ]
            results.append({
                "product_id": row.product_id,
                "product_name": row.name,
                "marketplace_count": row.mp_count,
                "marketplaces": domains,
            })
        return results
    finally:
        db.close()


def analyze_product_gap(product_id: int) -> MarketplaceGapResult | None:
    """Run full gap analysis for a product across all its researched marketplaces."""
    db = get_session()
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return None

        sessions = (
            db.query(SearchSession)
            .filter(SearchSession.product_id == product_id)
            .all()
        )
        if not sessions:
            return None

        # Group sessions by domain
        sessions_by_domain: dict[str, list[SearchSession]] = defaultdict(list)
        for s in sessions:
            domain = s.amazon_domain or "amazon.com"
            sessions_by_domain[domain].append(s)

        # Build snapshots per marketplace
        snapshots: dict[str, MarketplaceSnapshot] = {}
        # Collect all ASINs per domain for whitespace analysis
        asins_by_domain: dict[str, set[str]] = defaultdict(set)
        # Collect ASIN -> {domain: price} for arbitrage
        asin_prices: dict[str, dict[str, float]] = defaultdict(dict)
        asin_titles: dict[str, str] = {}

        for domain, domain_sessions in sessions_by_domain.items():
            mp_info = AMAZON_MARKETPLACES.get(domain, {"currency": "USD"})
            session_ids = [s.id for s in domain_sessions]

            competitors = (
                db.query(AmazonCompetitor)
                .filter(AmazonCompetitor.search_session_id.in_(session_ids))
                .all()
            )

            prices = [c.price for c in competitors if c.price is not None]
            ratings = [c.rating for c in competitors if c.rating is not None]
            reviews = [c.review_count for c in competitors if c.review_count is not None]

            # Collect ASINs
            for c in competitors:
                if c.asin:
                    asins_by_domain[domain].add(c.asin)
                    if c.price is not None:
                        asin_prices[c.asin][domain] = c.price
                    if c.title:
                        asin_titles[c.asin] = c.title

            # Top ASINs by review count
            top_comps = sorted(competitors, key=lambda c: c.review_count or 0, reverse=True)[:5]

            snapshots[domain] = MarketplaceSnapshot(
                domain=domain,
                currency=mp_info.get("currency", "USD"),
                session_count=len(domain_sessions),
                competitor_count=len(competitors),
                avg_price=round(sum(prices) / len(prices), 2) if prices else None,
                min_price=round(min(prices), 2) if prices else None,
                max_price=round(max(prices), 2) if prices else None,
                avg_rating=round(sum(ratings) / len(ratings), 1) if ratings else None,
                avg_reviews=round(sum(reviews) / len(reviews), 0) if reviews else None,
                top_asins=[c.asin for c in top_comps if c.asin],
            )

        # Arbitrage alerts: ASINs with > 30% price differential across marketplaces
        arbitrage_alerts = []
        for asin, domain_prices in asin_prices.items():
            if len(domain_prices) < 2:
                continue
            min_domain = min(domain_prices, key=domain_prices.get)
            max_domain = max(domain_prices, key=domain_prices.get)
            min_p = domain_prices[min_domain]
            max_p = domain_prices[max_domain]
            if min_p > 0:
                diff_pct = ((max_p - min_p) / min_p) * 100
                if diff_pct > 30:
                    arbitrage_alerts.append(ArbitrageAlert(
                        asin=asin,
                        title=asin_titles.get(asin),
                        prices=dict(domain_prices),
                        min_domain=min_domain,
                        max_domain=max_domain,
                        min_price=min_p,
                        max_price=max_p,
                        differential_pct=round(diff_pct, 1),
                    ))
        arbitrage_alerts.sort(key=lambda a: a.differential_pct, reverse=True)

        # Whitespace detection: ASINs in top performers of one marketplace absent in others
        all_domains = set(asins_by_domain.keys())
        whitespace = []
        for domain, asins in asins_by_domain.items():
            other_domains = all_domains - {domain}
            for asin in asins:
                missing_in = [d for d in other_domains if asin not in asins_by_domain[d]]
                if missing_in:
                    whitespace.append({
                        "asin": asin,
                        "title": asin_titles.get(asin, ""),
                        "present_in": domain,
                        "missing_in": missing_in,
                    })
        # Limit to most interesting (ASINs missing in the most marketplaces)
        whitespace.sort(key=lambda w: len(w["missing_in"]), reverse=True)
        whitespace = whitespace[:50]

        # Opportunity score per marketplace: simple heuristic
        # Higher score = fewer competitors, lower avg rating, higher avg price (more room)
        opportunity_scores = {}
        for domain, snap in snapshots.items():
            score = 50.0  # baseline
            if snap.competitor_count < 20:
                score += 15
            elif snap.competitor_count < 50:
                score += 5
            elif snap.competitor_count > 100:
                score -= 10

            if snap.avg_rating is not None:
                if snap.avg_rating < 4.0:
                    score += 15  # low avg rating = quality gap opportunity
                elif snap.avg_rating < 4.3:
                    score += 5
                else:
                    score -= 5

            if snap.avg_price is not None:
                if snap.avg_price > 25:
                    score += 10  # higher price point = more margin
                elif snap.avg_price < 10:
                    score -= 10

            opportunity_scores[domain] = max(0, min(100, round(score, 1)))

        return MarketplaceGapResult(
            product_id=product_id,
            product_name=product.name,
            marketplace_count=len(snapshots),
            snapshots=snapshots,
            arbitrage_alerts=arbitrage_alerts,
            whitespace=whitespace,
            opportunity_scores=opportunity_scores,
        )
    finally:
        db.close()
