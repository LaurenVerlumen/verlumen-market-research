"""Products page -- browse and manage imported products."""
import asyncio

from nicegui import ui
from sqlalchemy.orm import joinedload

from config import SERPAPI_KEY
from src.models import get_session, init_db, Category, Product, AmazonCompetitor, SearchSession
from src.services import parse_alibaba_url, ImageFetcher, download_image
from src.ui.layout import build_layout


def _product_image_src(product) -> str | None:
    """Return the best image source URL for a product (local preferred)."""
    if product.local_image_path:
        return f"/images/{product.local_image_path}"
    if product.alibaba_image_url:
        return product.alibaba_image_url
    return None


# Predefined palette for letter-avatar backgrounds
_AVATAR_COLORS = [
    "#E57373", "#F06292", "#BA68C8", "#9575CD", "#7986CB",
    "#64B5F6", "#4FC3F7", "#4DD0E1", "#4DB6AC", "#81C784",
    "#AED581", "#DCE775", "#FFD54F", "#FFB74D", "#FF8A65",
    "#A1887F", "#90A4AE",
]


def _avatar_color(name: str) -> str:
    """Return a deterministic color based on the first letter of *name*."""
    idx = ord(name[0].upper()) % len(_AVATAR_COLORS) if name else 0
    return _AVATAR_COLORS[idx]


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

                sort_select = ui.select(
                    ["Name (A-Z)", "Name (Z-A)", "Newest first", "Most competitors", "Category"],
                    value="Name (A-Z)",
                    label="Sort by",
                ).props("outlined dense").classes("w-48")

                ui.space()

                # Fetch Images button (image-fetcher feature)
                fetch_btn = ui.button(
                    "Fetch Product Images", icon="image_search",
                ).props("color=secondary outline")
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

            # --- Count label + view toggle ---
            with ui.row().classes("w-full items-center justify-between"):
                count_label = ui.label("").classes("text-body2 text-secondary")
                view_toggle = ui.toggle(
                    {False: "Grid", True: "Table"},
                    value=False,
                ).props("dense flat toggle-color=primary size=sm")

            # --- Product container ---
            product_container = ui.column().classes("w-full gap-2")

            def _get_filtered_products(db):
                """Query and filter products based on current filter state."""
                query = db.query(Product).options(
                    joinedload(Product.category),
                    joinedload(Product.search_sessions),
                )

                # Category filter
                if filter_select.value != "All":
                    cat = db.query(Category).filter_by(name=filter_select.value).first()
                    if cat:
                        query = query.filter(Product.category_id == cat.id)

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
                        key=lambda p: db.query(AmazonCompetitor).filter_by(product_id=p.id).count(),
                        reverse=True,
                    )
                elif sort_val == "Category":
                    products.sort(key=lambda p: (p.category.name if p.category else "", p.name.lower()))

                return products

            def _render_product_card(p, comp_count, session_count, db):
                """Render a single product as a card in the grid."""
                is_researched = session_count > 0

                with ui.card().classes("w-full p-4 cursor-pointer").on(
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
                                if is_researched:
                                    ui.badge("Researched", color="positive")
                                else:
                                    ui.badge("Pending", color="grey-5")

                        # Alibaba link (stop propagation so card click doesn't fire)
                        if p.alibaba_url:
                            with ui.link(
                                target=p.alibaba_url, new_tab=True,
                            ).classes("no-underline").on(
                                "click.stop", lambda e: None,
                            ):
                                ui.button(icon="open_in_new").props(
                                    "flat round dense color=primary size=sm"
                                ).tooltip("Open on Alibaba")

                    # Stats row
                    with ui.row().classes("w-full gap-4 mt-2 items-center"):
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

                        ui.space()
                        # Delete button (stop card click propagation)
                        with ui.element("div").on("click.stop", lambda e: None):
                            _delete_button(p.id, p.name, refresh_products)

            def _render_product_row(p, comp_count, session_count, db):
                """Render a single product as a row in the table view."""
                is_researched = session_count > 0
                price = _format_price(p.alibaba_price_min, p.alibaba_price_max)

                with ui.card().classes("w-full p-3"):
                    with ui.row().classes("items-center w-full gap-4"):
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
                                    if is_researched:
                                        ui.badge("Researched", color="positive")
                                    else:
                                        ui.badge("Pending", color="grey-5")
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
                product_container.clear()
                db = get_session()
                try:
                    total_count = db.query(Product).count()
                    products = _get_filtered_products(db)
                    count_label.text = f"Showing {len(products)} of {total_count} products"

                    with product_container:
                        if not products:
                            ui.label("No products match your filters.").classes(
                                "text-body2 text-secondary"
                            )
                            return

                        is_table = view_toggle.value

                        if is_table:
                            for p in products:
                                comp_count = db.query(AmazonCompetitor).filter_by(product_id=p.id).count()
                                session_count = len(p.search_sessions)
                                _render_product_row(p, comp_count, session_count, db)
                        else:
                            with ui.element("div").classes(
                                "w-full grid gap-4"
                            ).style(
                                "grid-template-columns: repeat(auto-fill, minmax(320px, 1fr))"
                            ):
                                for p in products:
                                    comp_count = db.query(AmazonCompetitor).filter_by(product_id=p.id).count()
                                    session_count = len(p.search_sessions)
                                    _render_product_card(p, comp_count, session_count, db)
                finally:
                    db.close()

            # Wire up all filter controls to refresh
            search_input.on("input", lambda _: refresh_products())
            filter_select.on_value_change(lambda _: refresh_products())
            status_select.on_value_change(lambda _: refresh_products())
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


def _format_price(pmin, pmax) -> str:
    if pmin is not None and pmax is not None:
        return f"${pmin:.2f} - ${pmax:.2f}"
    if pmin is not None:
        return f"${pmin:.2f}"
    if pmax is not None:
        return f"${pmax:.2f}"
    return "-"
