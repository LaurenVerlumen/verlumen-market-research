"""Market events detection -- review velocity anomalies and competitor changes."""
from datetime import datetime

from sqlalchemy import desc

from src.models import get_session, SearchSession, AmazonCompetitor, Product


def detect_events(product_id: int, db_session=None) -> list[dict]:
    """Compare the latest 2 search sessions for a product and detect market events.

    Returns a list of event dicts:
    [{type, asin, title, detail, severity, detected_at}]

    If fewer than 2 sessions exist, returns an empty list.
    """
    own_session = db_session is None
    session = db_session or get_session()
    try:
        sessions = (
            session.query(SearchSession)
            .filter(SearchSession.product_id == product_id)
            .order_by(desc(SearchSession.created_at))
            .limit(2)
            .all()
        )

        if len(sessions) < 2:
            return []

        current_sess = sessions[0]
        previous_sess = sessions[1]

        current_comps = (
            session.query(AmazonCompetitor)
            .filter(AmazonCompetitor.search_session_id == current_sess.id)
            .all()
        )
        previous_comps = (
            session.query(AmazonCompetitor)
            .filter(AmazonCompetitor.search_session_id == previous_sess.id)
            .all()
        )

        current_by_asin = {c.asin: c for c in current_comps}
        previous_by_asin = {c.asin: c for c in previous_comps}

        current_asins = set(current_by_asin.keys())
        previous_asins = set(previous_by_asin.keys())

        new_asins = current_asins - previous_asins
        gone_asins = previous_asins - current_asins
        stable_asins = current_asins & previous_asins

        detected_at = current_sess.created_at or datetime.utcnow()
        events: list[dict] = []

        # Calculate days between sessions for velocity threshold
        days_between = 30  # default
        if current_sess.created_at and previous_sess.created_at:
            delta = current_sess.created_at - previous_sess.created_at
            days_between = max(delta.days, 1)

        # New entrants with >20 reviews
        for asin in new_asins:
            comp = current_by_asin[asin]
            if comp.review_count is not None and comp.review_count > 20:
                events.append({
                    "type": "new_entrant",
                    "asin": asin,
                    "title": comp.title or asin,
                    "detail": f"New competitor with {comp.review_count} reviews",
                    "severity": "high",
                    "detected_at": detected_at,
                })

        # Competitor exits
        for asin in gone_asins:
            comp = previous_by_asin[asin]
            events.append({
                "type": "competitor_exit",
                "asin": asin,
                "title": comp.title or asin,
                "detail": "Competitor no longer in search results",
                "severity": "low",
                "detected_at": detected_at,
            })

        # Review velocity changes for stable ASINs
        for asin in stable_asins:
            cur = current_by_asin[asin]
            prev = previous_by_asin[asin]

            if cur.review_count is None or prev.review_count is None:
                continue

            review_delta = cur.review_count - prev.review_count

            # Launch surge: >50 new reviews in <30 days
            if review_delta > 50 and days_between < 30:
                events.append({
                    "type": "launch_surge",
                    "asin": asin,
                    "title": cur.title or asin,
                    "detail": f"+{review_delta} reviews in {days_between} days",
                    "severity": "high",
                    "detected_at": detected_at,
                })

            # Decline: velocity drop >20% from a meaningful base (>100 reviews)
            if prev.review_count >= 100 and review_delta < 0:
                pct_drop = abs(review_delta) / prev.review_count
                if pct_drop >= 0.20:
                    events.append({
                        "type": "decline",
                        "asin": asin,
                        "title": cur.title or asin,
                        "detail": f"{review_delta} reviews ({pct_drop:.0%} drop)",
                        "severity": "medium",
                        "detected_at": detected_at,
                    })

        return events
    finally:
        if own_session:
            session.close()


def get_all_recent_events(db_session=None, limit: int = 20) -> list[dict]:
    """Detect events across all products and return the most recent ones.

    Each event includes product_id and product_name.
    """
    own_session = db_session is None
    session = db_session or get_session()
    try:
        products = session.query(Product.id, Product.name).all()

        all_events: list[dict] = []
        for pid, pname in products:
            product_events = detect_events(pid, db_session=session)
            for ev in product_events:
                ev["product_id"] = pid
                ev["product_name"] = pname
            all_events.extend(product_events)

        # Sort by detected_at descending
        all_events.sort(
            key=lambda e: e.get("detected_at") or datetime.min,
            reverse=True,
        )

        return all_events[:limit]
    finally:
        if own_session:
            session.close()
