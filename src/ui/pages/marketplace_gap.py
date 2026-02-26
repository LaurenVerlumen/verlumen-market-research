"""Cross-Marketplace Gap Analyzer page.

Compares products across Amazon marketplaces to find price arbitrage,
competition differences, and whitespace opportunities.
"""
from nicegui import ui
from sqlalchemy import func

from config import AMAZON_MARKETPLACES
from src.models.search_session import SearchSession
from src.models.amazon_competitor import AmazonCompetitor
from src.services.marketplace_gap import (
    get_all_products_with_research,
    analyze_product_gap,
    MarketplaceGapResult,
)
from src.ui.layout import build_layout
from src.ui.components.helpers import page_header, section_header, CARD_CLASSES
from src.ui.components.stats_card import stats_card


def marketplace_gap_page():
    """Render the Cross-Marketplace Gap Analyzer page."""
    with build_layout("Marketplace Gap Analyzer"):
        page_header(
            "Cross-Marketplace Gap Analyzer",
            subtitle="Compare products across Amazon marketplaces to find arbitrage and whitespace opportunities.",
            icon="compare_arrows",
        )

        products = get_all_products_with_research()
        multi_mp = [p for p in products if p["marketplace_count"] > 1]

        # KPI cards
        with ui.row().classes("gap-4 flex-wrap"):
            stats_card(
                "Products Researched",
                str(len(products)),
                icon="inventory_2",
                color="accent",
            )
            stats_card(
                "Multi-Marketplace",
                str(len(multi_mp)),
                icon="public",
                color="positive",
            )
            # Count distinct marketplaces across all products
            all_domains = set()
            for p in products:
                all_domains.update(p.get("marketplaces", []))
            stats_card(
                "Marketplaces Used",
                str(len(all_domains)),
                icon="storefront",
                color="primary",
            )

        if not products:
            with ui.card().classes("w-full p-8"):
                with ui.column().classes("items-center w-full gap-2"):
                    ui.icon("public_off", size="xl").classes("text-grey-5")
                    ui.label("No marketplace research data yet").classes(
                        "text-h6 text-secondary"
                    )
                    ui.label(
                        "Run Amazon research on products to see cross-marketplace analysis."
                    ).classes("text-body2 text-grey-6")
            return

        # Summary table: all products with marketplace info
        with ui.card().classes(CARD_CLASSES):
            section_header(
                "Products by Marketplace Coverage",
                icon="table_chart",
                subtitle="Select a product with multiple marketplaces to see detailed comparison.",
            )

            columns = [
                {"name": "product", "label": "Product", "field": "product", "align": "left", "sortable": True},
                {"name": "mp_count", "label": "Marketplaces", "field": "mp_count", "align": "center", "sortable": True},
                {"name": "domains", "label": "Domains", "field": "domains", "align": "left"},
                {"name": "action", "label": "", "field": "action", "align": "center"},
            ]

            rows = []
            for p in products:
                mp_info = AMAZON_MARKETPLACES
                domain_labels = []
                for d in p["marketplaces"]:
                    info = mp_info.get(d, {})
                    flag = info.get("flag", "")
                    domain_labels.append(f"{flag} {d}")
                rows.append({
                    "product": p["product_name"],
                    "mp_count": p["marketplace_count"],
                    "domains": ", ".join(domain_labels),
                    "product_id": p["product_id"],
                })

            table = ui.table(
                columns=columns, rows=rows, row_key="product",
            ).props("flat bordered dense").classes("w-full")

            # Custom slot for action column: "Analyze" button for multi-marketplace products
            table.add_slot(
                "body-cell-action",
                r"""
                <q-td :props="props">
                    <q-btn
                        v-if="props.row.mp_count > 1"
                        label="Analyze"
                        icon="compare_arrows"
                        size="sm"
                        color="accent"
                        dense flat
                        @click="$parent.$emit('analyze', props.row)"
                    />
                    <span v-else class="text-grey-5 text-caption">Single marketplace</span>
                </q-td>
                """,
            )

            # Color-code marketplace count
            table.add_slot(
                "body-cell-mp_count",
                r"""
                <q-td :props="props">
                    <q-badge
                        :color="props.value > 2 ? 'green' : props.value > 1 ? 'blue' : 'grey'"
                        :label="props.value"
                        class="text-bold"
                    />
                </q-td>
                """,
            )

        # Detail area for selected product
        detail_container = ui.column().classes("w-full gap-4")

        def on_analyze(e):
            row = e.args
            product_id = row["product_id"]
            _show_product_detail(detail_container, product_id)

        table.on("analyze", on_analyze)


