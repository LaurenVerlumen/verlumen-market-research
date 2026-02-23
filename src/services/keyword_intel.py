"""PPC Keyword Intelligence: TF-IDF extraction, Amazon autocomplete, Claude campaign structuring."""
import logging
import re
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Noise words to filter from keyword results
_NOISE_WORDS = {
    "pack", "set", "count", "pcs", "piece", "pieces", "inch", "inches",
    "amp", "nbsp", "com", "amazon", "www",
}


def extract_keywords(competitors: list[dict], top_n: int = 30) -> list[dict]:
    """Extract keywords from competitor titles using TF-IDF.

    Returns list of dicts: [{"keyword": str, "score": float, "frequency": int, "competitor_count": int}]
    """
    from sklearn.feature_extraction.text import TfidfVectorizer

    titles = [c["title"] for c in competitors if c.get("title")]
    if len(titles) < 2:
        return []

    vectorizer = TfidfVectorizer(
        max_features=200,
        stop_words="english",
        ngram_range=(1, 3),
        min_df=2,
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9]+\b",
    )
    try:
        tfidf_matrix = vectorizer.fit_transform(titles)
    except ValueError:
        # Not enough terms after filtering
        return []

    feature_names = vectorizer.get_feature_names_out()
    # Sum TF-IDF scores across all documents
    summed_scores = tfidf_matrix.sum(axis=0).A1

    results = []
    for idx, term in enumerate(feature_names):
        # Filter noise words
        term_tokens = set(term.lower().split())
        if term_tokens & _NOISE_WORDS:
            continue
        if len(term) < 2:
            continue

        # Raw frequency: how many titles contain this term
        term_lower = term.lower()
        frequency = sum(1 for t in titles if term_lower in t.lower())

        results.append({
            "keyword": term,
            "score": round(float(summed_scores[idx]), 4),
            "frequency": frequency,
            "competitor_count": frequency,
        })

    # Sort by combined score (TF-IDF weighted, boosted by frequency)
    results.sort(key=lambda x: x["score"] * (1 + x["frequency"] * 0.1), reverse=True)
    return results[:top_n]


def get_amazon_suggestions(seed_keyword: str, api_key: Optional[str] = None) -> list[str]:
    """Get Amazon autocomplete suggestions for a seed keyword."""
    url = "https://completion.amazon.com/api/2017/suggestions"
    params = {"mid": "ATVPDKIKX0DER", "alias": "aps", "prefix": seed_keyword}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        suggestions = [s.get("value", "") for s in data.get("suggestions", []) if s.get("value")]
        time.sleep(0.5)  # Rate limit
        return suggestions
    except Exception as exc:
        logger.warning("Amazon autocomplete failed for '%s': %s", seed_keyword, exc)
        return []


def generate_ppc_campaign(product_id: int, db_session=None) -> dict:
    """Generate a PPC campaign structure for a product.

    Returns dict with: auto_seeds, manual_exact, negative_keywords,
    keyword_frequency, summary, total_keywords.
    """
    from src.models import get_session, Product, AmazonCompetitor, SearchSession

    own_session = db_session is None
    session = db_session or get_session()

    try:
        product = session.query(Product).filter(Product.id == product_id).first()
        if not product:
            return {"auto_seeds": [], "manual_exact": [], "negative_keywords": [],
                    "keyword_frequency": [], "summary": "Product not found.", "total_keywords": 0}

        # Get latest search session
        latest_session = (
            session.query(SearchSession)
            .filter(SearchSession.product_id == product_id)
            .order_by(SearchSession.created_at.desc())
            .first()
        )
        if not latest_session:
            return {"auto_seeds": [], "manual_exact": [], "negative_keywords": [],
                    "keyword_frequency": [], "summary": "No research data available.", "total_keywords": 0}

        comps = (
            session.query(AmazonCompetitor)
            .filter(AmazonCompetitor.search_session_id == latest_session.id)
            .order_by(AmazonCompetitor.position)
            .all()
        )

        comp_dicts = [
            {"title": c.title, "brand": c.brand, "price": c.price,
             "rating": c.rating, "review_count": c.review_count, "asin": c.asin}
            for c in comps
        ]

        # Extract TF-IDF keywords
        tfidf_keywords = extract_keywords(comp_dicts)

        # Get Amazon autocomplete suggestions
        seed = product.amazon_search_query or product.name
        suggestions = get_amazon_suggestions(seed)

        # Combine and deduplicate keywords
        all_keywords = set()
        for kw in tfidf_keywords:
            all_keywords.add(kw["keyword"].lower())
        for s in suggestions:
            all_keywords.add(s.lower())

        # Try Claude-powered campaign structuring
        from config import ANTHROPIC_API_KEY
        if ANTHROPIC_API_KEY:
            try:
                result = _generate_with_claude(product, tfidf_keywords, suggestions, ANTHROPIC_API_KEY)
                if result:
                    # Add keyword frequency data for chart
                    result["keyword_frequency"] = [
                        {"keyword": kw["keyword"], "count": kw["frequency"]}
                        for kw in tfidf_keywords[:15]
                    ]
                    result["total_keywords"] = len(all_keywords)
                    return result
            except Exception as exc:
                logger.warning("Claude PPC generation failed, using fallback: %s", exc)

        # Rule-based fallback
        return _generate_fallback(product, tfidf_keywords, suggestions, comp_dicts, all_keywords)

    finally:
        if own_session:
            session.close()


