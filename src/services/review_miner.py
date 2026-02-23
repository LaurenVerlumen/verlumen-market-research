"""Review mining service - fetches competitor review insights from SerpAPI and synthesizes pain points."""
import json
import logging
import time
from typing import Optional

import requests

from src.models import get_session, AmazonCompetitor, SearchSession
from src.models.review_analysis import ReviewAnalysis

logger = logging.getLogger(__name__)


def mine_reviews(product_id: int, db_session=None, max_competitors: int = 5) -> dict:
    """Mine review insights for top competitors of a product.

    Returns dict with mined_count, aspects, synthesis, errors.
    """
    own_session = db_session is None
    session = db_session or get_session()
    try:
        from config import SERPAPI_KEY, ANTHROPIC_API_KEY

        if not SERPAPI_KEY:
            return {"mined_count": 0, "aspects": [], "synthesis": None, "errors": ["SERPAPI_KEY not configured"]}

        # Get latest search session for product
        latest = (
            session.query(SearchSession)
            .filter(SearchSession.product_id == product_id)
            .order_by(SearchSession.created_at.desc())
            .first()
        )
        if not latest:
            return {"mined_count": 0, "aspects": [], "synthesis": None, "errors": ["No search session found"]}

        # Get top competitors by match_score
        competitors = (
            session.query(AmazonCompetitor)
            .filter(AmazonCompetitor.search_session_id == latest.id)
            .order_by(AmazonCompetitor.match_score.desc().nullslast())
            .limit(max_competitors)
            .all()
        )
        if not competitors:
            return {"mined_count": 0, "aspects": [], "synthesis": None, "errors": ["No competitors found"]}

        # Delete existing review analyses for this product (replace on re-mine)
        session.query(ReviewAnalysis).filter(ReviewAnalysis.product_id == product_id).delete()
        session.commit()

        errors = []
        mined_count = 0
        all_aspects = []

        for comp in competitors:
            result = _fetch_review_insights(comp.asin, SERPAPI_KEY)
            if result is None:
                errors.append(f"Failed to fetch reviews for {comp.asin}")
                continue

            aspects = result.get("aspects", [])
            all_aspects.extend(aspects)

            row = ReviewAnalysis(
                product_id=product_id,
                asin=comp.asin,
                competitor_title=comp.title,
                aspects_json=json.dumps(aspects),
                raw_insights_json=json.dumps(result.get("raw_response", {})),
                rating=result.get("rating"),
                total_reviews=result.get("total_reviews"),
            )
            session.add(row)
            mined_count += 1

        session.commit()

        # Aggregate aspects across all competitors
        aggregated = _aggregate_aspects(all_aspects)

        # AI synthesis if key is set
        synthesis = None
        if ANTHROPIC_API_KEY and aggregated:
            # Get product name
            from src.models import Product
            product = session.query(Product).filter(Product.id == product_id).first()
            product_name = product.name if product else "Unknown Product"
            try:
                synthesis = _synthesize_with_claude(aggregated, product_name)
                # Store synthesis on the last inserted row
                last_row = (
                    session.query(ReviewAnalysis)
                    .filter(ReviewAnalysis.product_id == product_id)
                    .order_by(ReviewAnalysis.analyzed_at.desc())
                    .first()
                )
                if last_row:
                    last_row.product_synthesis = synthesis
                    session.commit()
            except Exception as exc:
                logger.error("AI synthesis failed: %s", exc)
                errors.append(f"AI synthesis failed: {exc}")

        return {
            "mined_count": mined_count,
            "aspects": aggregated,
            "synthesis": synthesis,
            "errors": errors,
        }
    finally:
        if own_session:
            session.close()


def get_review_analysis(product_id: int, db_session=None) -> Optional[dict]:
    """Retrieve stored review analysis for a product.

    Returns structured dict with per-competitor aspects and product_synthesis, or None.
    """
    own_session = db_session is None
    session = db_session or get_session()
    try:
        rows = (
            session.query(ReviewAnalysis)
            .filter(ReviewAnalysis.product_id == product_id)
            .order_by(ReviewAnalysis.analyzed_at.desc())
            .all()
        )
        if not rows:
            return None

        competitors = []
        product_synthesis = None
        all_aspects = []

        for row in rows:
            aspects = json.loads(row.aspects_json) if row.aspects_json else []
            all_aspects.extend(aspects)
            competitors.append({
                "asin": row.asin,
                "title": row.competitor_title,
                "aspects": aspects,
                "rating": row.rating,
                "total_reviews": row.total_reviews,
                "analyzed_at": row.analyzed_at.isoformat() if row.analyzed_at else None,
            })
            if row.product_synthesis and not product_synthesis:
                product_synthesis = row.product_synthesis

        return {
            "competitors": competitors,
            "aggregated_aspects": _aggregate_aspects(all_aspects),
            "product_synthesis": product_synthesis,
        }
    finally:
        if own_session:
            session.close()