def _show_product_detail(container, product_id: int):
    """Load and display the gap analysis for a selected product."""
    container.clear()
    with container:
        with ui.row().classes("items-center gap-2"):
            spinner = ui.spinner("dots", size="lg")
            ui.label("Analyzing marketplace gaps...").classes("text-body2 text-secondary")

    result = analyze_product_gap(product_id)

    container.clear()
    with container:
        if result is None:
            ui.label("No data available for this product.").classes("text-body2 text-grey-6")
            return

        _render_gap_detail(result)


def _render_gap_detail(result: MarketplaceGapResult):
    """Render the full gap analysis detail for a product."""
    section_header(
        f"Gap Analysis: {result.product_name}",
        icon="compare_arrows",
        subtitle=f"Compared across {result.marketplace_count} marketplaces",
    )

    # Opportunity scores row
    with ui.row().classes("gap-4 flex-wrap"):
        for domain, score in sorted(
            result.opportunity_scores.items(), key=lambda x: x[1], reverse=True
        ):
            mp_info = AMAZON_MARKETPLACES.get(domain, {})
            flag = mp_info.get("flag", "")
            color = "positive" if score >= 65 else "warning" if score >= 45 else "negative"
            stats_card(
                f"{flag} {domain}",
                f"{score:.0f}/100",
                icon="trending_up",
                color=color,
            )

    # Side-by-side marketplace comparison table
    with ui.card().classes(CARD_CLASSES):
        section_header("Marketplace Comparison", icon="analytics")

        domains = list(result.snapshots.keys())

        comp_columns = [
            {"name": "metric", "label": "Metric", "field": "metric", "align": "left"},
        ]
        for d in domains:
            mp_info = AMAZON_MARKETPLACES.get(d, {})
            flag = mp_info.get("flag", "")
            comp_columns.append({
                "name": d, "label": f"{flag} {d}", "field": d, "align": "center",
            })

        comp_rows = []

        # Currency
        row_currency = {"metric": "Currency"}
        for d in domains:
            row_currency[d] = result.snapshots[d].currency
        comp_rows.append(row_currency)

        # Competitor count
        row_comps = {"metric": "Competitors"}
        for d in domains:
            row_comps[d] = str(result.snapshots[d].competitor_count)
        comp_rows.append(row_comps)

        # Avg price
        row_avg_price = {"metric": "Avg Price"}
        for d in domains:
            snap = result.snapshots[d]
            row_avg_price[d] = f"{snap.currency} {snap.avg_price:.2f}" if snap.avg_price else "-"
        comp_rows.append(row_avg_price)

        # Price range
        row_price_range = {"metric": "Price Range"}
        for d in domains:
            snap = result.snapshots[d]
            if snap.min_price is not None and snap.max_price is not None:
                row_price_range[d] = f"{snap.min_price:.2f} - {snap.max_price:.2f}"
            else:
                row_price_range[d] = "-"
        comp_rows.append(row_price_range)

        # Avg rating
        row_rating = {"metric": "Avg Rating"}
        for d in domains:
            snap = result.snapshots[d]
            row_rating[d] = f"{snap.avg_rating:.1f}" if snap.avg_rating is not None else "-"
        comp_rows.append(row_rating)

        # Avg reviews
        row_reviews = {"metric": "Avg Reviews"}
        for d in domains:
            snap = result.snapshots[d]
            row_reviews[d] = f"{snap.avg_reviews:.0f}" if snap.avg_reviews is not None else "-"
        comp_rows.append(row_reviews)

        # Session count
        row_sessions = {"metric": "Research Sessions"}
        for d in domains:
            row_sessions[d] = str(result.snapshots[d].session_count)
        comp_rows.append(row_sessions)

        # Opportunity score
        row_opp = {"metric": "Opportunity Score"}
        for d in domains:
            score = result.opportunity_scores.get(d, 0)
            row_opp[d] = f"{score:.0f}/100"
        comp_rows.append(row_opp)

        ui.table(
            columns=comp_columns, rows=comp_rows, row_key="metric",
        ).props("flat bordered dense").classes("w-full")

    # Price comparison chart
    if len(domains) > 1:
        with ui.card().classes(CARD_CLASSES):
            section_header("Price Comparison", icon="bar_chart")
            chart_domains = []
            chart_avg = []
            chart_min = []
            chart_max = []
            for d in domains:
                snap = result.snapshots[d]
                mp_info = AMAZON_MARKETPLACES.get(d, {})
                flag = mp_info.get("flag", "")
                chart_domains.append(f"{flag} {d}")
                chart_avg.append(snap.avg_price or 0)
                chart_min.append(snap.min_price or 0)
                chart_max.append(snap.max_price or 0)

            ui.echart({
                "title": {"text": "Price by Marketplace", "left": "center", "textStyle": {"fontSize": 14}},
                "tooltip": {"trigger": "axis"},
                "legend": {"data": ["Avg Price", "Min Price", "Max Price"], "bottom": 0},
                "xAxis": {"type": "category", "data": chart_domains, "axisLabel": {"rotate": 15}},
                "yAxis": {"type": "value", "name": "Price"},
                "series": [
                    {"name": "Avg Price", "data": chart_avg, "type": "bar", "color": "#A08968",
                     "itemStyle": {"borderRadius": [4, 4, 0, 0]}},
                    {"name": "Min Price", "data": chart_min, "type": "bar", "color": "#81C784",
                     "itemStyle": {"borderRadius": [4, 4, 0, 0]}},
                    {"name": "Max Price", "data": chart_max, "type": "bar", "color": "#E57373",
                     "itemStyle": {"borderRadius": [4, 4, 0, 0]}},
                ],
                "grid": {"bottom": 60},
            }).classes("w-full h-64")

    # Arbitrage alerts
    with ui.card().classes(CARD_CLASSES):
        section_header(
            "Arbitrage Alerts",
            icon="currency_exchange",
            subtitle="ASINs with >30% price differential across marketplaces",
        )
        if result.arbitrage_alerts:
            arb_columns = [
                {"name": "asin", "label": "ASIN", "field": "asin", "align": "left"},
                {"name": "title", "label": "Title", "field": "title", "align": "left"},
                {"name": "cheapest", "label": "Cheapest", "field": "cheapest", "align": "center"},
                {"name": "most_expensive", "label": "Most Expensive", "field": "most_expensive", "align": "center"},
                {"name": "diff", "label": "Differential", "field": "diff", "align": "center", "sortable": True},
            ]
            arb_rows = []
            for alert in result.arbitrage_alerts[:20]:
                min_info = AMAZON_MARKETPLACES.get(alert.min_domain, {})
                max_info = AMAZON_MARKETPLACES.get(alert.max_domain, {})
                arb_rows.append({
                    "asin": alert.asin,
                    "title": (alert.title[:50] + "...") if alert.title and len(alert.title) > 50 else (alert.title or "-"),
                    "cheapest": f"{min_info.get('flag', '')} {alert.min_price:.2f} ({alert.min_domain})",
                    "most_expensive": f"{max_info.get('flag', '')} {alert.max_price:.2f} ({alert.max_domain})",
                    "diff": f"+{alert.differential_pct:.0f}%",
                })

            arb_table = ui.table(
                columns=arb_columns, rows=arb_rows, row_key="asin",
            ).props("flat bordered dense").classes("w-full")

            # Color-code differential
            arb_table.add_slot(
                "body-cell-diff",
                r"""
                <q-td :props="props">
                    <q-badge
                        :color="parseInt(props.value) > 100 ? 'red' : parseInt(props.value) > 50 ? 'orange' : 'blue'"
                        :label="props.value"
                        class="text-bold"
                    />
                </q-td>
                """,
            )
        else:
            ui.label(
                "No significant price arbitrage detected (>30% differential)."
            ).classes("text-body2 text-grey-6 italic")

    # Whitespace detection
    with ui.card().classes(CARD_CLASSES):
        section_header(
            "Whitespace Opportunities",
            icon="explore",
            subtitle="ASINs present in some marketplaces but absent in others",
        )
        if result.whitespace:
            ws_columns = [
                {"name": "asin", "label": "ASIN", "field": "asin", "align": "left"},
                {"name": "title", "label": "Title", "field": "title", "align": "left"},
                {"name": "present", "label": "Present In", "field": "present", "align": "center"},
                {"name": "missing", "label": "Missing In", "field": "missing", "align": "left"},
            ]
            ws_rows = []
            for ws in result.whitespace[:30]:
                present_info = AMAZON_MARKETPLACES.get(ws["present_in"], {})
                missing_labels = []
                for d in ws["missing_in"]:
                    info = AMAZON_MARKETPLACES.get(d, {})
                    missing_labels.append(f"{info.get('flag', '')} {d}")
                ws_rows.append({
                    "asin": ws["asin"],
                    "title": (ws["title"][:50] + "...") if ws["title"] and len(ws["title"]) > 50 else (ws["title"] or "-"),
                    "present": f"{present_info.get('flag', '')} {ws['present_in']}",
                    "missing": ", ".join(missing_labels),
                })

            ui.table(
                columns=ws_columns, rows=ws_rows, row_key="asin",
            ).props("flat bordered dense").classes("w-full")
        else:
            ui.label(
                "No whitespace detected -- all ASINs appear across all researched marketplaces."
            ).classes("text-body2 text-grey-6 italic")

    # Competitor overlap matrix
    if len(domains) > 1:
        with ui.card().classes(CARD_CLASSES):
            section_header(
                "Competitor Overlap Matrix",
                icon="grid_on",
                subtitle="Number of shared ASINs between marketplace pairs",
            )
            # Build ASIN sets per domain
            asin_sets: dict[str, set] = {}
            for domain, snap in result.snapshots.items():
                asin_sets[domain] = set(snap.top_asins)
                # Also get full ASIN set from whitespace data
            # Re-derive full sets from the whitespace + present data
            db_asins: dict[str, set] = {}
            from src.models.database import get_session as _gs
            db = _gs()
            try:
                for domain in domains:
                    sessions = db.query(SearchSession.id).filter(
                        SearchSession.product_id == result.product_id,
                        SearchSession.amazon_domain == domain,
                    ).all()
                    sids = [s[0] for s in sessions]
                    if sids:
                        asins = db.query(func.distinct(AmazonCompetitor.asin)).filter(
                            AmazonCompetitor.search_session_id.in_(sids)
                        ).all()
                        db_asins[domain] = {a[0] for a in asins if a[0]}
                    else:
                        db_asins[domain] = set()
            finally:
                db.close()

            # Build matrix table
            matrix_cols = [
                {"name": "domain", "label": "", "field": "domain", "align": "left"},
            ]
            for d in domains:
                mp_info = AMAZON_MARKETPLACES.get(d, {})
                matrix_cols.append({
                    "name": d, "label": f"{mp_info.get('flag', '')} {d}", "field": d, "align": "center",
                })

            matrix_rows = []
            for d1 in domains:
                mp_info = AMAZON_MARKETPLACES.get(d1, {})
                row = {"domain": f"{mp_info.get('flag', '')} {d1}"}
                for d2 in domains:
                    if d1 == d2:
                        row[d2] = str(len(db_asins.get(d1, set())))
                    else:
                        overlap = len(db_asins.get(d1, set()) & db_asins.get(d2, set()))
                        row[d2] = str(overlap)
                matrix_rows.append(row)

            ui.table(
                columns=matrix_cols, rows=matrix_rows, row_key="domain",
            ).props("flat bordered dense").classes("w-full")
