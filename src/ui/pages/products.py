"""Products page -- browse and manage imported products."""
import asyncio

from nicegui import ui
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from config import SERPAPI_KEY
from src.models import get_session, init_db, Category, Product, AmazonCompetitor, SearchSession
from src.services import parse_alibaba_url, ImageFetcher, download_image
from src.ui.components.helpers import avatar_color as _avatar_color, product_image_src as _product_image_src, format_price as _format_price
from src.ui.layout import build_layout

# Status badge colors
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


def products_page():
    """Render the products browser page."""
    content = build_layout()

    with content:
        ui.label("Products").classes("text-h5 font-bold")
        ui.label("Browse and manage your products.").classes(
            "text-body2 text-secondary mb-2"
        )

        # --- Add Product Section ---
        with ui.expansion("Add Product Manually", icon="add_circle").classes("w-full mb-4"):
            url_input = ui.input(
                label="Alibaba URL",
                placeholder="https://www.alibaba.com/product-detail/...",
            ).classes("w-full")
            feedback_label = ui.label("").classes("text-body2")

            with ui.row().classes("w-full gap-4 items-end"):
                session_cats = get_session()
                try:
                    existing_cats = session_cats.query(Category).order_by(Category.name).all()
                    cat_options = {c.id: c.name for c in existing_cats}
                finally:
                    session_cats.close()

                category_select = ui.select(
                    options=cat_options,
                    label="Existing Category",
                    with_input=True,
                ).classes("w-64")
                ui.label("OR").classes("text-body2 text-secondary self-center")
                new_cat_input = ui.input(label="New Category Name").classes("w-64")

            name_input = ui.input(label="Product Name").classes("w-full")

            def on_url_change(e):
                url = url_input.value.strip() if url_input.value else ""
                feedback_label.text = ""
                feedback_label.classes(remove="text-warning text-positive text-negative")
                name_input.value = ""
                if not url:
                    return
                try:
                    info = parse_alibaba_url(url)
                    name_input.value = info.get("name", "")
                    # Check for duplicate
                    db = get_session()
                    try:
                        existing = db.query(Product).filter(
                            Product.alibaba_url == info["clean_url"]
                        ).first()
                        if existing:
                            feedback_label.text = f"Product already exists: {existing.name}"
                            feedback_label.classes(add="text-warning")
                    finally:
                        db.close()
                except Exception:
                    feedback_label.text = "Could not parse URL. Please check the format."
                    feedback_label.classes(add="text-negative")

            url_input.on("blur", on_url_change)

            def add_product():
                url = url_input.value.strip() if url_input.value else ""
                name = name_input.value.strip() if name_input.value else ""
                feedback_label.classes(remove="text-warning text-positive text-negative")
                if not url:
                    feedback_label.text = "Please enter an Alibaba URL."
                    feedback_label.classes(add="text-negative")
                    return
                if not name:
                    feedback_label.text = "Please enter a product name."
                    feedback_label.classes(add="text-negative")
                    return

                try:
                    info = parse_alibaba_url(url)
                except Exception:
                    feedback_label.text = "Invalid URL format."
                    feedback_label.classes(add="text-negative")
                    return

                init_db()
                db = get_session()
                try:
                    existing = db.query(Product).filter(
                        Product.alibaba_url == info["clean_url"]
                    ).first()
                    if existing:
                        feedback_label.text = f"Product already exists: {existing.name}"
                        feedback_label.classes(add="text-warning")
                        return

                    # Resolve category
                    new_cat_name = new_cat_input.value.strip() if new_cat_input.value else ""
                    cat_id = category_select.value

                    if new_cat_name:
                        cat = db.query(Category).filter(Category.name == new_cat_name).first()
                        if not cat:
                            cat = Category(name=new_cat_name)
                            db.add(cat)
                            db.flush()
                        cat_id = cat.id
                    elif not cat_id:
                        feedback_label.text = "Please select or create a category."
                        feedback_label.classes(add="text-negative")
                        return

                    product = Product(
                        category_id=cat_id,
                        alibaba_url=info["clean_url"],
                        alibaba_product_id=info.get("product_id"),
                        name=name,
                        amazon_search_query=name,
                    )
                    db.add(product)
                    db.commit()

                    feedback_label.text = f"Product added: {name}"
                    feedback_label.classes(add="text-positive")
                    url_input.value = ""
                    name_input.value = ""
                    new_cat_input.value = ""
                    refresh_products()
                except Exception as exc:
                    db.rollback()
                    feedback_label.text = f"Error: {exc}"
                    feedback_label.classes(add="text-negative")
                finally:
                    db.close()

            ui.button("Add Product", icon="add", on_click=add_product).props(
                "color=primary"
            ).classes("mt-2")

        # --- Products list ---
        session = get_session()
        try:
            categories = session.query(Category).order_by(Category.name).all()
            if not categories:
                ui.label(
                    "No products imported yet. Go to Import Data to get started."
                ).classes("text-body1 text-secondary")
                return

            # --- Search bar ---
            search_input = ui.input(
                label="Search products",
                placeholder="Type to filter by name...",
            ).props('clearable outlined dense').classes("w-full")
            search_input.props('prepend-inner-icon="search"')

            # --- Filter row ---
            with ui.row().classes("w-full items-center gap-4 flex-wrap"):
                cat_names = ["All"] + [c.name for c in categories]
                filter_select = ui.select(
                    cat_names, value="All", label="Category",
                ).props("outlined dense").classes("w-48")

                status_select = ui.select(
                    ["All", "Researched", "Pending"],
                    value="All",
                    label="Research Status",
                ).props("outlined dense").classes("w-48")

                profit_filter = ui.select(
                    ["All", "Has Profit Data", "No Profit Data"],
                    value="All",
                    label="Profit Data",
                ).props("outlined dense").classes("w-48")

                comp_range_filter = ui.select(
                    ["All", "0", "1-10", "10-50", "50+"],
                    value="All",
                    label="Competitors",
                ).props("outlined dense").classes("w-36")

                sort_select = ui.select(
                    ["Name (A-Z)", "Name (Z-A)", "Newest first", "Most competitors",
                     "Best Opportunity", "Category"],
                    value="Name (A-Z)",
                    label="Sort by",
                ).props("outlined dense").classes("w-48")

                ui.space()

                # Fetch Images button (image-fetcher feature)
                fetch_btn = ui.button(
                    "Fetch Product Images", icon="image_search",
                ).props("color=secondary outline")
                # Fetch Full Names button
                names_btn = ui.button(
                    "Fetch Full Names", icon="auto_fix_high",
                ).props("outline").tooltip(
                    "Fetch full product names from Google (1 API credit each)"
                )
                fetch_status = ui.label("").classes("text-body2 text-secondary")

            async def _fetch_all_images():
                if not SERPAPI_KEY:
                    ui.notify("SERPAPI_KEY is not configured.", type="negative")
                    return

                fetch_btn.disable()
                fetch_status.text = "Loading products..."

                db = get_session()
                try:
                    missing = (
                        db.query(Product)
                        .filter(Product.local_image_path.is_(None))
                        .all()
                    )
                    product_list = [{"id": p.id, "name": p.name} for p in missing]
                finally:
                    db.close()

                if not product_list:
                    fetch_status.text = "All products already have images."
                    fetch_btn.enable()
                    return

                total = len(product_list)
                fetched = 0
                not_found = 0
                fetcher = ImageFetcher(SERPAPI_KEY)

                for idx, prod in enumerate(product_list, start=1):
                    fetch_status.text = (
                        f"Fetching image {idx}/{total}: {prod['name'][:40]}..."
                    )
                    url, filename = await asyncio.get_event_loop().run_in_executor(
                        None, fetcher.fetch_and_save, prod["name"], prod["id"],
                    )

                    if url:
                        db = get_session()
                        try:
                            p = db.query(Product).filter(Product.id == prod["id"]).first()
                            if p:
                                p.alibaba_image_url = url
                                if filename:
                                    p.local_image_path = filename
                                db.commit()
                                fetched += 1
                        finally:
                            db.close()
                    else:
                        not_found += 1

                    if idx < total:
                        await asyncio.sleep(1.5)

                if not_found:
                    fetch_status.text = (
                        f"Done! Fetched & saved {fetched}/{total} images"
                        f" ({not_found} not found)"
                    )
                else:
                    fetch_status.text = f"Done! Fetched & saved {fetched}/{total} images locally"
                fetch_btn.enable()
                try:
                    refresh_products()
                except RuntimeError:
                    pass  # User navigated away during fetch

            fetch_btn.on_click(_fetch_all_images)

            async def _fetch_full_names():
                if not SERPAPI_KEY:
                    ui.notify("SERPAPI_KEY is not configured.", type="negative")
                    return

                names_btn.disable()
                fetch_status.text = "Loading products..."

                db = get_session()
                try:
                    all_products = db.query(Product).all()
                    product_list = [
                        {"id": p.id, "name": p.name, "product_id": p.alibaba_product_id}
                        for p in all_products
                    ]
                finally:
                    db.close()

                if not product_list:
                    fetch_status.text = "No products found."
                    names_btn.enable()
                    return

                from src.services.alibaba_parser import fetch_full_name
                total = len(product_list)
                updated = 0

                for idx, prod in enumerate(product_list, start=1):
                    fetch_status.text = (
                        f"Fetching name {idx}/{total}: {prod['name'][:40]}..."
                    )
                    full_name = await asyncio.get_event_loop().run_in_executor(
                        None, fetch_full_name, prod["name"], prod.get("product_id"),
                    )
                    if full_name and full_name != prod["name"]:
                        db = get_session()
                        try:
                            p = db.query(Product).filter(Product.id == prod["id"]).first()
                            if p:
                                p.name = full_name
                                p.amazon_search_query = full_name
                                db.commit()
                                updated += 1
                        finally:
                            db.close()

                    if idx < total:
                        await asyncio.sleep(1.5)

                fetch_status.text = f"Done! Updated {updated}/{total} product names"
                names_btn.enable()
                try:
                    refresh_products()
                except RuntimeError:
                    pass

            names_btn.on_click(_fetch_full_names)

            # --- Bulk selection state ---
            bulk_selected: set[int] = set()
            bulk_checkboxes: dict[int, ui.checkbox] = {}

            # --- Bulk action bar ---
            bulk_bar = ui.row().classes("w-full items-center gap-3 p-2").style(
                "background: #f5f0eb; border-left: 4px solid #A08968; display: none"
            )
            with bulk_bar:
                bulk_count_label = ui.label("0 selected").classes("text-subtitle2 font-bold")
                ui.button(
                    "Select All Visible", icon="select_all",
                    on_click=lambda: _bulk_select_all(),
                ).props("flat dense color=primary size=sm")
                ui.button(
                    "Deselect All", icon="deselect",
                    on_click=lambda: _bulk_deselect_all(),
                ).props("flat dense color=grey size=sm")
                ui.space()
                bulk_research_btn = ui.button(
                    "Research Selected", icon="search",
                ).props("color=positive size=sm")
                bulk_delete_btn = ui.button(
                    "Delete Selected", icon="delete",
                ).props("color=negative size=sm outline")

            def _update_bulk_bar():
                count = len(bulk_selected)
                bulk_count_label.text = f"{count} selected"
                bulk_bar.style(
                    "background: #f5f0eb; border-left: 4px solid #A08968; "
                    + ("display: flex" if count > 0 else "display: none")
                )

            def _bulk_select_all():
                db = get_session()
                try:
                    products = _get_filtered_products(db)
                    for p in products:
                        bulk_selected.add(p.id)
                        if p.id in bulk_checkboxes:
                            bulk_checkboxes[p.id].value = True
                finally:
                    db.close()
                _update_bulk_bar()

            def _bulk_deselect_all():
                for pid in list(bulk_selected):
                    if pid in bulk_checkboxes:
                        bulk_checkboxes[pid].value = False
                bulk_selected.clear()
                _update_bulk_bar()

            def _on_bulk_checkbox(pid: int, checked: bool):
                if checked:
                    bulk_selected.add(pid)
                else:
                    bulk_selected.discard(pid)
                _update_bulk_bar()

            def _bulk_research():
                if not bulk_selected:
                    ui.notify("No products selected.", type="warning")
                    return
                ids_param = ",".join(str(i) for i in bulk_selected)
                ui.navigate.to(f"/research?ids={ids_param}")

            def _bulk_delete():
                if not bulk_selected:
                    return

                def confirm():
                    db = get_session()
                    try:
                        for pid in list(bulk_selected):
                            prod = db.query(Product).filter(Product.id == pid).first()
                            if prod:
                                db.delete(prod)
                        db.commit()
                    finally:
                        db.close()
                    bulk_selected.clear()
                    _update_bulk_bar()
                    dialog.close()
                    refresh_products()

                with ui.dialog() as dialog, ui.card():
                    ui.label(f"Delete {len(bulk_selected)} products?").classes(
                        "text-subtitle1 font-bold"
                    )
                    ui.label(
                        "This will permanently delete the selected products "
                        "and all their research data."
                    ).classes("text-body2 text-secondary")
                    with ui.row().classes("justify-end gap-2 mt-4"):
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                        ui.button("Delete All", on_click=confirm).props("color=negative")
                dialog.open()

            bulk_research_btn.on_click(_bulk_research)
            bulk_delete_btn.on_click(_bulk_delete)

            # --- Count label + view toggle ---
            with ui.row().classes("w-full items-center justify-between"):
                count_label = ui.label("").classes("text-body2 text-secondary")
                view_toggle = ui.toggle(
                    {False: "Grid", True: "Table"},
                    value=False,
                ).props("dense flat toggle-color=primary size=sm")

            # Persist view toggle in localStorage
            async def _load_saved_view():
                try:
                    result = await ui.run_javascript(
                        'localStorage.getItem("verlumen_view_toggle")'
                    )
                    if result is not None:
                        view_toggle.value = result == "true"
                except RuntimeError:
                    pass

            ui.timer(0.1, _load_saved_view, once=True)

            def _persist_view(e):
                ui.run_javascript(
                    f'localStorage.setItem("verlumen_view_toggle", "{str(view_toggle.value).lower()}")'
                )

            view_toggle.on_value_change(_persist_view)

            # --- Pagination state ---
            _page_state = {"current": 1, "size": 20, "total": 0}

            with ui.row().classes("w-full items-center gap-3"):
                page_size_select = ui.select(
                    {10: "10 / page", 20: "20 / page", 50: "50 / page", 100: "100 / page"},
                    value=20,
                    label="Per page",
                ).props("outlined dense").classes("w-36")
                pagination_label = ui.label("").classes("text-body2 text-secondary flex-1")
                prev_btn = ui.button(icon="chevron_left").props("flat dense round")
                page_num_label = ui.label("1").classes("text-body2 font-bold")
                next_btn = ui.button(icon="chevron_right").props("flat dense round")

            def _go_prev():
                if _page_state["current"] > 1:
                    _page_state["current"] -= 1
                    refresh_products()

            def _go_next():
                total_pages = max(1, (_page_state["total"] + _page_state["size"] - 1) // _page_state["size"])
                if _page_state["current"] < total_pages:
                    _page_state["current"] += 1
                    refresh_products()

            def _on_page_size_change(_):
                _page_state["size"] = page_size_select.value
                _page_state["current"] = 1
                refresh_products()

            prev_btn.on_click(_go_prev)
            next_btn.on_click(_go_next)
            page_size_select.on_value_change(_on_page_size_change)

            # --- Product container ---
            product_container = ui.column().classes("w-full gap-2")

            def _get_comp_counts(db) -> dict[int, int]:
                """Batch-load competitor counts for all products in a single query."""
                rows = (
                    db.query(
                        AmazonCompetitor.product_id,
                        func.count(AmazonCompetitor.id),
                    )
                    .group_by(AmazonCompetitor.product_id)
                    .all()
                )
                return {pid: cnt for pid, cnt in rows}

            def _get_filtered_products(db, comp_counts: dict[int, int] | None = None):
                """Query and filter products based on current filter state."""
                if comp_counts is None:
                    comp_counts = _get_comp_counts(db)

                query = db.query(Product).options(
                    joinedload(Product.category),
                    joinedload(Product.search_sessions),
                )

                # Category filter
                if filter_select.value != "All":
                    cat = db.query(Category).filter_by(name=filter_select.value).first()
                    if cat:
                        query = query.filter(Product.category_id == cat.id)

                # Profit data filter (at DB level)
                if profit_filter.value == "Has Profit Data":
                    query = query.filter(Product.alibaba_price_min.isnot(None))
                elif profit_filter.value == "No Profit Data":
                    query = query.filter(Product.alibaba_price_min.is_(None))

                products = query.all()

                # Search filter (name substring, case-insensitive)
                search_term = (search_input.value or "").strip().lower()
                if search_term:
                    products = [p for p in products if search_term in p.name.lower()]

                # Research status filter
                if status_select.value == "Researched":
                    products = [p for p in products if len(p.search_sessions) > 0]
                elif status_select.value == "Pending":
                    products = [p for p in products if len(p.search_sessions) == 0]

                # Competitor count range filter (using batch-loaded counts)
                comp_val = comp_range_filter.value
                if comp_val != "All":
                    if comp_val == "0":
                        products = [p for p in products if comp_counts.get(p.id, 0) == 0]
                    elif comp_val == "1-10":
                        products = [p for p in products if 1 <= comp_counts.get(p.id, 0) <= 10]
                    elif comp_val == "10-50":
                        products = [p for p in products if 10 < comp_counts.get(p.id, 0) <= 50]
                    elif comp_val == "50+":
                        products = [p for p in products if comp_counts.get(p.id, 0) > 50]

                # Sort
                sort_val = sort_select.value
                if sort_val == "Name (A-Z)":
                    products.sort(key=lambda p: p.name.lower())
                elif sort_val == "Name (Z-A)":
                    products.sort(key=lambda p: p.name.lower(), reverse=True)
                elif sort_val == "Newest first":
                    products.sort(key=lambda p: p.created_at or p.id, reverse=True)
                elif sort_val == "Most competitors":
                    products.sort(
                        key=lambda p: comp_counts.get(p.id, 0),
                        reverse=True,
                    )
                elif sort_val == "Best Opportunity":
                    def _opp_score(p):
                        if p.search_sessions:
                            latest = p.search_sessions[-1]
                            return -(latest.avg_reviews or 0)
                        return 0
                    products.sort(key=_opp_score)
                elif sort_val == "Category":
                    products.sort(key=lambda p: (p.category.name if p.category else "", p.name.lower()))

                return products

            def _render_product_card(p, comp_count, session_count, db):
                """Render a single product as a card in the grid."""
                is_researched = session_count > 0

                with ui.card().classes("w-full p-4"):
                    # Bulk checkbox row
                    with ui.row().classes("items-start w-full gap-3"):
                        with ui.element("div").on("click.stop", lambda e: None):
                            cb = ui.checkbox(
                                value=p.id in bulk_selected,
                                on_change=lambda e, pid=p.id: _on_bulk_checkbox(pid, e.value),
                            )
                            bulk_checkboxes[p.id] = cb

                        # Clickable area for navigation
                        with ui.column().classes("flex-1 gap-2 cursor-pointer").on(
                            "click",
                            lambda _, pid=p.id: ui.navigate.to(f"/products/{pid}"),
                        ):
                            # Top row: thumbnail + name + link
                            with ui.row().classes("items-start w-full gap-3"):
                                # Thumbnail / avatar
                                img_src = _product_image_src(p)
                                if img_src:
                                    ui.image(img_src).classes(
                                        "w-16 h-16 rounded object-cover"
                                    ).style("min-width:64px")
                                else:
                                    letter = p.name[0].upper() if p.name else "?"
                                    bg = _avatar_color(p.name)
                                    ui.avatar(
                                        letter, color=bg, text_color="white", size="64px",
                                    )

                                with ui.column().classes("flex-1 gap-1"):
                                    ui.label(p.name).classes("text-subtitle1 font-bold")
                                    if p.alibaba_supplier:
                                        ui.label(f"Supplier: {p.alibaba_supplier}").classes(
                                            "text-caption text-secondary"
                                        )
                                    with ui.row().classes("gap-2 items-center flex-wrap"):
                                        ui.badge(
                                            p.category.name if p.category else "",
                                            color="blue-2",
                                        ).props("outline")
                                        _st = getattr(p, "status", None) or "imported"
                                        ui.badge(
                                            _STATUS_LABELS.get(_st, _st.replace("_", " ").title()),
                                            color=_STATUS_COLORS.get(_st, "grey-5"),
                                        )

                            # Stats row
                            with ui.row().classes("w-full gap-4 items-center"):
                                ui.label(
                                    f"{comp_count} competitor{'s' if comp_count != 1 else ''}"
                                ).classes("text-caption text-secondary")

                                if is_researched:
                                    latest = p.search_sessions[-1]
                                    if latest.avg_price is not None:
                                        ui.label(f"Avg ${latest.avg_price:.2f}").classes(
                                            "text-caption text-positive"
                                        )
                                    if latest.avg_rating is not None:
                                        ui.label(f"Rating {latest.avg_rating:.1f}").classes(
                                            "text-caption text-secondary"
                                        )

                                price = _format_price(p.alibaba_price_min, p.alibaba_price_max)
                                if price != "-":
                                    ui.label(price).classes("text-caption text-positive")

                        # Actions column
                        with ui.column().classes("gap-1"):
                            if p.alibaba_url:
                                with ui.link(
                                    target=p.alibaba_url, new_tab=True,
                                ).classes("no-underline").on(
                                    "click.stop", lambda e: None,
                                ):
                                    ui.button(icon="open_in_new").props(
                                        "flat round dense color=primary size=sm"
                                    ).tooltip("Open on Alibaba")
                            with ui.element("div").on("click.stop", lambda e: None):
                                _delete_button(p.id, p.name, refresh_products)

            def _render_product_row(p, comp_count, session_count, db):
                """Render a single product as a row in the table view."""
                is_researched = session_count > 0
                price = _format_price(p.alibaba_price_min, p.alibaba_price_max)

                with ui.card().classes("w-full p-3"):
                    with ui.row().classes("items-center w-full gap-4"):
                        # Bulk checkbox
                        cb = ui.checkbox(
                            value=p.id in bulk_selected,
                            on_change=lambda e, pid=p.id: _on_bulk_checkbox(pid, e.value),
                        )
                        bulk_checkboxes[p.id] = cb

                        with ui.row().classes(
                            "items-center flex-1 gap-4 cursor-pointer"
                        ).on(
                            "click",
                            lambda _, pid=p.id: ui.navigate.to(f"/products/{pid}"),
                        ):
                            # Thumbnail / avatar
                            img_src = _product_image_src(p)
                            if img_src:
                                ui.image(img_src).classes(
                                    "w-10 h-10 rounded object-cover"
                                )
                            else:
                                letter = p.name[0].upper() if p.name else "?"
                                bg = _avatar_color(p.name)
                                ui.avatar(
                                    letter, color=bg, text_color="white", size="40px",
                                )

                            with ui.column().classes("flex-1 gap-0"):
                                ui.label(p.name).classes("text-subtitle2 font-bold")
                                if p.alibaba_supplier:
                                    ui.label(f"Supplier: {p.alibaba_supplier}").classes(
                                        "text-caption text-secondary"
                                    )
                                with ui.row().classes("gap-2 items-center"):
                                    ui.badge(
                                        p.category.name if p.category else "",
                                        color="blue-2",
                                    ).props("outline")
                                    _st = getattr(p, "status", None) or "imported"
                                    ui.badge(
                                        _STATUS_LABELS.get(_st, _st.replace("_", " ").title()),
                                        color=_STATUS_COLORS.get(_st, "grey-5"),
                                    )
                                    ui.label(
                                        f"{comp_count} competitor{'s' if comp_count != 1 else ''}"
                                    ).classes("text-caption text-secondary")

                            ui.label(price).classes(
                                "text-body2 text-right"
                                + (" text-positive" if price != "-" else " text-secondary")
                            ).style("min-width:100px")

                        if p.alibaba_url:
                            with ui.link(
                                target=p.alibaba_url, new_tab=True,
                            ).classes("no-underline"):
                                ui.button(icon="open_in_new").props(
                                    "flat round dense color=primary size=sm"
                                ).tooltip("Open on Alibaba")
                        else:
                            ui.icon("link_off").classes("text-grey-5").tooltip(
                                "No Alibaba URL"
                            )

                        _delete_button(p.id, p.name, refresh_products)

            def refresh_products():
                bulk_checkboxes.clear()
                product_container.clear()
                db = get_session()
                try:
                    total_count = db.query(Product).count()
                    comp_counts = _get_comp_counts(db)
                    all_filtered = _get_filtered_products(db, comp_counts)
                    filtered_count = len(all_filtered)

                    # Pagination
                    page_size = _page_state["size"]
                    _page_state["total"] = filtered_count
                    total_pages = max(1, (filtered_count + page_size - 1) // page_size)
                    if _page_state["current"] > total_pages:
                        _page_state["current"] = total_pages
                    current_page = _page_state["current"]
                    start = (current_page - 1) * page_size
                    end = start + page_size
                    products = all_filtered[start:end]

                    count_label.text = f"Showing {start + 1}-{min(end, filtered_count)} of {filtered_count} products ({total_count} total)"
                    pagination_label.text = f"Page {current_page} of {total_pages}"
                    page_num_label.text = str(current_page)
                    prev_btn.set_enabled(current_page > 1)
                    next_btn.set_enabled(current_page < total_pages)

                    with product_container:
                        if not products:
                            ui.label("No products match your filters.").classes(
                                "text-body2 text-secondary"
                            )
                            return

                        is_table = view_toggle.value

                        if is_table:
                            for p in products:
                                comp_count = comp_counts.get(p.id, 0)
                                session_count = len(p.search_sessions)
                                _render_product_row(p, comp_count, session_count, db)
                        else:
                            with ui.element("div").classes(
                                "w-full grid gap-4"
                            ).style(
                                "grid-template-columns: repeat(auto-fill, minmax(320px, 1fr))"
                            ):
                                for p in products:
                                    comp_count = comp_counts.get(p.id, 0)
                                    session_count = len(p.search_sessions)
                                    _render_product_card(p, comp_count, session_count, db)
                finally:
                    db.close()

            # Wire up all filter controls to refresh (reset to page 1)
            def _filter_and_reset(_=None):
                _page_state["current"] = 1
                refresh_products()

            _search_timer = {"ref": None}

            def _debounced_search(_):
                if _search_timer["ref"] is not None:
                    _search_timer["ref"].cancel()
                _search_timer["ref"] = ui.timer(
                    0.3, lambda: _filter_and_reset(), once=True,
                )

            search_input.on("input", _debounced_search)
            filter_select.on_value_change(_filter_and_reset)
            status_select.on_value_change(_filter_and_reset)
            profit_filter.on_value_change(_filter_and_reset)
            comp_range_filter.on_value_change(_filter_and_reset)
            sort_select.on_value_change(lambda _: refresh_products())
            view_toggle.on_value_change(lambda _: refresh_products())

            refresh_products()
        finally:
            session.close()


def _delete_button(product_id: int, product_name: str, on_deleted):
    """Render a delete icon button with confirmation dialog."""

    def show_confirm():
        with ui.dialog() as dialog, ui.card():
            ui.label(f'Delete "{product_name}"?').classes("text-subtitle1 font-bold")
            ui.label(
                "Are you sure you want to delete this product? "
                "This will also delete all associated Amazon research data."
            ).classes("text-body2 text-secondary")
            with ui.row().classes("justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                def confirm_delete():
                    db = get_session()
                    try:
                        prod = db.query(Product).filter(Product.id == product_id).first()
                        if prod:
                            db.delete(prod)
                            db.commit()
                    finally:
                        db.close()
                    dialog.close()
                    on_deleted()

                ui.button("Delete", on_click=confirm_delete).props("color=negative")
        dialog.open()

    ui.button(icon="delete", on_click=show_confirm).props(
        "flat round dense color=negative size=sm"
    ).tooltip("Delete product")


