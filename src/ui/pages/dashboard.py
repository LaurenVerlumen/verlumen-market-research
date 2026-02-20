"""Dashboard page -- market intelligence overview."""
from nicegui import ui
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from src.models import get_session, Category, Product, AmazonCompetitor, SearchSession
from src.services.utils import parse_bought
from src.services.viability_scorer import calculate_vvs
from src.ui.layout import build_layout
from src.ui.components.stats_card import stats_card


def _price_bucket(price: float) -> str:
    """Return the label for a price bucket."""
    if price < 5:
        return "$0-5"
    elif price < 10:
        return "$5-10"
    elif price < 15:
        return "$10-15"
    elif price < 20:
        return "$15-20"
    elif price < 30:
        return "$20-30"
    elif price < 50:
        return "$30-50"
    else:
        return "$50+"


_BUCKET_ORDER = ["$0-5", "$5-10", "$10-15", "$15-20", "$20-30", "$30-50", "$50+"]


def dashboard_page():
    """Render the main dashboard."""
    content = build_layout()

    with content:
        ui.label("Dashboard").classes("text-h5 font-bold")
        ui.label("Market intelligence overview.").classes("text-body2 text-secondary")

        # ------------------------------------------------------------------
        # Gather stats
        # ------------------------------------------------------------------
        session = get_session()
        try:
            cat_count = session.query(Category).count()
            product_count = session.query(Product).count()
            competitor_count = session.query(AmazonCompetitor).count()
            search_count = session.query(SearchSession).count()

            # Avg opportunity: average opportunity_score from the latest
            # search session per product (computed by CompetitionAnalyzer).
            from src.services.competition_analyzer import CompetitionAnalyzer as _CA
            _analyzer = _CA()

            # Get latest session ID per product in a single subquery
            from sqlalchemy import distinct
            latest_session_subq = (
                session.query(
                    SearchSession.product_id,
                    func.max(SearchSession.id).label("max_id"),
                )
                .group_by(SearchSession.product_id)
                .subquery()
            )
            latest_session_ids = [
                row.max_id for row in session.query(latest_session_subq.c.max_id).all()
            ]

            # Batch-load competitors for all latest sessions at once
            _opp_scores: list[float] = []
            if latest_session_ids:
                all_comps = (
                    session.query(AmazonCompetitor)
                    .filter(AmazonCompetitor.search_session_id.in_(latest_session_ids))
                    .all()
                )
                # Group by session
                comps_by_session: dict[int, list] = {}
                for c in all_comps:
                    comps_by_session.setdefault(c.search_session_id, []).append(c)

                for sid in latest_session_ids:
                    comps = comps_by_session.get(sid, [])
                    if comps:
                        comp_dicts = [
                            {
                                "price": c.price, "rating": c.rating,
                                "review_count": c.review_count,
                                "is_prime": c.is_prime, "badge": c.badge,
                                "bought_last_month": c.bought_last_month,
                            }
                            for c in comps
                        ]
                        analysis = _analyzer.analyze(comp_dicts)
                        _opp_scores.append(analysis["opportunity_score"])
            avg_opportunity = round(sum(_opp_scores) / len(_opp_scores), 1) if _opp_scores else None

            # Market size: sum(price * bought_last_month) for competitors
            # that have both values.  bought_last_month is stored as text
            # (e.g. "1K+"), so we parse it into an integer estimate.
            market_size_total = 0.0
            for c_row in (
                session.query(AmazonCompetitor.price, AmazonCompetitor.bought_last_month)
                .filter(AmazonCompetitor.price.isnot(None))
                .all()
            ):
                bought = parse_bought(c_row[1]) or 0
                if bought > 0:
                    market_size_total += c_row[0] * bought
            market_size = round(market_size_total, 0) if market_size_total > 0 else None

            # Prices for histogram
            prices = [
                row[0]
                for row in session.query(AmazonCompetitor.price)
                .filter(AmazonCompetitor.price.isnot(None))
                .all()
            ]

            # Category comparison data
            cat_stats = (
                session.query(
                    Category.name,
                    func.avg(SearchSession.avg_price),
                    func.avg(SearchSession.avg_rating),
                    func.count(AmazonCompetitor.id),
                )
                .join(Product, Product.category_id == Category.id)
                .join(SearchSession, SearchSession.product_id == Product.id)
                .outerjoin(AmazonCompetitor, AmazonCompetitor.product_id == Product.id)
                .group_by(Category.name)
                .all()
            )

            # Top opportunities: products with research, ordered by opportunity_score
            _top_query = (
                session.query(
                    Product.id,
                    Product.name,
                    Category.name.label("category_name"),
                    func.avg(AmazonCompetitor.price).label("avg_price"),
                    func.count(AmazonCompetitor.id).label("comp_count"),
                    func.avg(AmazonCompetitor.rating).label("avg_rating"),
                )
                .join(Category, Category.id == Product.category_id)
                .join(AmazonCompetitor, AmazonCompetitor.product_id == Product.id)
                .group_by(Product.id, Product.name, Category.name)
                .all()
            )
            # Build a product_id -> comps dict from already-loaded latest-session data
            _comps_by_product: dict[int, list] = {}
            if latest_session_ids:
                for sid in latest_session_ids:
                    for c in comps_by_session.get(sid, []):
                        _comps_by_product.setdefault(c.product_id, []).append(c)

            _top_with_score = []
            _vvs_by_product: dict[int, float] = {}
            for tp in _top_query:
                tp_comps = _comps_by_product.get(tp.id, [])
                if tp_comps:
                    _tp_dicts = [
                        {
                            "price": c.price, "rating": c.rating,
                            "review_count": c.review_count,
                            "is_prime": c.is_prime, "badge": c.badge,
                            "bought_last_month": c.bought_last_month,
                            "position": c.position,
                        }
                        for c in tp_comps
                    ]
                    _tp_analysis = _analyzer.analyze(_tp_dicts)
                    _top_with_score.append((tp, _tp_analysis["opportunity_score"]))
                    # Compute VVS for dashboard display
                    try:
                        # Look up the product for alibaba_cost
                        _tp_product = session.query(Product).filter(Product.id == tp.id).first()
                        _tp_alibaba = _tp_product.alibaba_price_min if _tp_product else None
                        _tp_vvs = calculate_vvs(_tp_product, _tp_dicts, alibaba_cost=_tp_alibaba)
                        _vvs_by_product[tp.id] = _tp_vvs.get("vvs_score", 0.0)
                    except Exception:
                        _vvs_by_product[tp.id] = 0.0
                else:
                    _top_with_score.append((tp, 0.0))
            _top_with_score.sort(key=lambda x: x[1], reverse=True)
            top_products = [item[0] for item in _top_with_score[:10]]

            # Recent searches with product name
            recent = (
                session.query(SearchSession)
                .options(joinedload(SearchSession.product))
                .order_by(SearchSession.created_at.desc())
                .limit(5)
                .all()
            )
        finally:
            session.close()

        has_research = search_count > 0 and competitor_count > 0

        # ------------------------------------------------------------------
        # KPI row
        # ------------------------------------------------------------------
        with ui.row().classes("gap-4 flex-wrap"):
            stats_card("Categories", str(cat_count), icon="category", color="primary")
            stats_card("Products", str(product_count), icon="inventory_2", color="accent")
            stats_card("Competitors", str(competitor_count), icon="groups", color="positive")
            stats_card("Searches", str(search_count), icon="search", color="secondary")
            if avg_opportunity is not None:
                stats_card("Avg Opportunity", f"{avg_opportunity}/100", icon="trending_up", color="warning")
            if market_size is not None:
                stats_card("Market Size", f"${market_size:,.0f}", icon="attach_money", color="positive")

        # ------------------------------------------------------------------
        # Charts row (only when research data exists)
        # ------------------------------------------------------------------
        if has_research:
            with ui.row().classes("w-full gap-4 flex-wrap"):
                # --- Price Distribution Chart ---
                with ui.card().classes("flex-1 min-w-[400px] p-4"):
                    bucket_counts = {b: 0 for b in _BUCKET_ORDER}
                    for p in prices:
                        bucket_counts[_price_bucket(p)] += 1
                    buckets = _BUCKET_ORDER
                    counts = [bucket_counts[b] for b in buckets]

                    ui.echart({
                        'title': {'text': 'Amazon Price Distribution', 'left': 'center',
                                  'textStyle': {'fontSize': 14}},
                        'tooltip': {'trigger': 'axis'},
                        'xAxis': {'type': 'category', 'data': buckets,
                                  'axisLabel': {'rotate': 30}},
                        'yAxis': {'type': 'value', 'name': 'Products'},
                        'series': [{
                            'data': counts,
                            'type': 'bar',
                            'color': '#A08968',
                            'itemStyle': {'borderRadius': [4, 4, 0, 0]},
                        }],
                        'grid': {'bottom': 60},
                    }).classes("w-full h-64")

                # --- Category Comparison Chart ---
                if cat_stats:
                    with ui.card().classes("flex-1 min-w-[400px] p-4"):
                        cat_names = [row[0] for row in cat_stats]
                        avg_prices = [round(row[1], 2) if row[1] else 0 for row in cat_stats]
                        avg_ratings = [round(row[2], 1) if row[2] else 0 for row in cat_stats]
                        comp_counts = [row[3] or 0 for row in cat_stats]

                        ui.echart({
                            'title': {'text': 'Category Comparison', 'left': 'center',
                                      'textStyle': {'fontSize': 14}},
                            'tooltip': {'trigger': 'axis'},
                            'legend': {'data': ['Avg Price ($)', 'Avg Rating', 'Competitors'],
                                       'bottom': 0},
                            'xAxis': {'type': 'category', 'data': cat_names,
                                      'axisLabel': {'rotate': 30, 'interval': 0}},
                            'yAxis': [
                                {'type': 'value', 'name': 'Price ($) / Rating', 'position': 'left'},
                                {'type': 'value', 'name': 'Count', 'position': 'right'},
                            ],
                            'series': [
                                {'name': 'Avg Price ($)', 'data': avg_prices, 'type': 'bar',
                                 'color': '#A08968'},
                                {'name': 'Avg Rating', 'data': avg_ratings, 'type': 'bar',
                                 'color': '#6B8E68'},
                                {'name': 'Competitors', 'data': comp_counts, 'type': 'bar',
                                 'yAxisIndex': 1, 'color': '#68839E'},
                            ],
                            'grid': {'bottom': 80},
                        }).classes("w-full h-64")

        # ------------------------------------------------------------------
        # Top Opportunities table (or Getting Started tips)
        # ------------------------------------------------------------------
        if has_research and top_products:
            with ui.card().classes("w-full p-4"):
                ui.label("Top Opportunities").classes("text-subtitle1 font-bold mb-2")
                columns = [
                    {"name": "product", "label": "Product", "field": "product", "align": "left"},
                    {"name": "category", "label": "Category", "field": "category", "align": "left"},
                    {"name": "vvs", "label": "VVS", "field": "vvs", "align": "center", "sortable": True},
                    {"name": "avg_price", "label": "Avg Amazon Price", "field": "avg_price", "align": "right"},
                    {"name": "competitors", "label": "Competitors", "field": "competitors", "align": "right"},
                    {"name": "avg_rating", "label": "Avg Rating", "field": "avg_rating", "align": "right"},
                ]
                rows = []
                for tp in top_products:
                    vvs_val = _vvs_by_product.get(tp.id, 0.0)
                    rows.append({
                        "product": tp.name,
                        "category": tp.category_name,
                        "vvs": f"{vvs_val:.1f}" if vvs_val > 0 else "-",
                        "avg_price": f"${tp.avg_price:.2f}" if tp.avg_price else "N/A",
                        "competitors": tp.comp_count,
                        "avg_rating": f"{tp.avg_rating:.1f}" if tp.avg_rating else "N/A",
                    })
                ui.table(columns=columns, rows=rows, row_key="product").props(
                    "flat bordered dense"
                ).classes("w-full")
        else:
            # Quick-start tips when no research data exists
            with ui.card().classes("w-full p-4"):
                ui.label("Getting Started").classes("text-subtitle1 font-bold mb-2")
                with ui.column().classes("gap-1"):
                    ui.label("1. Go to Import Data to upload your Verlumen Excel spreadsheet.").classes("text-body2")
                    ui.label("2. Review imported products on the Products page.").classes("text-body2")
                    ui.label("3. Use Amazon Search to find competitors for each product.").classes("text-body2")
                    ui.label("4. Check the Analysis page for competition and opportunity scores.").classes("text-body2")
                    ui.label("5. Export results to Excel from the Export page.").classes("text-body2")

        # ------------------------------------------------------------------
        # Recent Searches (enhanced with product name)
        # ------------------------------------------------------------------
        if recent:
            with ui.card().classes("w-full p-4"):
                ui.label("Recent Searches").classes("text-subtitle1 font-bold mb-2")
                columns = [
                    {"name": "product", "label": "Product", "field": "product", "align": "left"},
                    {"name": "query", "label": "Query", "field": "query", "align": "left"},
                    {"name": "results", "label": "Results", "field": "results", "align": "right"},
                    {"name": "date", "label": "Date", "field": "date", "align": "left"},
                ]
                rows = []
                for s in recent:
                    rows.append({
                        "product": s.product.name if s.product else "—",
                        "query": s.search_query,
                        "results": (s.organic_results or 0) + (s.sponsored_results or 0),
                        "date": s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "",
                    })
                ui.table(columns=columns, rows=rows, row_key="query").props("flat bordered dense")
