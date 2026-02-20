"""Dashboard page -- overview of the research project."""
from nicegui import ui

from src.models import get_session, Category, Product, AmazonCompetitor, SearchSession
from src.ui.layout import build_layout
from src.ui.components.stats_card import stats_card


def dashboard_page():
    """Render the main dashboard."""
    content = build_layout()

    with content:
        ui.label("Dashboard").classes("text-h5 font-bold")
        ui.label("Overview of your market research data.").classes("text-body2 text-secondary")

        # Gather stats
        session = get_session()
        try:
            cat_count = session.query(Category).count()
            product_count = session.query(Product).count()
            competitor_count = session.query(AmazonCompetitor).count()
            search_count = session.query(SearchSession).count()
        finally:
            session.close()

        # KPI row
        with ui.row().classes("gap-4 flex-wrap"):
            stats_card("Categories", str(cat_count), icon="category", color="primary")
            stats_card("Products", str(product_count), icon="inventory_2", color="accent")
            stats_card("Competitors", str(competitor_count), icon="groups", color="positive")
            stats_card("Searches", str(search_count), icon="search", color="secondary")

        # Quick-start tips
        with ui.card().classes("w-full p-4"):
            ui.label("Getting Started").classes("text-subtitle1 font-bold mb-2")
            with ui.column().classes("gap-1"):
                ui.label("1. Go to Import Data to upload your Verlumen Excel spreadsheet.").classes("text-body2")
                ui.label("2. Review imported products on the Products page.").classes("text-body2")
                ui.label("3. Use Amazon Search to find competitors for each product.").classes("text-body2")
                ui.label("4. Check the Analysis page for competition and opportunity scores.").classes("text-body2")
                ui.label("5. Export results to Excel from the Export page.").classes("text-body2")

        # Recent search sessions
        session = get_session()
        try:
            recent = (
                session.query(SearchSession)
                .order_by(SearchSession.created_at.desc())
                .limit(5)
                .all()
            )
        finally:
            session.close()

        if recent:
            with ui.card().classes("w-full p-4"):
                ui.label("Recent Searches").classes("text-subtitle1 font-bold mb-2")
                columns = [
                    {"name": "query", "label": "Query", "field": "query", "align": "left"},
                    {"name": "results", "label": "Results", "field": "results", "align": "right"},
                    {"name": "date", "label": "Date", "field": "date", "align": "left"},
                ]
                rows = []
                for s in recent:
                    rows.append({
                        "query": s.search_query,
                        "results": (s.organic_results or 0) + (s.sponsored_results or 0),
                        "date": s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "",
                    })
                ui.table(columns=columns, rows=rows, row_key="query").props("flat bordered dense")
