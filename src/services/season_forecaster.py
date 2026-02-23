"""Seasonal demand forecasting using Google Trends + BSR history."""
import logging
import time
from datetime import datetime

from sqlalchemy import func

from src.models import get_session, Product, AmazonCompetitor, SearchSession

logger = logging.getLogger(__name__)

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def get_seasonal_data(keyword: str, timeframe: str = "today 5-y") -> dict | None:
    """Fetch Google Trends interest-over-time data for *keyword*.

    Returns ``{"interest_over_time": [...], "error": str|None}`` or ``None``
    if pytrends is not installed.
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        logger.warning("pytrends not installed – skipping Google Trends")
        return None

    try:
        time.sleep(2)  # be polite to Google
        pytrends = TrendReq(hl="en-US", tz=360)
        pytrends.build_payload([keyword], timeframe=timeframe)
        df = pytrends.interest_over_time()
        if df.empty:
            return {"interest_over_time": [], "error": "No data returned"}
        points = [
            {"date": idx.strftime("%Y-%m-%d"), "value": int(row[keyword])}
            for idx, row in df.iterrows()
            if keyword in row
        ]
        return {"interest_over_time": points, "error": None}
    except Exception as exc:
        logger.warning("Google Trends request failed: %s", exc)
        return {"interest_over_time": [], "error": str(exc)}


def _compute_bsr_history(product_id: int, session) -> list[dict]:
    """Return average BSR per search session for *product_id*."""
    rows = (
        session.query(
            SearchSession.id,
            SearchSession.created_at,
            func.avg(AmazonCompetitor.bsr_rank).label("avg_bsr"),
            func.count(AmazonCompetitor.id).label("cnt"),
        )
        .join(AmazonCompetitor, AmazonCompetitor.search_session_id == SearchSession.id)
        .filter(
            SearchSession.product_id == product_id,
            AmazonCompetitor.bsr_rank.isnot(None),
        )
        .group_by(SearchSession.id)
        .order_by(SearchSession.created_at)
        .all()
    )
    return [
        {
            "date": r.created_at.strftime("%Y-%m-%d") if r.created_at else "",
            "avg_bsr": round(float(r.avg_bsr), 1),
            "competitor_count": r.cnt,
        }
        for r in rows
    ]


def forecast_demand(product_id: int, db_session=None) -> dict:
    """Build a seasonal demand forecast for *product_id*.

    Combines Google Trends interest-over-time (if available) with BSR
    history from search sessions.  Returns a dict suitable for the UI
    rendering layer.
    """
    own_session = db_session is None
    session = db_session or get_session()
    try:
        product = session.query(Product).get(product_id)
        if product is None:
            return _empty_result("Product not found")

        keyword = product.amazon_search_query or product.name
        bsr_history = _compute_bsr_history(product_id, session)
        trends_data = get_seasonal_data(keyword)

        trends_available = (
            trends_data is not None
            and len(trends_data.get("interest_over_time", [])) >= 104
        )

        # ---- seasonal decomposition via Google Trends --------------------
        monthly_demand_index: list[dict] = []
        peak_months: list[str] = []
        seasonality_strength: float = 0.0
        forecast_12m: list[dict] = []

        if trends_available:
            import pandas as pd
            from statsmodels.tsa.seasonal import seasonal_decompose

            points = trends_data["interest_over_time"]
            dates = [p["date"] for p in points]
            values = [p["value"] for p in points]

            series = pd.Series(values, index=pd.DatetimeIndex(dates))
            series = series.asfreq("W").interpolate()
            result = seasonal_decompose(series, model="additive", period=52)
            seasonal = result.seasonal

            # Monthly demand index (average weekly seasonal values per month)
            monthly_vals: dict[int, list[float]] = {m: [] for m in range(1, 13)}
            for ts, val in seasonal.items():
                monthly_vals[ts.month].append(val)

            raw_monthly = {m: sum(v) / len(v) for m, v in monthly_vals.items() if v}
            mean_val = sum(raw_monthly.values()) / len(raw_monthly) if raw_monthly else 1.0
            if mean_val == 0:
                mean_val = 1.0
            # Normalise so average = 100
            norm = {m: (v / mean_val) * 100 for m, v in raw_monthly.items()}

            for m in range(1, 13):
                idx_val = round(norm.get(m, 100.0), 1)
                is_peak = idx_val > 120
                monthly_demand_index.append(
                    {"month": MONTH_NAMES[m - 1], "index": idx_val, "is_peak": is_peak}
                )
                if is_peak:
                    peak_months.append(MONTH_NAMES[m - 1])

            vals = [e["index"] for e in monthly_demand_index]
            max_v, min_v, mean_v = max(vals), min(vals), sum(vals) / len(vals)
            seasonality_strength = min(max((max_v - min_v) / mean_v, 0.0), 1.0)

            # 12-month rolling forecast starting from current month
            now = datetime.utcnow()
            for offset in range(12):
                m = ((now.month - 1 + offset) % 12) + 1
                y = now.year + ((now.month - 1 + offset) // 12)
                forecast_12m.append({
                    "month": f"{MONTH_NAMES[m - 1][:3]} {y}",
                    "predicted_index": round(norm.get(m, 100.0), 1),
                })
        else:
            # Fallback: flat index
            for m in range(1, 13):
                monthly_demand_index.append(
                    {"month": MONTH_NAMES[m - 1], "index": 100.0, "is_peak": False}
                )
            now = datetime.utcnow()
            for offset in range(12):
                m = ((now.month - 1 + offset) % 12) + 1
                y = now.year + ((now.month - 1 + offset) // 12)
                forecast_12m.append({
                    "month": f"{MONTH_NAMES[m - 1][:3]} {y}",
                    "predicted_index": 100.0,
                })

        # ---- launch recommendation text ----------------------------------
        launch_recommendation = _build_recommendation(
            product.name, peak_months, trends_available, monthly_demand_index,
        )

        return {
            "monthly_demand_index": monthly_demand_index,
            "peak_months": peak_months,
            "launch_recommendation": launch_recommendation,
            "trends_available": trends_available,
            "bsr_history": bsr_history,
            "forecast_12m": forecast_12m,
            "seasonality_strength": seasonality_strength,
            "keyword_used": keyword,
        }
    finally:
        if own_session:
            session.close()


def _build_recommendation(
    product_name: str,
    peak_months: list[str],
    trends_available: bool,
    monthly_demand_index: list[dict],
) -> str:
    """Return a human-readable launch-window recommendation."""
    if not trends_available:
        return (
            f"Google Trends data unavailable for \"{product_name}\". "
            "Consider researching peak demand periods manually or running "
            "additional search sessions to build BSR history."
        )
    if not peak_months:
        return (
            f"\"{product_name}\" shows relatively flat demand year-round. "
            "No strong seasonal peak detected — you can launch any time."
        )

    # Find the month with the highest index
    best = max(monthly_demand_index, key=lambda e: e["index"])
    best_month_idx = MONTH_NAMES.index(best["month"])  # 0-based

    # Recommend shipping FBA 6-8 weeks before peak
    ship_month_idx = (best_month_idx - 2) % 12  # ~8 weeks before
    ship_month = MONTH_NAMES[ship_month_idx]

    peak_str = ", ".join(peak_months)
    return (
        f"Ship FBA by {ship_month} to capture {best['month']} demand. "
        f"\"{product_name}\" shows strongest demand in {peak_str}."
    )


def _empty_result(message: str) -> dict:
    return {
        "monthly_demand_index": [],
        "peak_months": [],
        "launch_recommendation": message,
        "trends_available": False,
        "bsr_history": [],
        "forecast_12m": [],
        "seasonality_strength": 0.0,
        "keyword_used": "",
    }
