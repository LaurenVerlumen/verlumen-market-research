"""Export page - download enriched research data as Excel."""
from datetime import datetime

from nicegui import ui, app
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from config import EXPORTS_DIR
from src.models import get_session, Product, Category, SearchSession, AmazonCompetitor
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
                on_click=lambda: ui.navigate.to("/products"),
            ).props("color=primary")
            return

        with ui.card().classes("w-full p-4"):
            ui.label("Export Summary").classes("text-subtitle1 font-bold mb-2")
            ui.label(f"Total products: {total_products}").classes("text-body2")
            ui.label(f"Products with research data: {researched}").classes("text-body2")
            unresearched = total_products - researched
            if unresearched > 0:
                ui.label(
                    f"{unresearched} product(s) not yet researched -- "
                    "they will appear as 'Not researched' in the export."
                ).classes("text-body2 text-warning")

            ui.separator().classes("my-2")

            # Export options
            ui.label("Export Options").classes("text-subtitle2 font-medium mb-1")

            include_ml_cb = ui.checkbox(
                "Include ML Analysis",
                value=True,
            ).tooltip("Adds Match Score, Price Strategy, Demand Level columns and AI Recommendations sheet")

            include_profit_cb = ui.checkbox(
                "Include Profit Analysis",
                value=True,
            ).tooltip("Adds Profit Analysis sheet with margins, ROI, and break-even calculations")

            # Sheets summary
            sheets_label = ui.label("").classes("text-caption text-secondary mt-1")

            def _update_sheets_label():
                sheets = ["Summary", "Detailed Competitors", "Category Analysis"]
                if include_profit_cb.value:
                    sheets.append("Profit Analysis")
                if include_ml_cb.value:
                    sheets.append("AI Recommendations")
                sheets_label.text = (
                    f"Exporting {total_products} products across {len(sheets)} sheets: "
                    + ", ".join(sheets)
                )

            _update_sheets_label()
            include_ml_cb.on_value_change(lambda _: _update_sheets_label())
            include_profit_cb.on_value_change(lambda _: _update_sheets_label())

        # --- Export Filters ---
        with ui.card().classes("w-full p-4"):
            ui.label("Export Filters").classes("text-subtitle1 font-bold mb-2")
            ui.label("Narrow down which products to include in the export.").classes(
                "text-caption text-secondary mb-2"
            )

            # Load categories for filter dropdown
            _cat_session = get_session()
            try:
                _cat_names = ["All"] + [
                    c.name for c in _cat_session.query(Category).order_by(Category.name).all()
                ]
            finally:
                _cat_session.close()

            with ui.row().classes("gap-4 flex-wrap items-end"):
                export_cat_filter = ui.select(
                    _cat_names, value="All", label="Category",
                ).props("outlined dense").classes("w-48")

                export_status_filter = ui.select(
                    ["All", "Imported", "Researched", "Under Review", "Approved", "Rejected"],
                    value="All",
                    label="Product Status",
                ).props("outlined dense").classes("w-48")

                export_research_filter = ui.select(
                    ["All", "Researched Only", "Unresearched Only"],
                    value="All",
                    label="Research Status",
                ).props("outlined dense").classes("w-48")

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

            do_ml = include_ml_cb.value
            do_profit = include_profit_cb.value

            session = get_session()
            try:
                query = (
                    session.query(Product)
                    .options(joinedload(Product.category))
                )

                # Apply export filters
                _cat_val = export_cat_filter.value
                if _cat_val != "All":
                    _cat_obj = session.query(Category).filter_by(name=_cat_val).first()
                    if _cat_obj:
                        query = query.filter(Product.category_id == _cat_obj.id)

                _status_map = {
                    "Imported": "imported",
                    "Researched": "researched",
                    "Under Review": "under_review",
                    "Approved": "approved",
                    "Rejected": "rejected",
                }
                _st_val = export_status_filter.value
                if _st_val != "All" and _st_val in _status_map:
                    query = query.filter(Product.status == _status_map[_st_val])

                _res_val = export_research_filter.value
                if _res_val == "Researched Only":
                    query = query.filter(
                        Product.id.in_(
                            session.query(SearchSession.product_id).distinct()
                        )
                    )
                elif _res_val == "Unresearched Only":
                    query = query.filter(
                        ~Product.id.in_(
                            session.query(SearchSession.product_id).distinct()
                        )
                    )

                products = query.order_by(Product.category_id, Product.name).all()
                analyzer = CompetitionAnalyzer()
                products_data = []

                # Batch: get latest session ID per product
                latest_subq = (
                    session.query(
                        SearchSession.product_id,
                        func.max(SearchSession.id).label("max_id"),
                    )
                    .group_by(SearchSession.product_id)
                    .subquery()
                )
                latest_map = {
                    row.product_id: row.max_id
                    for row in session.query(
                        latest_subq.c.product_id,
                        latest_subq.c.max_id,
                    ).all()
                }

                # Batch: load all competitors for latest sessions
                latest_ids = list(latest_map.values())
                all_comps = []
                if latest_ids:
                    all_comps = (
                        session.query(AmazonCompetitor)
                        .filter(AmazonCompetitor.search_session_id.in_(latest_ids))
                        .order_by(AmazonCompetitor.position)
                        .all()
                    )
                comps_by_session: dict[int, list] = {}
                for c in all_comps:
                    comps_by_session.setdefault(c.search_session_id, []).append(c)

                for p in products:
                    latest_sid = latest_map.get(p.id)

                    competitors_raw = []
                    analysis = {}

                    if latest_sid:
                        comps = comps_by_session.get(latest_sid, [])
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

                    entry = {
                        "category": p.category.name if p.category else "Uncategorized",
                        "name": p.name,
                        "alibaba_url": p.alibaba_url,
                        "alibaba_price_min": p.alibaba_price_min,
                        "alibaba_price_max": p.alibaba_price_max,
                        "analysis": analysis,
                        "competitors": competitors_raw,
                    }

                    # ML data
                    if do_ml and competitors_raw:
                        entry["ml_data"] = _compute_ml_data(
                            p.name, competitors_raw, p.alibaba_price_min, p.alibaba_price_max,
                        )

                    # Profit data
                    if do_profit and competitors_raw and p.alibaba_price_min is not None:
                        entry["profit_data"] = _compute_profit_data(
                            p.alibaba_price_min,
                            p.alibaba_price_max or p.alibaba_price_min,
                            competitors_raw,
                        )

                    products_data.append(entry)

                exporter = ExcelExporter()
                saved_path = exporter.export(
                    products_data, str(output_path),
                    include_ml=do_ml, include_profit=do_profit,
                )

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