def _generate_with_claude(product, tfidf_keywords, suggestions, api_key):
    """Use Claude to structure PPC campaign keywords."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    tool_def = {
        "name": "submit_ppc_campaign",
        "description": "Submit structured PPC campaign keyword tiers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "auto_seeds": {"type": "array", "items": {"type": "object", "properties": {
                    "keyword": {"type": "string"},
                    "match_type": {"type": "string", "enum": ["broad", "phrase"]},
                    "relevance": {"type": "string", "enum": ["high", "medium", "low"]},
                    "rationale": {"type": "string"},
                }, "required": ["keyword", "match_type", "relevance", "rationale"]}},
                "manual_exact": {"type": "array", "items": {"type": "object", "properties": {
                    "keyword": {"type": "string"},
                    "match_type": {"type": "string", "enum": ["exact"]},
                    "relevance": {"type": "string", "enum": ["high", "medium"]},
                    "rationale": {"type": "string"},
                }, "required": ["keyword", "match_type", "relevance", "rationale"]}},
                "negative_keywords": {"type": "array", "items": {"type": "object", "properties": {
                    "keyword": {"type": "string"},
                    "reason": {"type": "string"},
                }, "required": ["keyword", "reason"]}},
                "campaign_summary": {"type": "string"},
            },
            "required": ["auto_seeds", "manual_exact", "negative_keywords", "campaign_summary"],
        },
    }

    category_name = product.category.name if product.category else "N/A"
    kw_lines = "\n".join(
        f"- {kw['keyword']} (score: {kw['score']:.3f}, in {kw['competitor_count']} competitors)"
        for kw in tfidf_keywords[:25]
    )
    sug_lines = "\n".join(f"- {s}" for s in suggestions[:15])

    prompt = f"""You are an Amazon PPC campaign strategist for Verlumen Kids, a wooden toy company.

PRODUCT: {product.name}
CATEGORY: {category_name}

EXTRACTED KEYWORDS FROM COMPETITORS (TF-IDF):
{kw_lines}

AMAZON AUTOCOMPLETE SUGGESTIONS:
{sug_lines}

Based on this data, generate a PPC campaign structure by calling submit_ppc_campaign.
- auto_seeds: 10-15 broad/phrase match keywords for automatic campaigns
- manual_exact: 5-10 high-relevance exact match keywords for manual campaigns
- negative_keywords: 5-8 irrelevant terms to exclude
Be specific to wooden/Montessori toys for children."""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        tools=[tool_def],
        tool_choice={"type": "tool", "name": "submit_ppc_campaign"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_ppc_campaign":
            data = block.input
            return {
                "auto_seeds": data.get("auto_seeds", []),
                "manual_exact": data.get("manual_exact", []),
                "negative_keywords": data.get("negative_keywords", []),
                "summary": data.get("campaign_summary", ""),
            }

    logger.warning("No tool_use block found in Claude PPC response")
    return None


def _generate_fallback(product, tfidf_keywords, suggestions, comp_dicts, all_keywords):
    """Rule-based fallback when Claude is not available."""
    # Auto seeds: keywords with frequency >= 3
    auto_seeds = [
        {"keyword": kw["keyword"], "match_type": "broad", "relevance": "medium",
         "rationale": f"Found in {kw['frequency']} competitor titles"}
        for kw in tfidf_keywords if kw["frequency"] >= 3
    ][:15]

    # Manual exact: top 10 by TF-IDF score
    manual_exact = [
        {"keyword": kw["keyword"], "match_type": "exact", "relevance": "high",
         "rationale": f"TF-IDF score: {kw['score']:.3f}"}
        for kw in tfidf_keywords[:10]
    ]

    # Negative keywords: brand names detected in competitor titles
    brands = set()
    for c in comp_dicts:
        brand = (c.get("brand") or "").strip()
        if brand and brand.lower() not in {"generic", "unknown", "n/a", ""}:
            brands.add(brand)
    negative_keywords = [
        {"keyword": b, "reason": "Competitor brand name"}
        for b in sorted(brands)
    ][:8]

    keyword_frequency = [
        {"keyword": kw["keyword"], "count": kw["frequency"]}
        for kw in tfidf_keywords[:15]
    ]

    return {
        "auto_seeds": auto_seeds,
        "manual_exact": manual_exact,
        "negative_keywords": negative_keywords,
        "keyword_frequency": keyword_frequency,
        "summary": f"Rule-based campaign for {product.name}: {len(auto_seeds)} auto seeds, "
                   f"{len(manual_exact)} exact match, {len(negative_keywords)} negatives.",
        "total_keywords": len(all_keywords),
    }
