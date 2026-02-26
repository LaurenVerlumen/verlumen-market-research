"""LLM Listing Autopsy — feed competitor listings into Claude for structured competitive analysis."""
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Default empty autopsy structure
_EMPTY_AUTOPSY = {
    "gaps": [],
    "winning_angles": [],
    "missing_claims": [],
    "messaging_framework": "",
}


def analyze_listings(product_name: str, competitors: list[dict]) -> dict:
    """Run a Listing Autopsy on competitor data using Claude AI.

    Parameters
    ----------
    product_name : str
        The name/query of the product being researched.
    competitors : list[dict]
        List of competitor dicts with keys: title, brand, price, rating,
        review_count, bought_last_month, badge, position, asin, monthly_sales,
        monthly_revenue.

    Returns
    -------
    dict with keys: gaps, winning_angles, missing_claims, messaging_framework.

    Raises
    ------
    RuntimeError
        If the Anthropic API key is missing or the SDK is not installed.
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package is not installed. Run: pip install anthropic")

    from config import ANTHROPIC_API_KEY

    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured. Set it in Settings.")

    if not competitors:
        raise RuntimeError("No competitor data available for analysis.")

    prompt = _build_prompt(product_name, competitors)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    tool_def = {
        "name": "submit_listing_autopsy",
        "description": "Submit a structured Listing Autopsy analysis of competitor listings.",
        "input_schema": {
            "type": "object",
            "properties": {
                "gaps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "gap": {"type": "string", "description": "A specific gap or opportunity found in the competitive landscape."},
                            "evidence": {"type": "string", "description": "Brief evidence from competitor data supporting this gap."},
                            "priority": {"type": "string", "enum": ["high", "medium", "low"], "description": "Priority level of this gap."},
                        },
                        "required": ["gap", "evidence", "priority"],
                    },
                    "description": "3-6 specific gaps or opportunities in the competitive landscape that the seller can exploit.",
                },
                "winning_angles": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "angle": {"type": "string", "description": "A winning positioning angle or strategy."},
                            "rationale": {"type": "string", "description": "Why this angle works based on competitor analysis."},
                        },
                        "required": ["angle", "rationale"],
                    },
                    "description": "3-5 winning positioning angles or strategies based on what top performers are doing right.",
                },
                "missing_claims": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-6 specific claims, certifications, or selling points that competitors are NOT mentioning but could differentiate a new listing (e.g., 'ASTM certified', 'sensory play', 'travel-friendly').",
                },
                "messaging_framework": {
                    "type": "string",
                    "description": "A 3-5 sentence messaging framework / positioning statement that synthesizes the gaps and angles into an actionable listing strategy for the seller.",
                },
            },
            "required": ["gaps", "winning_angles", "missing_claims", "messaging_framework"],
        },
    }

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        tools=[tool_def],
        tool_choice={"type": "tool", "name": "submit_listing_autopsy"},
        messages=[{"role": "user", "content": prompt}],
    )

    # Extract tool use result
    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_listing_autopsy":
            autopsy = block.input
            result = dict(_EMPTY_AUTOPSY)
            result.update(autopsy)
            return result

    logger.warning("No tool_use block found in Claude response for listing autopsy")
    return dict(_EMPTY_AUTOPSY)


def _build_prompt(product_name: str, competitors: list[dict]) -> str:
    """Build the analysis prompt from product name and competitor data."""
    parts = [
        "You are an expert Amazon listing strategist for Verlumen Kids, a wooden toy brand.",
        "Analyze the following competitor listings and produce a Listing Autopsy:",
        "- Identify gaps in the market that a new listing can exploit",
        "- Determine winning angles from top-performing listings",
        "- Find claims or selling points that competitors are missing",
        "- Create an actionable messaging framework",
        "",
        f"PRODUCT QUERY: {product_name}",
        f"TOTAL COMPETITORS ANALYZED: {len(competitors)}",
        "",
        "TOP COMPETITOR LISTINGS:",
        "=" * 50,
    ]

    # Include up to 20 competitors (sorted by position if available)
    sorted_comps = sorted(
        competitors,
        key=lambda c: c.get("position") or 999,
    )[:20]

    for i, c in enumerate(sorted_comps, 1):
        parts.append(f"\n--- Competitor #{i} ---")
        if c.get("title"):
            parts.append(f"Title: {c['title']}")
        if c.get("brand"):
            parts.append(f"Brand: {c['brand']}")
        if c.get("price") is not None:
            parts.append(f"Price: ${c['price']:.2f}")
        if c.get("rating") is not None:
            parts.append(f"Rating: {c['rating']:.1f}")
        if c.get("review_count") is not None:
            parts.append(f"Reviews: {c['review_count']:,}")
        if c.get("bought_last_month"):
            parts.append(f"Bought Last Month: {c['bought_last_month']}")
        if c.get("monthly_sales"):
            parts.append(f"Est. Monthly Sales: {c['monthly_sales']:,}")
        if c.get("monthly_revenue"):
            parts.append(f"Est. Monthly Revenue: ${c['monthly_revenue']:,.0f}")
        if c.get("badge"):
            parts.append(f"Badge: {c['badge']}")
        if c.get("position") is not None:
            parts.append(f"Search Position: #{c['position']}")

    parts.append("")
    parts.append("=" * 50)
    parts.append("")
    parts.append(
        "Based on this competitive landscape, perform a Listing Autopsy by calling "
        "the submit_listing_autopsy tool. Be specific, actionable, and grounded in "
        "the data above. Focus on insights a wooden toy seller can immediately act on. "
        "Example insight: 'All top sellers mention ASTM certification and age 3+ but "
        "none mention sensory play -- that is your opening.'"
    )

    return "\n".join(parts)
