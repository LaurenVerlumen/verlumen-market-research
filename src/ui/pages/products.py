"""Products page -- browse and manage imported products."""
from nicegui import ui

from src.models import get_session, Category, Product, AmazonCompetitor
from src.ui.layout import build_layout


def products_page():
    """Render the products browser page."""
    content = build_layout()

    with content:
        ui.label("Products").classes("text-h5 font-bold")
        ui.label("Browse products imported from your spreadsheet.").classes(
            "text-body2 text-secondary mb-2"
        )

        session = get_session()
        try:
            categories = session.query(Category).order_by(Category.name).all()
            if not categories:
                ui.label(
                    "No products imported yet. Go to Import Data to get started."
                ).classes("text-body1 text-secondary")
                return

            # Category filter
            cat_names = ["All"] + [c.name for c in categories]
            filter_select = ui.select(
                cat_names, value="All", label="Filter by Category"
            ).classes("w-64")

            product_container = ui.column().classes("w-full gap-2")

            def refresh_products():
                product_container.clear()
                db = get_session()
                try:
                    query = db.query(Product).order_by(Product.name)
                    if filter_select.value != "All":
                        cat = db.query(Category).filter_by(name=filter_select.value).first()
                        if cat:
                            query = query.filter(Product.category_id == cat.id)

                    products = query.all()
                    with product_container:
                        if not products:
                            ui.label("No products found.").classes("text-body2 text-secondary")
                            return

                        # Summary table
                        columns = [
                            {"name": "name", "label": "Product Name", "field": "name", "sortable": True, "align": "left"},
                            {"name": "category", "label": "Category", "field": "category", "sortable": True, "align": "left"},
                            {"name": "price", "label": "Alibaba Price", "field": "price", "align": "right"},
                            {"name": "competitors", "label": "Competitors", "field": "competitors", "sortable": True, "align": "right"},
                            {"name": "search_query", "label": "Search Query", "field": "search_query", "align": "left"},
                        ]
                        rows = []
                        for p in products:
                            comp_count = db.query(AmazonCompetitor).filter_by(product_id=p.id).count()
                            price = _format_price(p.alibaba_price_min, p.alibaba_price_max)
                            rows.append({
                                "name": p.name,
                                "category": p.category.name if p.category else "",
                                "price": price,
                                "competitors": comp_count,
                                "search_query": p.amazon_search_query or p.name,
                            })

                        table = ui.table(
                            columns=columns,
                            rows=rows,
                            row_key="name",
                            pagination={"rowsPerPage": 20, "sortBy": "name"},
                        ).classes("w-full")
                        table.props("flat bordered dense")
                finally:
                    db.close()

            filter_select.on_value_change(lambda _: refresh_products())
            refresh_products()
        finally:
            session.close()


def _format_price(pmin, pmax) -> str:
    if pmin is not None and pmax is not None:
        return f"${pmin:.2f} - ${pmax:.2f}"
    if pmin is not None:
        return f"${pmin:.2f}"
    if pmax is not None:
        return f"${pmax:.2f}"
    return "-"
