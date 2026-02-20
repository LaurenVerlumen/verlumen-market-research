"""Export page - download enriched research data as Excel."""
from datetime import datetime

from nicegui import ui, app

from config import EXPORTS_DIR
from src.models import get_session, Product, SearchSession, AmazonCompetitor
from src.services import ExcelExporter, CompetitionAnalyzer
from src.ui.layout import build_layout


def export_page():
    """Render the export page."""
    content = build_layout()

    with content:
        ui.label("Export Results").classes("text-h5 font-bold")
        ui.label("Download enriched research data as Excel.").classes("text-body2 text-secondary mb-2")

        session = get_session()
        try:
            total_products = session.query(Product).count()
            researched = (
                session.query(Product.id)
                .join(SearchSession)
                .distinct()
                .count()
            )
        finally:
            session.close()

        if total_products == 0:
            ui.label("No products to export. Import some products first.").classes(
                "text-body2 text-secondary"
            )
            ui.button(
                "Import Excel", icon="upload_file",
                on_click=lambda: ui.navigate.to("/import"),
            ).props("color=primary")
            return

        with ui.card().classes("w-full p-4"):
            ui.label("Export Summary").classes("text-subtitle1 font-bold mb-2")
            ui.label(f"Total products: {total_products}").classes("text-body2")
            ui.label(f"Products with research data: {researched}").classes("text-body2")
            if researched < total_products:
                ui.label(
                    f"{total_products - researched} products have not been researched yet. "
                    "They will be included with empty competition data."
                ).classes("text-body2 text-warning")

        filename_input = ui.input(
            label="Output filename",
            value=f"verlumen-research-{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx",
        ).classes("w-96 mt-4")

        result_container = ui.column().classes("w-full")

        async def do_export():
            filename = filename_input.value.strip()
            if not filename.endswith(".xlsx"):
                filename += ".xlsx"

            output_path = EXPORTS_DIR / filename
            result_container.clear()

            session = get_session()
            try:
                products = session.query(Product).order_by(Product.category_id, Product.name).all()
                analyzer = CompetitionAnalyzer()
                products_data = []

                for p in products:
                    latest = (
                        session.query(SearchSession)
                        .filter(SearchSession.product_id == p.id)
                        .order_by(SearchSession.created_at.desc())
                        .first()
                    )

                    competitors_raw = []
                    analysis = {}

                    if latest:
                        comps = (
                            session.query(AmazonCompetitor)
                            .filter(AmazonCompetitor.search_session_id == latest.id)
                            .order_by(AmazonCompetitor.position)
                            .all()
                        )
                        competitors_raw = [
                            {
                                "asin": c.asin,
                                "title": c.title,
                                "price": c.price,
                                "rating": c.rating,
                                "review_count": c.review_count,
                                "bought_last_month": c.bought_last_month,
                                "is_prime": c.is_prime,
                                "badge": c.badge,
                                "amazon_url": c.amazon_url,
                            }
                            for c in comps
                        ]
                        analysis = analyzer.analyze(competitors_raw)

                    products_data.append({
                        "category": p.category.name if p.category else "Uncategorized",
                        "name": p.name,
                        "alibaba_url": p.alibaba_url,
                        "alibaba_price_min": p.alibaba_price_min,
                        "alibaba_price_max": p.alibaba_price_max,
                        "analysis": analysis,
                        "competitors": competitors_raw,
                    })

                exporter = ExcelExporter()
                saved_path = exporter.export(products_data, str(output_path))

                with result_container:
                    ui.label(f"Exported to: {saved_path}").classes("text-body2 text-positive mt-2")

                ui.notify(f"Export saved: {filename}", type="positive")

                app.add_static_file(local_file=str(output_path), url_path=f"/exports/{filename}")
                ui.download(f"/exports/{filename}")

            except Exception as e:
                with result_container:
                    ui.label(f"Export failed: {e}").classes("text-negative mt-2")
                ui.notify(f"Export failed: {e}", type="negative")
            finally:
                session.close()

        ui.button("Export to Excel", icon="download", on_click=do_export).props(
            "color=positive size=lg"
        ).classes("mt-4")

        # Previous exports
        ui.separator().classes("my-4")
        ui.label("Previous Exports").classes("text-subtitle1 font-bold mb-2")

        exports = sorted(
            EXPORTS_DIR.glob("*.xlsx"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not exports:
            ui.label("No previous exports.").classes("text-body2 text-secondary")
        else:
            for f in exports[:10]:
                with ui.row().classes("items-center gap-2"):
                    ui.icon("description").classes("text-secondary")
                    ui.label(f.name).classes("text-body2")
                    ui.label(
                        datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                    ).classes("text-caption text-secondary")
