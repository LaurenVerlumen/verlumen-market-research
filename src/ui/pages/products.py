"""Products page -- browse and manage imported products."""
from nicegui import ui

from src.models import get_session, init_db, Category, Product, AmazonCompetitor
from src.services import parse_alibaba_url
from src.ui.layout import build_layout


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

                        for p in products:
                            comp_count = db.query(AmazonCompetitor).filter_by(product_id=p.id).count()
                            price = _format_price(p.alibaba_price_min, p.alibaba_price_max)

                            with ui.card().classes("w-full p-3"):
                                with ui.row().classes("items-center w-full gap-4"):
                                    # Clickable area: thumbnail + info + price
                                    with ui.row().classes(
                                        "items-center flex-1 gap-4 cursor-pointer"
                                    ).on(
                                        "click",
                                        lambda _, pid=p.id: ui.navigate.to(f"/products/{pid}"),
                                    ):
                                        # Thumbnail / avatar
                                        if p.alibaba_image_url:
                                            ui.image(p.alibaba_image_url).classes(
                                                "w-10 h-10 rounded object-cover"
                                            )
                                        else:
                                            letter = p.name[0].upper() if p.name else "?"
                                            bg = _avatar_color(p.name)
                                            ui.avatar(
                                                letter, color=bg, text_color="white", size="40px",
                                            )

                                        # Product info
                                        with ui.column().classes("flex-1 gap-0"):
                                            ui.label(p.name).classes("text-subtitle2 font-bold")
                                            with ui.row().classes("gap-2 items-center"):
                                                ui.badge(
                                                    p.category.name if p.category else "",
                                                    color="blue-2",
                                                ).props("outline")
                                                ui.label(
                                                    f"{comp_count} competitor{'s' if comp_count != 1 else ''}"
                                                ).classes("text-caption text-secondary")

                                        # Price
                                        ui.label(price).classes(
                                            "text-body2 text-right"
                                            + (" text-positive" if price != "-" else " text-secondary")
                                        ).style("min-width:100px")

                                    # Alibaba link
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

                                    # Delete button
                                    _delete_button(p.id, p.name, refresh_products)
                finally:
                    db.close()

            filter_select.on_value_change(lambda _: refresh_products())
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
