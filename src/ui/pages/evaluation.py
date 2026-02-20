"""Decision Hub -- evaluate, compare, and approve/reject researched products."""
import statistics as _stats

from nicegui import ui
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from src.models import get_session, Product, Category, SearchSession, AmazonCompetitor
from src.services.viability_scorer import calculate_vvs
from src.services.utils import parse_bought as _parse_bought
from src.ui.components.helpers import (
    avatar_color as _avatar_color,
    product_image_src as _product_image_src,
)
from src.ui.layout import build_layout

# Status badge colors (shared with products.py)
_STATUS_COLORS = {
    "imported": "grey-5",
    "researched": "blue",
    "under_review": "warning",
    "approved": "positive",
    "rejected": "negative",
}
_STATUS_LABELS = {
    "imported": "Imported",
    "researched": "Researched",
    "under_review": "Under Review",
    "approved": "Approved",
    "rejected": "Rejected",
}


def evaluation_page():
    """Render the Decision Hub page."""
    content = build_layout()

    with content:
        ui.label("Decision Hub").classes("text-h5 font-bold")
        ui.label("Evaluate, compare, and approve or reject products.").classes(
            "text-body2 text-secondary mb-2"
        )

        # ----- Load data -----
        session = get_session()
        try:
            # Get all products with research data
            products = (
                session.query(Product)
                .options(
                    joinedload(Product.category),
                    joinedload(Product.search_sessions),
                )
                .order_by(Product.name)
                .all()
            )

            if not products:
                ui.label("No products found. Import products first.").classes(
                    "text-body2 text-secondary"
                )
                ui.button(
                    "Import Data", icon="upload_file",
                    on_click=lambda: ui.navigate.to("/import"),
                ).props("color=primary")
                return

            # Get latest session IDs per product
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
                    latest_subq.c.product_id, latest_subq.c.max_id
                ).all()
            }

            # Batch load competitors for latest sessions
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

            # Build enriched product data list
            product_rows: list[dict] = []
            for p in products:
                has_research = len(list(p.search_sessions)) > 0
                latest_sid = latest_map.get(p.id)
                comps = comps_by_session.get(latest_sid, []) if latest_sid else []

                # Competitor stats
                prices = [c.price for c in comps if c.price is not None]
                avg_amazon_price = _stats.mean(prices) if prices else None

                # VVS score
                vvs_score = 0.0
                vvs_verdict = ""
                vvs_color = "grey"
                if comps:
                    comp_dicts = [
                        {
                            "price": c.price,
                            "rating": c.rating,
                            "review_count": c.review_count,
                            "bought_last_month": c.bought_last_month,
                            "badge": c.badge,
                            "is_prime": c.is_prime,
                            "is_sponsored": c.is_sponsored,
                            "position": c.position,
                        }
                        for c in comps
                    ]
                    alibaba_cost = p.alibaba_price_min
                    try:
                        vvs = calculate_vvs(p, comp_dicts, alibaba_cost=alibaba_cost)
                        vvs_score = vvs.get("vvs_score", 0.0)
                        vvs_verdict = vvs.get("verdict", "")
                        vvs_color = vvs.get("verdict_color", "grey")
                    except Exception:
                        pass

                # Estimated margin
                est_margin = None
                if avg_amazon_price and p.alibaba_price_min and avg_amazon_price > 0:
                    fees_est = avg_amazon_price * 0.15 + 4.0  # ~15% referral + FBA
                    net = avg_amazon_price - fees_est - p.alibaba_price_min
                    est_margin = (net / avg_amazon_price) * 100

                # Competition level
                reviews = [c.review_count or 0 for c in comps]
                top_reviews = sorted(reviews, reverse=True)[:10]
                avg_top = _stats.mean(top_reviews) if top_reviews else 0
                if avg_top >= 2000:
                    comp_level = "High"
                elif avg_top >= 500:
                    comp_level = "Medium"
                else:
                    comp_level = "Low"

                # Demand level
                bought_vals = []
                for c in comps:
                    b = _parse_bought(c.bought_last_month)
                    if b is not None and b > 0:
                        bought_vals.append(b)
                avg_bought = _stats.mean(bought_vals) if bought_vals else 0
                if avg_bought >= 100:
                    demand_level = "High"
                elif avg_bought >= 30:
                    demand_level = "Medium"
                else:
                    demand_level = "Low"

                product_rows.append({
                    "id": p.id,
                    "name": p.name,
                    "category": p.category.name if p.category else "Uncategorized",
                    "status": getattr(p, "status", None) or "imported",
                    "image_src": _product_image_src(p),
                    "avatar_letter": p.name[0].upper() if p.name else "?",
                    "avatar_color": _avatar_color(p.name) if p.name else "#90A4AE",
                    "has_research": has_research,
                    "vvs_score": vvs_score,
                    "vvs_verdict": vvs_verdict,
                    "vvs_color": vvs_color,
                    "alibaba_cost": p.alibaba_price_min,
                    "avg_amazon_price": avg_amazon_price,
                    "est_margin": est_margin,
                    "comp_level": comp_level if comps else "-",
                    "demand_level": demand_level if comps else "-",
                    "comp_count": len(comps),
                })
        finally:
            session.close()

        # ----- Summary Stats -----
        researched_rows = [r for r in product_rows if r["has_research"]]
        approved_count = sum(1 for r in product_rows if r["status"] == "approved")
        rejected_count = sum(1 for r in product_rows if r["status"] == "rejected")
        under_review_count = sum(1 for r in product_rows if r["status"] == "under_review")
        vvs_scores = [r["vvs_score"] for r in researched_rows if r["vvs_score"] > 0]
        avg_vvs = _stats.mean(vvs_scores) if vvs_scores else 0

        with ui.row().classes("gap-4 flex-wrap"):
            _summary_card("Total Researched", str(len(researched_rows)), "science", "primary")
            _summary_card("Approved", str(approved_count), "check_circle", "positive")
            _summary_card("Rejected", str(rejected_count), "cancel", "negative")
            _summary_card("Pending Review", str(under_review_count), "visibility", "warning")
            _summary_card("Avg VVS", f"{avg_vvs:.1f}/10" if avg_vvs > 0 else "-", "speed", "accent")

        # ----- Filter Buttons -----
        active_filter = {"value": "All"}

        with ui.row().classes("gap-2 items-center flex-wrap"):
            filter_buttons: dict[str, ui.button] = {}
            for fval, flabel, ficon in [
                ("All", "All", "apps"),
                ("researched", "Researched", "science"),
                ("under_review", "Under Review", "visibility"),
                ("approved", "Approved", "check_circle"),
                ("rejected", "Rejected", "cancel"),
            ]:
                btn = ui.button(flabel, icon=ficon).props("outline dense")
                filter_buttons[fval] = btn

        # ----- Bulk Selection State -----
        selected_ids: set[int] = set()
        row_checkboxes: dict[int, ui.checkbox] = {}

        # ----- Bulk Action Bar -----
        bulk_bar = ui.row().classes("w-full items-center gap-3 p-2").style(
            "background: #f5f0eb; border-left: 4px solid #A08968; display: none"
        )
        with bulk_bar:
            bulk_count_label = ui.label("0 selected").classes("text-subtitle2 font-bold")
            ui.space()
            bulk_approve_btn = ui.button("Approve Selected", icon="check_circle").props(
                "color=positive size=sm"
            )
            bulk_reject_btn = ui.button("Reject Selected", icon="cancel").props(
                "color=negative size=sm"
            )
            bulk_review_btn = ui.button("Mark for Review", icon="visibility").props(
                "color=warning size=sm"
            )

        def _update_bulk_bar():
            count = len(selected_ids)
            bulk_count_label.text = f"{count} selected"
            bulk_bar.style(
                "background: #f5f0eb; border-left: 4px solid #A08968; "
                + ("display: flex" if count > 0 else "display: none")
            )

        def _on_checkbox_change(pid: int, checked: bool):
            if checked:
                selected_ids.add(pid)
            else:
                selected_ids.discard(pid)
            _update_bulk_bar()

        def _bulk_set_status(new_status: str):
            if not selected_ids:
                ui.notify("No products selected.", type="warning")
                return
            count = len(selected_ids)
            db = get_session()
            try:
                for pid in list(selected_ids):
                    p = db.query(Product).filter(Product.id == pid).first()
                    if p:
                        p.status = new_status
                db.commit()
            finally:
                db.close()
            # Update local data
            for row in product_rows:
                if row["id"] in selected_ids:
                    row["status"] = new_status
            selected_ids.clear()
            _update_bulk_bar()
            _render_table()
            _update_summary_stats()
            ui.notify(
                f"Updated {count} product(s) to {_STATUS_LABELS.get(new_status, new_status)}.",
                type="positive",
            )

        bulk_approve_btn.on_click(lambda: _bulk_set_status("approved"))
        bulk_reject_btn.on_click(lambda: _bulk_set_status("rejected"))
        bulk_review_btn.on_click(lambda: _bulk_set_status("under_review"))

        # ----- Table Container -----
        table_container = ui.column().classes("w-full gap-0")

        def _get_filtered_rows():
            filt = active_filter["value"]
            if filt == "All":
                return list(product_rows)
            return [r for r in product_rows if r["status"] == filt]

        def _set_product_status(pid: int, new_status: str):
            """Set a single product's status."""
            db = get_session()
            try:
                p = db.query(Product).filter(Product.id == pid).first()
                if p:
                    p.status = new_status
                    db.commit()
            finally:
                db.close()
            # Update local data
            for row in product_rows:
                if row["id"] == pid:
                    row["status"] = new_status
                    break
            _render_table()
            _update_summary_stats()

        def _update_summary_stats():
            """Recalculate summary stat labels after status changes."""
            r_count = sum(1 for r in product_rows if r["has_research"])
            a_count = sum(1 for r in product_rows if r["status"] == "approved")
            rej_count = sum(1 for r in product_rows if r["status"] == "rejected")
            rev_count = sum(1 for r in product_rows if r["status"] == "under_review")
            v_scores = [r["vvs_score"] for r in product_rows if r["has_research"] and r["vvs_score"] > 0]
            a_vvs = _stats.mean(v_scores) if v_scores else 0
            # Update labels set by _summary_card -- we store refs
            _summary_refs["Total Researched"].text = str(r_count)
            _summary_refs["Approved"].text = str(a_count)
            _summary_refs["Rejected"].text = str(rej_count)
            _summary_refs["Pending Review"].text = str(rev_count)
            _summary_refs["Avg VVS"].text = f"{a_vvs:.1f}/10" if a_vvs > 0 else "-"

        def _vvs_color_class(score: float) -> str:
            if score >= 8:
                return "text-positive"
            elif score >= 6:
                return "text-warning"
            elif score >= 4:
                return "text-orange"
            else:
                return "text-negative"

        def _render_table():
            row_checkboxes.clear()
            table_container.clear()
            filtered = _get_filtered_rows()

            with table_container:
                if not filtered:
                    ui.label("No products match this filter.").classes(
                        "text-body2 text-secondary py-4"
                    )
                    return

                # Table header
                with ui.row().classes(
                    "w-full items-center gap-0 px-3 py-2"
                ).style("background: #f5f5f5; border-bottom: 1px solid #e0e0e0; font-size: 12px"):
                    ui.label("").style("width: 40px")  # checkbox space
                    ui.label("Product").classes("font-bold text-secondary").style("flex: 2; min-width: 200px")
                    ui.label("Category").classes("font-bold text-secondary").style("flex: 1; min-width: 100px")
                    ui.label("Status").classes("font-bold text-secondary text-center").style("width: 100px")
                    ui.label("VVS").classes("font-bold text-secondary text-center").style("width: 70px")
                    ui.label("Alibaba").classes("font-bold text-secondary text-right").style("width: 80px")
                    ui.label("Amazon Avg").classes("font-bold text-secondary text-right").style("width: 90px")
                    ui.label("Margin").classes("font-bold text-secondary text-right").style("width: 70px")
                    ui.label("Comp.").classes("font-bold text-secondary text-center").style("width: 60px")
                    ui.label("Demand").classes("font-bold text-secondary text-center").style("width: 70px")
                    ui.label("# Comp").classes("font-bold text-secondary text-right").style("width: 60px")
                    ui.label("Actions").classes("font-bold text-secondary text-center").style("width: 120px")

                # Table rows
                for row in filtered:
                    _bg = "#FAFAFA" if filtered.index(row) % 2 == 0 else "white"
                    with ui.row().classes(
                        "w-full items-center gap-0 px-3 py-2"
                    ).style(f"border-bottom: 1px solid #eee; background: {_bg}"):
                        # Checkbox
                        cb = ui.checkbox(
                            value=row["id"] in selected_ids,
                            on_change=lambda e, pid=row["id"]: _on_checkbox_change(pid, e.value),
                        ).style("width: 40px")
                        row_checkboxes[row["id"]] = cb

                        # Product name + thumbnail
                        with ui.row().classes(
                            "items-center gap-2 cursor-pointer"
                        ).style("flex: 2; min-width: 200px").on(
                            "click", lambda _, pid=row["id"]: ui.navigate.to(f"/products/{pid}")
                        ):
                            if row["image_src"]:
                                ui.image(row["image_src"]).classes(
                                    "w-8 h-8 rounded object-cover"
                                ).style("min-width: 32px")
                            else:
                                ui.avatar(
                                    row["avatar_letter"],
                                    color=row["avatar_color"],
                                    text_color="white",
                                    size="32px",
                                )
                            ui.label(row["name"]).classes(
                                "text-body2 font-medium"
                            ).style("overflow: hidden; text-overflow: ellipsis; white-space: nowrap")

                        # Category
                        ui.label(row["category"]).classes("text-caption text-secondary").style(
                            "flex: 1; min-width: 100px"
                        )

                        # Status badge
                        with ui.element("div").style("width: 100px; text-align: center"):
                            st = row["status"]
                            ui.badge(
                                _STATUS_LABELS.get(st, st.replace("_", " ").title()),
                                color=_STATUS_COLORS.get(st, "grey-5"),
                            )

                        # VVS Score
                        with ui.element("div").style("width: 70px; text-align: center"):
                            if row["vvs_score"] > 0:
                                ui.label(f"{row['vvs_score']:.1f}").classes(
                                    f"text-body2 font-bold {_vvs_color_class(row['vvs_score'])}"
                                )
                            else:
                                ui.label("-").classes("text-caption text-secondary")

                        # Alibaba cost
                        with ui.element("div").style("width: 80px; text-align: right"):
                            if row["alibaba_cost"] is not None:
                                ui.label(f"${row['alibaba_cost']:.2f}").classes("text-body2")
                            else:
                                ui.label("-").classes("text-caption text-secondary")

                        # Amazon avg price
                        with ui.element("div").style("width: 90px; text-align: right"):
                            if row["avg_amazon_price"] is not None:
                                ui.label(f"${row['avg_amazon_price']:.2f}").classes("text-body2")
                            else:
                                ui.label("-").classes("text-caption text-secondary")

                        # Estimated margin
                        with ui.element("div").style("width: 70px; text-align: right"):
                            if row["est_margin"] is not None:
                                _mc = "text-positive" if row["est_margin"] > 20 else (
                                    "text-warning" if row["est_margin"] > 0 else "text-negative"
                                )
                                ui.label(f"{row['est_margin']:.0f}%").classes(f"text-body2 font-bold {_mc}")
                            else:
                                ui.label("-").classes("text-caption text-secondary")

                        # Competition level
                        with ui.element("div").style("width: 60px; text-align: center"):
                            _cl = row["comp_level"]
                            _cl_color = {
                                "Low": "text-positive",
                                "Medium": "text-warning",
                                "High": "text-negative",
                            }.get(_cl, "text-secondary")
                            ui.label(_cl).classes(f"text-caption font-medium {_cl_color}")

                        # Demand level
                        with ui.element("div").style("width: 70px; text-align: center"):
                            _dl = row["demand_level"]
                            _dl_color = {
                                "High": "text-positive",
                                "Medium": "text-warning",
                                "Low": "text-negative",
                            }.get(_dl, "text-secondary")
                            ui.label(_dl).classes(f"text-caption font-medium {_dl_color}")

                        # Competitor count
                        with ui.element("div").style("width: 60px; text-align: right"):
                            ui.label(str(row["comp_count"])).classes("text-body2")

                        # Action buttons
                        with ui.row().classes("gap-1 items-center justify-center").style("width: 120px"):
                            ui.button(
                                icon="check_circle",
                                on_click=lambda _, pid=row["id"]: _set_product_status(pid, "approved"),
                            ).props("flat round dense color=positive size=sm").tooltip("Approve")
                            ui.button(
                                icon="cancel",
                                on_click=lambda _, pid=row["id"]: _set_product_status(pid, "rejected"),
                            ).props("flat round dense color=negative size=sm").tooltip("Reject")
                            ui.button(
                                icon="visibility",
                                on_click=lambda _, pid=row["id"]: _set_product_status(pid, "under_review"),
                            ).props("flat round dense color=warning size=sm").tooltip("Mark for Review")

        # Wire filter buttons
        def _apply_filter(fval: str):
            active_filter["value"] = fval
            # Update button styles
            for k, btn in filter_buttons.items():
                if k == fval:
                    btn.props("unelevated color=primary")
                else:
                    btn.props("outline color=grey")
            _render_table()

        for fval, btn in filter_buttons.items():
            btn.on_click(lambda _, f=fval: _apply_filter(f))

        # Initial render
        _apply_filter("All")


# Store references to summary value labels for dynamic updates
_summary_refs: dict[str, ui.label] = {}


def _summary_card(title: str, value: str, icon: str, color: str):
    """Render a small summary stat card and store a ref to the value label."""
    with ui.card().classes("p-3").style("min-width: 140px"):
        with ui.row().classes("items-center gap-2"):
            ui.icon(icon).classes(f"text-{color}")
            ui.label(title).classes("text-caption text-secondary font-medium")
        lbl = ui.label(value).classes("text-h6 font-bold")
        _summary_refs[title] = lbl
