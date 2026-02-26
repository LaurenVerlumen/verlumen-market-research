"""Products page -- browse and manage imported products."""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from nicegui import ui
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from config import (
    BASE_DIR, SERPAPI_KEY,
    SP_API_REFRESH_TOKEN,
    AMAZON_MARKETPLACES,
)
from src.models import get_session, init_db, Category, Product, AmazonCompetitor, SearchSession
from src.services import (
    parse_alibaba_url, parse_excel, ImageFetcher, download_image,
    AmazonSearchService, AmazonSearchError, CompetitionAnalyzer,
    get_search_context,
)
from src.services.match_scorer import score_matches
from src.services.query_optimizer import optimize_query
from src.ui.components.helpers import (
    avatar_color as _avatar_color, product_image_src as _product_image_src,
    format_price as _format_price, STATUS_COLORS as _STATUS_COLORS, STATUS_LABELS as _STATUS_LABELS,
    page_header,
)
from src.ui.layout import build_layout

logger = logging.getLogger(__name__)

# Default Excel file path (for import feature)
_DEFAULT_EXCEL = BASE_DIR / "verlumen-Product Research.xlsx"


def products_page(
    category: str | None = None,
    category_id: int | None = None,
    search: str | None = None,
):
    """Render the products browser page.

    Args:
        category: Optional category name for backward compat (from URL query param).
        category_id: Optional category ID to pre-filter by (from URL query param).
        search: Optional search term to pre-fill the search input (from URL query param).
    """
    content = build_layout()

    # Resolve category name to ID for backward compat
    _active_cat_id = category_id
    _active_cat_path = None
    if category and not _active_cat_id:
        _resolve_db = get_session()
        try:
            _cat_obj = _resolve_db.query(Category).filter_by(name=category).first()
            if _cat_obj:
                _active_cat_id = _cat_obj.id
        finally:
            _resolve_db.close()

    # Look up category path for header display
    if _active_cat_id:
        _path_db = get_session()
        try:
            _cat_obj = _path_db.query(Category).filter_by(id=_active_cat_id).first()
            if _cat_obj:
                _active_cat_path = _cat_obj.get_path()
        finally:
            _path_db.close()

    with content:
        if _active_cat_path:
            with ui.row().classes("items-center gap-3"):
                ui.button(
                    icon="arrow_back", on_click=lambda: ui.navigate.to("/products"),
                ).props("flat round size=sm")
                ui.label(_active_cat_path).classes("text-h5 font-bold")
            ui.label(f"Products in {_active_cat_path}").classes(
                "text-body2 text-secondary"
            )
        else:
            page_header("Products", subtitle="Browse and manage your products.", icon="inventory_2")

        # ===================================================================
        # Import from Excel section (merged from import_page.py)
        # ===================================================================
        with ui.expansion("Import from Excel", icon="upload_file").classes("w-full mb-4"):
            import_status_container = ui.column().classes("w-full gap-2")
            import_results_container = ui.column().classes("w-full gap-2")

            def _do_import(data: list[dict]):
                """Import parsed Excel data into the database."""
                init_db()
                session = get_session()
                total_products = 0
                skipped_names: list[str] = []
                imported_names: list[str] = []

                try:
                    for group in data:
                        cat_name = group["category"]
                        category = session.query(Category).filter(Category.name == cat_name).first()
                        if not category:
                            category = Category(name=cat_name)
                            session.add(category)
                            session.flush()

                        for prod in group["products"]:
                            existing = session.query(Product).filter(
                                Product.alibaba_url == prod["url"]
                            ).first()
                            if existing and existing.status == "rejected":
                                # Re-import rejected product
                                existing.name = prod["name"]
                                existing.category_id = category.id
                                existing.status = "imported"
                                existing.amazon_search_query = prod["name"]
                                existing.alibaba_product_id = prod.get("product_id")
                                existing.alibaba_supplier = prod.get("supplier")
                                existing.decision_log = "[]"
                                imported_names.append(prod["name"])
                                total_products += 1
                                continue
                            elif existing:
                                skipped_names.append(prod["name"])
                                continue

                            product = Product(
                                category_id=category.id,
                                alibaba_url=prod["url"],
                                alibaba_product_id=prod.get("product_id"),
                                name=prod["name"],
                                amazon_search_query=prod["name"],
                                alibaba_supplier=prod.get("supplier"),
                            )
                            session.add(product)
                            imported_names.append(prod["name"])
                            total_products += 1

                    session.commit()
                except Exception as e:
                    session.rollback()
                    with import_status_container:
                        ui.label(f"Error during import: {e}").classes("text-negative")
                    return
                finally:
                    session.close()

                import_results_container.clear()
                with import_results_container:
                    ui.label("Import complete!").classes("text-subtitle1 font-bold text-positive")
                    with ui.row().classes("gap-4"):
                        ui.label(f"Categories: {len(data)}").classes("text-body2")
                        ui.label(f"Products imported: {total_products}").classes(
                            "text-body2 text-positive"
                        )
                        if skipped_names:
                            ui.label(
                                f"Skipped (duplicates): {len(skipped_names)}"
                            ).classes("text-body2 text-warning")

                    if imported_names:
                        with ui.expansion(
                            f"New products ({len(imported_names)})", icon="check_circle",
                        ).classes("w-full").props("default-opened"):
                            for name in imported_names:
                                with ui.row().classes("items-center gap-1 ml-4"):
                                    ui.icon("check_circle", size="xs").classes("text-positive")
                                    ui.label(name).classes("text-body2")

                    if skipped_names:
                        with ui.expansion(
                            f"Skipped duplicates ({len(skipped_names)})", icon="content_copy",
                        ).classes("w-full"):
                            for name in skipped_names:
                                with ui.row().classes("items-center gap-1 ml-4"):
                                    ui.icon("block", size="xs").classes("text-warning")
                                    ui.label(name).classes("text-body2 text-secondary")

                # Refresh the product listing
                try:
                    refresh_products()
                except Exception:
                    pass
                ui.notify(
                    f"Imported {total_products} product(s).",
                    type="positive",
                )

            # Import default file button
            file_exists = _DEFAULT_EXCEL.exists()
            if file_exists:
                ui.label(f"Default file: {_DEFAULT_EXCEL.name}").classes(
                    "text-body2 text-secondary mb-2"
                )

                def _import_default():
                    import_status_container.clear()
                    import_results_container.clear()
                    with import_status_container:
                        ui.label("Parsing Excel file...").classes("text-body2 text-primary")
                    try:
                        data = parse_excel(str(_DEFAULT_EXCEL))
                        import_status_container.clear()
                        _do_import(data)
                    except Exception as e:
                        import_status_container.clear()
                        with import_status_container:
                            ui.label(f"Error parsing file: {e}").classes("text-negative")

                ui.button(
                    "Import Default Spreadsheet", icon="upload_file",
                    on_click=_import_default,
                ).props("color=primary")
            else:
                ui.label(
                    f"Default file not found at: {_DEFAULT_EXCEL}"
                ).classes("text-body2 text-warning")

            ui.separator().classes("my-2")

            # Upload custom file
            ui.label("Or upload an Excel file").classes("text-subtitle2 font-bold mb-1")

            async def _handle_upload(e):
                import_status_container.clear()
                import_results_container.clear()
                with import_status_container:
                    ui.label("Parsing uploaded file...").classes("text-body2 text-primary")
                try:
                    file_content = await e.file.read()
                    data = parse_excel(file_content)
                    import_status_container.clear()
                    _do_import(data)
                except Exception as exc:
                    import_status_container.clear()
                    with import_status_container:
                        ui.label(f"Error parsing upload: {exc}").classes("text-negative")

            ui.upload(
                label="Choose Excel file",
                auto_upload=True,
                on_upload=_handle_upload,
            ).props('accept=".xlsx" max-file-size=10485760').classes("w-full")

        # ===================================================================
        # Add Product Manually section
        # ===================================================================
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
                        if existing and existing.status == "rejected":
                            feedback_label.text = f"Previously rejected — will re-import: {existing.name}"
                            feedback_label.classes(add="text-info")
                        elif existing:
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

                    # If it exists and is NOT rejected, block
                    if existing and existing.status != "rejected":
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

                    if existing and existing.status == "rejected":
                        # Re-import: reset the rejected product
                        existing.name = name
                        existing.category_id = cat_id
                        existing.status = "imported"
                        existing.amazon_search_query = name
                        existing.alibaba_product_id = info.get("product_id")
                        existing.decision_log = "[]"
                        db.commit()
                        feedback_label.text = f"Re-imported (was rejected): {name}"
                    else:
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
            categories = (
                session.query(Category)
                .order_by(Category.sort_order, Category.name)
                .all()
            )
            if not categories:
                ui.label(
                    "No products imported yet. Go to Import Data to get started."
                ).classes("text-body1 text-secondary")
                return

            # --- Search bar ---
            search_input = ui.input(
                label="Search products",
                placeholder="Type to filter by name...",
                value=search or "",
            ).props('clearable outlined dense').classes("w-full")
            search_input.props('prepend-inner-icon="search"')

            # --- Filter Presets ---
            _BUILTIN_PRESETS = {
                "All Products": {
                    "category": "all", "status": "All", "profit": "All",
                    "comp_range": "All", "sort": "Name (A-Z)",
                },
                "High Opportunity": {
                    "category": "all", "status": "Researched", "profit": "All",
                    "comp_range": "All", "sort": "Best Opportunity",
                },
                "Needs Research": {
                    "category": "all", "status": "Imported", "profit": "All",
                    "comp_range": "All", "sort": "Newest first",
                },
                "Approved Winners": {
                    "category": "all", "status": "Approved", "profit": "All",
                    "comp_range": "All", "sort": "Best Opportunity",
                },
            }
            _BUILTIN_NAMES = list(_BUILTIN_PRESETS.keys())

            # State to track user presets loaded from localStorage
            _user_presets: dict[str, dict] = {}
            # Flag to suppress preset clearing when we programmatically set filters
            _applying_preset = {"active": False}

            def _all_preset_options():
                opts = list(_BUILTIN_NAMES)
                for name in _user_presets:
                    opts.append(name)
                return opts

            with ui.row().classes("w-full items-center gap-3"):
                preset_select = ui.select(
                    options=_all_preset_options(),
                    value=None,
                    label="Preset",
                    clearable=True,
                ).props("outlined dense").classes("w-56")

                def _save_preset_dialog():
                    with ui.dialog() as dlg, ui.card().classes("w-80"):
                        ui.label("Save Filter Preset").classes("text-subtitle1 font-bold")
                        preset_name_input = ui.input(
                            label="Preset name",
                            placeholder="My custom filter...",
                        ).classes("w-full")

                        async def _do_save():
                            name = (preset_name_input.value or "").strip()
                            if not name:
                                ui.notify("Please enter a name.", type="warning")
                                return
                            if name in _BUILTIN_NAMES:
                                ui.notify("Cannot overwrite a built-in preset.", type="negative")
                                return
                            filters = {
                                "category": filter_select.value,
                                "status": status_select.value,
                                "profit": profit_filter.value,
                                "comp_range": comp_range_filter.value,
                                "sort": sort_select.value,
                            }
                            _user_presets[name] = filters
                            # Persist to localStorage
                            presets_list = [
                                {"name": n, "filters": f} for n, f in _user_presets.items()
                            ]
                            await ui.run_javascript(
                                f'localStorage.setItem("verlumen_filter_presets", {json.dumps(json.dumps(presets_list))})'
                            )
                            preset_select.options = _all_preset_options()
                            preset_select.update()
                            preset_select.value = name
                            dlg.close()
                            ui.notify(f'Preset "{name}" saved.', type="positive")

                        with ui.row().classes("justify-end gap-2 mt-3"):
                            ui.button("Cancel", on_click=dlg.close).props("flat")
                            ui.button("Save", icon="save", on_click=_do_save).props("color=primary")
                    dlg.open()

                ui.button(icon="bookmark_add", on_click=_save_preset_dialog).props(
                    "flat dense round"
                ).tooltip("Save current filters as preset")

                preset_delete_btn = ui.button(icon="delete").props(
                    "flat dense round color=negative"
                ).tooltip("Delete selected preset")
                preset_delete_btn.set_visibility(False)

                async def _delete_selected_preset():
                    name = preset_select.value
                    if not name or name in _BUILTIN_NAMES:
                        return
                    _user_presets.pop(name, None)
                    presets_list = [
                        {"name": n, "filters": f} for n, f in _user_presets.items()
                    ]
                    await ui.run_javascript(
                        f'localStorage.setItem("verlumen_filter_presets", {json.dumps(json.dumps(presets_list))})'
                    )
                    preset_select.value = None
                    preset_select.options = _all_preset_options()
                    preset_select.update()
                    preset_delete_btn.set_visibility(False)
                    ui.notify(f'Preset "{name}" deleted.', type="info")

                preset_delete_btn.on_click(_delete_selected_preset)

            def _apply_preset(e):
                name = preset_select.value
                if not name:
                    preset_delete_btn.set_visibility(False)
                    return
                # Show delete button only for user presets
                preset_delete_btn.set_visibility(name not in _BUILTIN_NAMES)
                # Get filter values
                filters = _BUILTIN_PRESETS.get(name) or _user_presets.get(name)
                if not filters:
                    return
                _applying_preset["active"] = True
                filter_select.value = filters.get("category", "All")
                status_select.value = filters.get("status", "All")
                profit_filter.value = filters.get("profit", "All")
                comp_range_filter.value = filters.get("comp_range", "All")
                sort_select.value = filters.get("sort", "Name (A-Z)")
                _applying_preset["active"] = False
                _page_state["current"] = 1
                refresh_products()

            preset_select.on_value_change(_apply_preset)

            async def _load_user_presets():
                """Load saved user presets from localStorage on page load."""
                try:
                    raw = await ui.run_javascript(
                        'localStorage.getItem("verlumen_filter_presets")'
                    )
                    if raw:
                        presets_list = json.loads(raw)
                        for item in presets_list:
                            _user_presets[item["name"]] = item["filters"]
                        preset_select.options = _all_preset_options()
                        preset_select.update()
                except Exception:
                    pass

            ui.timer(0.1, _load_user_presets, once=True)

            # --- Filter row ---
            with ui.row().classes("w-full items-center gap-4 flex-wrap"):
                # Build hierarchical category options with product counts
                _total_products = session.query(Product).filter(Product.status != "deleted").count()
                _cat_options = {"all": f"All Categories ({_total_products})"}

                # Product counts per category (exclude deleted)
                _cat_prod_counts = dict(
                    session.query(Product.category_id, func.count(Product.id))
                    .filter(Product.status != "deleted")
                    .group_by(Product.category_id)
                    .all()
                )

                def _cat_total_count(cat):
                    """Own + descendant product count."""
                    total = _cat_prod_counts.get(cat.id, 0)
                    for child in cat.children:
                        total += _cat_total_count(child)
                    return total

                def _build_cat_options(cats, depth=0):
                    for c in cats:
                        indent = "\u00A0\u00A0\u00A0\u00A0" * depth
                        count = _cat_total_count(c)
                        _cat_options[str(c.id)] = f"{indent}{c.name} ({count})"
                        _build_cat_options(c.children, depth + 1)

                roots = [c for c in categories if c.parent_id is None]
                _build_cat_options(roots)

                _initial_cat = str(_active_cat_id) if _active_cat_id else "all"
                filter_select = ui.select(
                    _cat_options, value=_initial_cat, label="Category",
                ).props("outlined dense").classes("w-56")

                status_select = ui.select(
                    ["All", "Imported", "Researched", "Under Review", "Approved", "Rejected"],
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
                        .filter(Product.status != "deleted")
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
                    all_products = db.query(Product).filter(Product.status != "deleted").all()
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
                ).props("flat dense color=secondary size=sm")
                ui.space()
                _bulk_mp_options = {d: info["label"] for d, info in AMAZON_MARKETPLACES.items()}
                bulk_marketplace_select = ui.select(
                    options=_bulk_mp_options,
                    value="amazon.com",
                    label="Marketplace",
                ).props("outlined dense").classes("w-56")
                bulk_research_btn = ui.button(
                    "Research Selected", icon="search",
                ).props("color=positive size=sm")
                bulk_delete_btn = ui.button(
                    "Delete Selected", icon="delete",
                ).props("color=negative size=sm outline")
                # --- Evaluation action buttons (merged from evaluation.py) ---
                bulk_approve_btn = ui.button(
                    "Approve Selected", icon="check_circle",
                ).props("color=positive size=sm")
                bulk_reject_btn = ui.button(
                    "Reject Selected", icon="cancel",
                ).props("color=negative size=sm outline")
                bulk_review_btn = ui.button(
                    "Mark for Review", icon="rate_review",
                ).props("color=warning size=sm outline")

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

            # ---------------------------------------------------------------
            # Bulk status change handler (merged from evaluation.py)
            # ---------------------------------------------------------------
            def _bulk_set_status(new_status: str):
                """Set the status of all selected products."""
                if not bulk_selected:
                    ui.notify("No products selected.", type="warning")
                    return
                count = len(bulk_selected)
                db = get_session()
                try:
                    for pid in list(bulk_selected):
                        p = db.query(Product).filter(Product.id == pid).first()
                        if p:
                            p.status = new_status
                    db.commit()
                finally:
                    db.close()
                bulk_selected.clear()
                _update_bulk_bar()
                refresh_products()
                ui.notify(
                    f"Updated {count} product(s) to {_STATUS_LABELS.get(new_status, new_status)}.",
                    type="positive",
                )

            bulk_approve_btn.on_click(lambda: _bulk_set_status("approved"))
            bulk_reject_btn.on_click(lambda: _bulk_set_status("rejected"))
            bulk_review_btn.on_click(lambda: _bulk_set_status("under_review"))

            # ---------------------------------------------------------------
            # Inline batch research (merged from research.py)
            # ---------------------------------------------------------------
            async def _bulk_research():
                """Run Amazon research for selected products inline with a progress dialog."""
                if not bulk_selected:
                    ui.notify("No products selected.", type="warning")
                    return

                if not SERPAPI_KEY:
                    ui.notify("SERPAPI_KEY is not configured.", type="negative")
                    return

                ids = list(bulk_selected)

                with ui.dialog() as research_dialog, ui.card().classes("w-full").style("min-width: 600px"):
                    ui.label("Research Progress").classes("text-subtitle1 font-bold mb-2")
                    progress = ui.linear_progress(value=0, show_value=False).classes("w-full")
                    with ui.row().classes("items-center gap-3 mt-1"):
                        current_thumb = ui.element("div").classes("w-10 h-10")
                        status_label = ui.label(
                            f"Starting research for {len(ids)} products..."
                        ).classes("text-body2 text-secondary")
                    log_area = ui.log(max_lines=100).classes("w-full h-64 mt-2")

                research_dialog.open()

                _selected_domain = bulk_marketplace_select.value
                search_service = AmazonSearchService(api_key=SERPAPI_KEY, amazon_domain=_selected_domain)
                analyzer = CompetitionAnalyzer()

                log_area.push(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"Starting research for {len(ids)} product(s)..."
                )
                log_area.push(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"Marketplace: {_selected_domain}"
                )

                total = len(ids)
                completed = 0
                errors = 0
                total_competitors_found = 0
                cache_hits = 0
                results: dict = {}

                for pid in ids:
                    db = get_session()
                    try:
                        product = (
                            db.query(Product)
                            .options(joinedload(Product.category))
                            .filter(Product.id == pid)
                            .first()
                        )
                        if not product:
                            completed += 1
                            progress.value = completed / total
                            continue

                        query = product.amazon_search_query or optimize_query(product.name) or product.name

                        # Resolve department + query suffix from category hierarchy
                        _ctx = get_search_context(product.category)
                        dept = _ctx["department"]
                        if _ctx["query_suffix"] and _ctx["query_suffix"].lower() not in query.lower():
                            query = f"{query} {_ctx['query_suffix']}"

                        # Update current product display
                        current_thumb.clear()
                        with current_thumb:
                            img_src = _product_image_src(product)
                            if img_src:
                                ui.image(img_src).classes("w-10 h-10 rounded object-cover")
                            else:
                                letter = product.name[0].upper() if product.name else "?"
                                ui.avatar(
                                    letter,
                                    color=_avatar_color(product.name),
                                    text_color="white",
                                    size="40px",
                                )

                        status_label.text = f"Searching ({completed + 1}/{total}): {product.name}"
                        dept_label = f" [dept: {dept}]" if dept else ""
                        log_area.push(
                            f"[{datetime.now().strftime('%H:%M:%S')}] "
                            f"Searching ({completed + 1}/{total}): {product.name}{dept_label}"
                        )

                        try:
                            # Multi-page search with caching, dedup, department filter
                            results = await asyncio.get_event_loop().run_in_executor(
                                None,
                                lambda q=query, d=dept: search_service.search_products(
                                    q, max_pages=1, amazon_department=d,
                                ),
                            )
                            all_competitors = results["competitors"]
                            analysis = await asyncio.get_event_loop().run_in_executor(
                                None, analyzer.analyze, all_competitors,
                            )

                            # Compute match scores
                            scored = await asyncio.get_event_loop().run_in_executor(
                                None,
                                lambda: score_matches(product.name, [dict(c) for c in all_competitors]),
                            )
                            score_by_asin: dict[str, float | None] = {}
                            for s in scored:
                                a = s.get("asin")
                                if a:
                                    score_by_asin[a] = s.get("match_score")

                            # SP-API brand enrichment (optional)
                            brand_data: dict[str, dict] = {}
                            if SP_API_REFRESH_TOKEN:
                                try:
                                    from src.services.sp_api_client import SPAPIClient
                                    status_label.text = (
                                        f"Enriching brand data ({completed + 1}/{total}): {product.name}"
                                    )
                                    sp_client = SPAPIClient()
                                    unique_asins = list({
                                        c.get("asin") for c in all_competitors if c.get("asin")
                                    })
                                    brand_data = await asyncio.get_event_loop().run_in_executor(
                                        None, sp_client.enrich_asins, unique_asins,
                                    )
                                    log_area.push(
                                        f"  -> Brand data enriched for {len(brand_data)} ASINs"
                                    )
                                except Exception as exc:
                                    logger.warning("SP-API enrichment failed: %s", exc)
                                    log_area.push(f"  -> SP-API enrichment skipped: {exc}")

                            if results.get("cache_hit"):
                                cache_hits += 1
                                log_area.push("  -> (cached result)")

                            comp_count = len(all_competitors)
                            total_competitors_found += comp_count

                            search_session = SearchSession(
                                product_id=product.id,
                                search_query=query,
                                amazon_domain=_selected_domain,
                                total_results=results.get(
                                    "total_results_across_pages", comp_count
                                ),
                                organic_results=results["total_organic"],
                                sponsored_results=results["total_sponsored"],
                                avg_price=analysis["price_mean"],
                                avg_rating=analysis["avg_rating"],
                                avg_reviews=analysis["avg_reviews"],
                            )
                            db.add(search_session)
                            db.flush()

                            seen_asins_in_session: set[str] = set()
                            for comp in all_competitors:
                                asin = comp.get("asin", "")
                                if asin and asin in seen_asins_in_session:
                                    continue
                                if asin:
                                    exists = (
                                        db.query(AmazonCompetitor.id)
                                        .filter(
                                            AmazonCompetitor.product_id == product.id,
                                            AmazonCompetitor.asin == asin,
                                            AmazonCompetitor.search_session_id == search_session.id,
                                        )
                                        .first()
                                    )
                                    if exists:
                                        continue
                                    seen_asins_in_session.add(asin)
                                amazon_comp = AmazonCompetitor(
                                    product_id=product.id,
                                    search_session_id=search_session.id,
                                    asin=asin,
                                    title=comp.get("title"),
                                    price=comp.get("price"),
                                    rating=comp.get("rating"),
                                    review_count=comp.get("review_count"),
                                    bought_last_month=comp.get("bought_last_month"),
                                    is_prime=comp.get("is_prime", False),
                                    badge=comp.get("badge"),
                                    thumbnail_url=comp.get("thumbnail_url"),
                                    amazon_url=comp.get("amazon_url"),
                                    is_sponsored=comp.get("is_sponsored", False),
                                    position=comp.get("position"),
                                    match_score=score_by_asin.get(asin),
                                    brand=brand_data.get(asin, {}).get("brand"),
                                    manufacturer=brand_data.get(asin, {}).get("manufacturer"),
                                )
                                db.add(amazon_comp)

                            # Auto-update product status to "researched"
                            if product.status == "imported":
                                product.status = "researched"

                            db.commit()

                            log_area.push(
                                f"  -> Found {comp_count} competitors. "
                                f"Opportunity: {analysis['opportunity_score']:.0f}/100, "
                                f"Competition: {analysis['competition_score']:.0f}/100"
                            )

                        except (AmazonSearchError, Exception) as e:
                            errors += 1
                            logger.error("Research failed for product %d: %s", pid, e)
                            log_area.push(f"  -> ERROR: {e}")
                            db.rollback()

                    finally:
                        db.close()

                    completed += 1
                    progress.value = completed / total

                    # Short sleep between products (cache hits don't need long waits)
                    if not results.get("cache_hit"):
                        await asyncio.sleep(0.5)

                # --- Research summary ---
                successful = completed - errors
                avg_comps = total_competitors_found / successful if successful > 0 else 0

                summary_text = (
                    f"Research complete! {successful}/{total} products analyzed. "
                    f"Total competitors: {total_competitors_found}, "
                    f"avg per product: {avg_comps:.0f}"
                )
                if cache_hits:
                    summary_text += f", cache hits: {cache_hits}"
                if errors:
                    summary_text += f" ({errors} errors)"

                status_label.text = summary_text
                log_area.push(
                    f"\n[{datetime.now().strftime('%H:%M:%S')}] {summary_text}"
                )

                # Close dialog, clear selection, refresh
                research_dialog.close()
                bulk_selected.clear()
                _update_bulk_bar()
                try:
                    refresh_products()
                except RuntimeError:
                    pass
                ui.notify(
                    f"Research complete! {successful}/{total} products analyzed.",
                    type="positive",
                )

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

            # Status filter value -> DB status value mapping
            _STATUS_FILTER_MAP = {
                "Imported": "imported",
                "Researched": "researched",
                "Under Review": "under_review",
                "Approved": "approved",
                "Rejected": "rejected",
            }

            def _get_filtered_products(db, comp_counts: dict[int, int] | None = None):
                """Query and filter products based on current filter state."""
                if comp_counts is None:
                    comp_counts = _get_comp_counts(db)

                query = db.query(Product).options(
                    joinedload(Product.category),
                    joinedload(Product.search_sessions),
                ).filter(Product.status != "deleted")

                # Category filter (hierarchical - includes descendant products)
                if filter_select.value != "all":
                    try:
                        cat = db.query(Category).filter_by(id=int(filter_select.value)).first()
                        if cat:
                            all_ids = cat.get_all_ids()
                            query = query.filter(Product.category_id.in_(all_ids))
                    except (ValueError, TypeError):
                        pass

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

                # Research status filter (expanded for evaluation statuses)
                status_val = status_select.value
                if status_val != "All":
                    db_status = _STATUS_FILTER_MAP.get(status_val)
                    if db_status:
                        products = [
                            p for p in products
                            if (getattr(p, "status", None) or "imported") == db_status
                        ]

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
                    total_count = db.query(Product).filter(Product.status != "deleted").count()
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

                        # Group products by category
                        from collections import OrderedDict
                        cat_groups: OrderedDict[str, list] = OrderedDict()
                        for p in products:
                            cat_name = p.category.name if p.category else "Uncategorized"
                            cat_groups.setdefault(cat_name, []).append(p)

                        for cat_name, cat_products in cat_groups.items():
                            cat_comp_total = sum(comp_counts.get(p.id, 0) for p in cat_products)
                            # Category status summary
                            statuses = {}
                            for p in cat_products:
                                st = getattr(p, "status", None) or "imported"
                                statuses[st] = statuses.get(st, 0) + 1

                            with ui.expansion(
                                value=True,
                            ).classes("w-full").props("dense header-class='py-1'").style(
                                "border-left: 3px solid #A08968; background: #faf8f5; "
                                "border-radius: 6px; margin-bottom: 8px"
                            ):
                                # Custom header slot
                                with ui.row().classes(
                                    "items-center gap-3 w-full py-1"
                                ).style("min-height: 40px"):
                                    ui.icon("category", size="sm").classes("text-accent")
                                    ui.label(cat_name).classes("text-subtitle2 font-bold")
                                    ui.badge(
                                        str(len(cat_products)),
                                        color="accent",
                                    ).props("rounded").tooltip("Products in category")
                                    ui.label(
                                        f"{cat_comp_total} competitors"
                                    ).classes("text-caption text-secondary")
                                    # Mini status badges
                                    for st, cnt in statuses.items():
                                        ui.badge(
                                            f"{cnt} {_STATUS_LABELS.get(st, st)}",
                                            color=_STATUS_COLORS.get(st, "grey-5"),
                                        ).props("outline dense")

                                # Products inside category
                                if is_table:
                                    for p in cat_products:
                                        comp_count = comp_counts.get(p.id, 0)
                                        session_count = len(p.search_sessions)
                                        _render_product_row(p, comp_count, session_count, db)
                                else:
                                    with ui.element("div").classes(
                                        "w-full grid gap-4"
                                    ).style(
                                        "grid-template-columns: repeat(auto-fill, minmax(320px, 1fr))"
                                    ):
                                        for p in cat_products:
                                            comp_count = comp_counts.get(p.id, 0)
                                            session_count = len(p.search_sessions)
                                            _render_product_card(p, comp_count, session_count, db)
                finally:
                    db.close()

            # Wire up all filter controls to refresh (reset to page 1)
            def _clear_preset_if_manual():
                """Clear preset selection when user manually changes a filter."""
                if not _applying_preset["active"] and preset_select.value is not None:
                    preset_select.value = None

            def _filter_and_reset(_=None):
                _clear_preset_if_manual()
                _page_state["current"] = 1
                refresh_products()

            _search_timer = {"ref": None}

            def _debounced_search(_):
                _clear_preset_if_manual()
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
            sort_select.on_value_change(lambda _: (_clear_preset_if_manual(), refresh_products()))
            view_toggle.on_value_change(lambda _: refresh_products())

            refresh_products()

            if search:
                ui.timer(0.3, lambda: refresh_products(), once=True)
        finally:
            session.close()


def _delete_button(product_id: int, product_name: str, on_deleted):
    """Render a delete icon button with confirmation dialog (soft-delete to recycle bin)."""

    def show_confirm():
        with ui.dialog() as dialog, ui.card():
            ui.label(f'Move "{product_name}" to Recycle Bin?').classes("text-subtitle1 font-bold")
            ui.label(
                "The product will be moved to the Recycle Bin. "
                "You can restore it later or delete it permanently."
            ).classes("text-body2 text-secondary")
            with ui.row().classes("justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                def confirm_delete():
                    db = get_session()
                    try:
                        prod = db.query(Product).filter(Product.id == product_id).first()
                        if prod:
                            prod.status = "deleted"
                            db.commit()
                    finally:
                        db.close()
                    dialog.close()
                    on_deleted()

                ui.button("Move to Bin", on_click=confirm_delete).props("color=negative")
        dialog.open()

    ui.button(icon="delete", on_click=show_confirm).props(
        "flat round dense color=negative size=sm"
    ).tooltip("Delete product")