def _compute_ml_data(
    product_name: str,
    competitors: list[dict],
    alibaba_price_min: float | None,
    alibaba_price_max: float | None,
) -> dict:
    """Compute ML-based data for a product's export row."""
    try:
        from src.services.match_scorer import score_matches
        from src.services.price_recommender import recommend_pricing
        from src.services.demand_estimator import estimate_demand
        from src.services.query_optimizer import optimize_query
    except ImportError:
        return {}

    try:
        matches = score_matches(product_name, [dict(c) for c in competitors])
        best_score = matches[0].get("match_score", 0) if matches else 0
        top_3 = ", ".join(
            (m.get("title") or "")[:50] for m in matches[:3]
        ) if matches else ""

        alibaba_cost = None
        if alibaba_price_min is not None:
            alibaba_cost = (
                (alibaba_price_min + (alibaba_price_max or alibaba_price_min)) / 2.0
            )
        pricing = recommend_pricing(competitors, alibaba_cost)
        demand = estimate_demand(competitors)

        strategies = pricing.get("strategies") or {}
        competitive = strategies.get("competitive") or {}
        rec_price = competitive.get("price")
        rationale = competitive.get("rationale", "")

        # Profit margin for competitive strategy
        margin = competitive.get("margin_percent")

        # Demand level
        market_size = demand.get("market_size_category", "")
        demand_level = market_size.capitalize() if market_size else ""

        # Estimated monthly revenue
        est_monthly_revenue = competitive.get("estimated_monthly_revenue")

        optimized_query = optimize_query(product_name)

        return {
            "best_match_score": best_score,
            "price_strategy": "Competitive",
            "demand_level": demand_level,
            "estimated_monthly_revenue": est_monthly_revenue,
            "profit_margin_pct": margin,
            "optimized_query": optimized_query,
            "top_3_matches": top_3,
            "recommended_price": rec_price,
            "rationale": rationale,
            "market_size": demand_level,
        }
    except Exception:
        return {}


def _compute_profit_data(
    alibaba_price_min: float,
    alibaba_price_max: float,
    competitors: list[dict],
) -> dict:
    """Compute profit analysis data for a product."""
    try:
        from src.services.profit_calculator import calculate_profit
        return calculate_profit(alibaba_price_min, alibaba_price_max, competitors)
    except Exception:
        return {}
