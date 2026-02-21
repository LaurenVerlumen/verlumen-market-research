"""Competitor trend tracking -- compares recent search sessions to detect trends."""
from sqlalchemy import desc

from src.models import get_session, SearchSession, AmazonCompetitor


def compute_trends(product_id: int) -> dict | None:
    """Compare the 2 most recent search sessions for a product.

    Returns None if fewer than 2 sessions exist.
    Returns dict with:
    - session_current: {id, date, avg_price, avg_rating, competitor_count}
    - session_previous: {id, date, avg_price, avg_rating, competitor_count}
    - deltas: {avg_price_change, avg_rating_change, competitor_count_change}
    - competitor_trends: {asin: {status, price_delta, rating_delta, review_delta}}
    - timeline: [{session_id, date, avg_price, avg_rating, competitor_count}]
    """
    with get_session() as session:
        # All sessions for this product, newest first
        all_sessions = (
            session.query(SearchSession)
            .filter(SearchSession.product_id == product_id)
            .order_by(desc(SearchSession.created_at))
            .all()
        )

        if len(all_sessions) < 2:
            return None

        current_sess = all_sessions[0]
        previous_sess = all_sessions[1]

        # Load competitors for each session
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

        # Build ASIN-keyed dicts
        current_by_asin = {c.asin: c for c in current_comps}
        previous_by_asin = {c.asin: c for c in previous_comps}

        current_asins = set(current_by_asin.keys())
        previous_asins = set(previous_by_asin.keys())

        new_asins = current_asins - previous_asins
        gone_asins = previous_asins - current_asins
        stable_asins = current_asins & previous_asins

        # Build competitor_trends
        competitor_trends = {}

        for asin in new_asins:
            competitor_trends[asin] = {
                "status": "new",
                "price_delta": None,
                "rating_delta": None,
                "review_delta": None,
            }

        for asin in gone_asins:
            competitor_trends[asin] = {
                "status": "gone",
                "price_delta": None,
                "rating_delta": None,
                "review_delta": None,
            }

        for asin in stable_asins:
            cur = current_by_asin[asin]
            prev = previous_by_asin[asin]

            price_delta = None
            if cur.price is not None and prev.price is not None:
                price_delta = round(cur.price - prev.price, 2)

            rating_delta = None
            if cur.rating is not None and prev.rating is not None:
                rating_delta = round(cur.rating - prev.rating, 2)

            review_delta = None
            if cur.review_count is not None and prev.review_count is not None:
                review_delta = cur.review_count - prev.review_count

            competitor_trends[asin] = {
                "status": "stable",
                "price_delta": price_delta,
                "rating_delta": rating_delta,
                "review_delta": review_delta,
            }

        # Session-level summaries
        def _session_summary(sess, comps):
            return {
                "id": sess.id,
                "date": sess.created_at.isoformat() if sess.created_at else None,
                "avg_price": sess.avg_price,
                "avg_rating": sess.avg_rating,
                "competitor_count": len(comps),
            }

        session_current = _session_summary(current_sess, current_comps)
        session_previous = _session_summary(previous_sess, previous_comps)

        # Aggregate deltas
        avg_price_change = None
        if current_sess.avg_price is not None and previous_sess.avg_price is not None:
            avg_price_change = round(current_sess.avg_price - previous_sess.avg_price, 2)

        avg_rating_change = None
        if current_sess.avg_rating is not None and previous_sess.avg_rating is not None:
            avg_rating_change = round(current_sess.avg_rating - previous_sess.avg_rating, 2)

        competitor_count_change = len(current_comps) - len(previous_comps)

        deltas = {
            "avg_price_change": avg_price_change,
            "avg_rating_change": avg_rating_change,
            "competitor_count_change": competitor_count_change,
        }

        # Build timeline from ALL sessions (oldest first for charts)
        timeline = []
        for sess in reversed(all_sessions):
            comp_count = (
                session.query(AmazonCompetitor)
                .filter(AmazonCompetitor.search_session_id == sess.id)
                .count()
            )
            timeline.append({
                "session_id": sess.id,
                "date": sess.created_at.isoformat() if sess.created_at else None,
                "avg_price": sess.avg_price,
                "avg_rating": sess.avg_rating,
                "competitor_count": comp_count,
            })

        return {
            "session_current": session_current,
            "session_previous": session_previous,
            "deltas": deltas,
            "competitor_trends": competitor_trends,
            "timeline": timeline,
        }
