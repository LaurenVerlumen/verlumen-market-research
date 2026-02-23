"""AI Go-to-Market Brief generator using Anthropic Claude API."""
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Default empty brief structure
_EMPTY_BRIEF = {
    "launch_price": None,
    "rationale": "",
    "headline_angles": [],
    "risk_flags": [],
    "milestones_90day": [],
    "market_summary": "",
}


def generate_gtm_brief(product_data: dict) -> dict:
    """Generate a Go-to-Market brief for a product using Claude AI.

    Parameters
    ----------
    product_data : dict
        Keys: name, category, vvs (dict from calculate_vvs), pricing (dict from
        recommend_pricing), demand (dict from estimate_demand), competitor_count,
        avg_price, avg_rating, alibaba_cost.

    Returns
    -------
    dict with keys: launch_price, rationale, headline_angles, risk_flags,
    milestones_90day, market_summary.

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

    prompt = _build_prompt(product_data)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    tool_def = {
        "name": "submit_gtm_brief",
        "description": "Submit a structured Go-to-Market brief for the product.",
        "input_schema": {
            "type": "object",
            "properties": {
                "launch_price": {
                    "type": "number",
                    "description": "Recommended launch price in USD.",
                },
                "rationale": {
                    "type": "string",
                    "description": "2-3 sentence rationale for the recommended launch price and positioning strategy.",
                },
                "headline_angles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-5 listing headline angles / value propositions for the Amazon listing.",
                },
                "risk_flags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-4 key risks or concerns for this product launch.",
                },
                "milestones_90day": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "4-6 concrete milestones for the first 90 days after launch.",
                },
                "market_summary": {
                    "type": "string",
                    "description": "A concise 2-3 sentence summary of the market opportunity.",
                },
            },
            "required": [
                "launch_price",
                "rationale",
                "headline_angles",
                "risk_flags",
                "milestones_90day",
                "market_summary",
            ],
        },
    }

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        tools=[tool_def],
        tool_choice={"type": "tool", "name": "submit_gtm_brief"},
        messages=[{"role": "user", "content": prompt}],
    )

    # Extract tool use result
    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_gtm_brief":
            brief = block.input
            # Ensure all expected keys are present
            result = dict(_EMPTY_BRIEF)
            result.update(brief)
            return result

    logger.warning("No tool_use block found in Claude response")
    return dict(_EMPTY_BRIEF)


def _build_prompt(data: dict) -> str:
    """Build the system prompt from product data."""
    parts = [
        "You are an Amazon product launch strategist for Verlumen Kids, a wooden toy company.",
        "Analyze the following product data and generate a Go-to-Market brief.",
        "",
        f"PRODUCT: {data.get('name', 'Unknown')}",
        f"CATEGORY: {data.get('category', 'N/A')}",
    ]

    # VVS scores
    vvs = data.get("vvs")
    if vvs and vvs.get("vvs_score"):
        parts.append("")
        parts.append(f"VIABILITY SCORE (VVS): {vvs['vvs_score']}/10 - {vvs.get('verdict', 'N/A')}")
        dims = vvs.get("dimensions", {})
        for dim_name, dim_data in dims.items():
            parts.append(f"  {dim_name}: {dim_data.get('score', 'N/A')}/10 - {dim_data.get('details', '')}")
        if vvs.get("recommendation"):
            parts.append(f"  Recommendation: {vvs['recommendation']}")

    # Pricing strategies
    pricing = data.get("pricing")
    if pricing and pricing.get("strategies"):
        parts.append("")
        parts.append("PRICING ANALYSIS:")
        for strategy_name, strategy in pricing["strategies"].items():
            margin_info = ""
            if "margin_percent" in strategy:
                margin_info = f" (margin: {strategy['margin_percent']}%)"
            parts.append(
                f"  {strategy_name}: ${strategy.get('price', 0):.2f}{margin_info}"
                f" - est. {strategy.get('estimated_monthly_units', 0)} units/mo"
            )
        stats = pricing.get("summary_stats", {})
        if stats:
            parts.append(f"  Price range: ${stats.get('min', 0):.2f} - ${stats.get('max', 0):.2f}")
        gaps = pricing.get("price_gap_opportunities", [])
        if gaps:
            parts.append("  Price gaps: " + ", ".join(
                f"${g['low']:.2f}-${g['high']:.2f}" for g in gaps[:3]
            ))

    # Demand
    demand = data.get("demand")
    if demand and demand.get("total_monthly_units"):
        parts.append("")
        parts.append("DEMAND ESTIMATES:")
        parts.append(f"  Total monthly units: {demand['total_monthly_units']:,}")
        parts.append(f"  Total monthly revenue: ${demand.get('total_monthly_revenue', 0):,.0f}")
        parts.append(f"  Market size: {demand.get('market_size_category', 'N/A')}")
        parts.append(f"  Confidence: {demand.get('demand_confidence', 0):.0f}%")

    # Competitor stats
    parts.append("")
    parts.append("COMPETITOR LANDSCAPE:")
    parts.append(f"  Competitors analyzed: {data.get('competitor_count', 0)}")
    if data.get("avg_price"):
        parts.append(f"  Average price: ${data['avg_price']:.2f}")
    if data.get("avg_rating"):
        parts.append(f"  Average rating: {data['avg_rating']:.1f}")

    # Alibaba cost
    if data.get("alibaba_cost"):
        parts.append(f"  Alibaba unit cost: ${data['alibaba_cost']:.2f}")

    parts.append("")
    parts.append(
        "Based on this data, generate a Go-to-Market brief by calling the submit_gtm_brief tool. "
        "Be specific and actionable. Tailor advice to a wooden toy brand selling on Amazon."
    )

    return "\n".join(parts)