def _fetch_review_insights(asin: str, api_key: str) -> Optional[dict]:
    """Fetch review insights from SerpAPI for a single ASIN."""
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={
                "engine": "amazon_product",
                "product_id": asin,
                "api_key": api_key,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract review insights
        reviews_info = data.get("reviews_information", {})
        summary = reviews_info.get("summary", {})
        insights = summary.get("insights", [])

        aspects = []
        for ins in insights:
            aspects.append({
                "title": ins.get("title", ""),
                "sentiment": ins.get("sentiment", ""),
                "mentions_total": ins.get("mentions", {}).get("total", 0),
                "mentions_positive": ins.get("mentions", {}).get("positive", 0),
                "mentions_negative": ins.get("mentions", {}).get("negative", 0),
                "summary": ins.get("summary", ""),
                "examples": [
                    ex.get("snippet", "") for ex in ins.get("examples", [])
                ],
            })

        # Overall rating and review count
        rating = None
        total_reviews = None
        product_info = data.get("product_information", {})
        if "reviews" in reviews_info:
            total_reviews = reviews_info.get("reviews")
        if "rating" in reviews_info:
            rating = reviews_info.get("rating")
        # Fallback to product_information
        if rating is None and "rating" in product_info:
            rating = product_info.get("rating")
        if total_reviews is None and "reviews_total" in product_info:
            total_reviews = product_info.get("reviews_total")

        # Rate limit
        time.sleep(1.5)

        return {
            "aspects": aspects,
            "rating": rating,
            "total_reviews": total_reviews,
            "raw_response": {
                "reviews_information": reviews_info,
                "top_reviews": data.get("top_reviews", [])[:5],
            },
        }
    except Exception as exc:
        logger.error("SerpAPI review fetch failed for %s: %s", asin, exc)
        time.sleep(1.5)
        return None


def _aggregate_aspects(all_aspects: list) -> list:
    """Aggregate aspects across competitors into a unified pain map."""
    merged = {}
    for asp in all_aspects:
        title = asp.get("title", "").strip().lower()
        if not title:
            continue
        if title not in merged:
            merged[title] = {
                "title": asp.get("title", "").strip(),
                "mentions_positive": 0,
                "mentions_negative": 0,
                "mentions_total": 0,
                "competitor_count": 0,
                "examples": [],
            }
        entry = merged[title]
        entry["mentions_positive"] += asp.get("mentions_positive", 0)
        entry["mentions_negative"] += asp.get("mentions_negative", 0)
        entry["mentions_total"] += asp.get("mentions_total", 0)
        entry["competitor_count"] += 1
        for ex in asp.get("examples", []):
            if ex and ex not in entry["examples"]:
                entry["examples"].append(ex)

    # Sort by total mentions descending
    return sorted(merged.values(), key=lambda x: x["mentions_total"], reverse=True)


def _synthesize_with_claude(aspects: list, product_name: str) -> str:
    """Use Claude to synthesize review insights into actionable product recommendations."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package is not installed. Run: pip install anthropic")

    from config import ANTHROPIC_API_KEY

    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured.")

    # Build prompt
    aspects_text = []
    for asp in aspects[:15]:  # Top 15 aspects
        aspects_text.append(
            f"- {asp['title']}: {asp['mentions_total']} mentions "
            f"(+{asp['mentions_positive']}/-{asp['mentions_negative']}), "
            f"across {asp['competitor_count']} competitors"
        )
        for ex in asp.get("examples", [])[:2]:
            aspects_text.append(f"  Example: \"{ex}\"")

    prompt = (
        f"You are analyzing competitor product reviews on Amazon for '{product_name}' "
        f"(a Verlumen Kids wooden toy). Here are the aggregated review aspects from competitor products:\n\n"
        + "\n".join(aspects_text)
        + "\n\nAnalyze these review insights and identify the top pain points, "
        "product improvement opportunities, and competitive advantages "
        "for Verlumen Kids. Call the submit_review_synthesis tool."
    )

    tool_def = {
        "name": "submit_review_synthesis",
        "description": "Submit structured review analysis synthesis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "top_pain_points": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "aspect": {"type": "string"},
                            "frequency": {"type": "integer"},
                            "insight": {"type": "string"},
                            "product_opportunity": {"type": "string"},
                        },
                        "required": ["aspect", "frequency", "insight", "product_opportunity"],
                    },
                },
                "product_recommendations": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "competitive_advantages": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "summary": {"type": "string"},
            },
            "required": ["top_pain_points", "product_recommendations", "summary"],
        },
    }

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        tools=[tool_def],
        tool_choice={"type": "tool", "name": "submit_review_synthesis"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_review_synthesis":
            return json.dumps(block.input)

    logger.warning("No tool_use block found in Claude synthesis response")
    return json.dumps({"summary": "Synthesis unavailable", "top_pain_points": [], "product_recommendations": []})
