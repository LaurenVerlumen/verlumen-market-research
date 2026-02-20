"""Import page - upload or select the Verlumen Excel file to import products."""
from pathlib import Path

from nicegui import ui

from config import BASE_DIR
from src.models import get_session, init_db, Category, Product
from src.services import parse_excel
from src.ui.layout import build_layout


# Default Excel file path
DEFAULT_EXCEL = BASE_DIR / "verlumen-Product Research.xlsx"


def import_page():
    """Render the import page."""
    content = build_layout()

    with content:
        ui.label("Import Products from Excel").classes("text-h5 font-bold")
        ui.label(
            "Upload the Verlumen Product Research spreadsheet or import the default file."
        ).classes("text-body2 text-secondary mb-2")

        # Status area
        status_container = ui.column().classes("w-full gap-2")
        results_container = ui.column().classes("w-full gap-2")

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
                        if existing:
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
                with status_container:
                    ui.label(f"Error during import: {e}").classes("text-negative")
                return
            finally:
                session.close()

            results_container.clear()
            with results_container:
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

                # Imported products
                if imported_names:
                    with ui.expansion(
                        f"New products ({len(imported_names)})", icon="check_circle",
                    ).classes("w-full").props("default-opened"):
                        for name in imported_names:
                            with ui.row().classes("items-center gap-1 ml-4"):
                                ui.icon("check_circle", size="xs").classes("text-positive")
                                ui.label(name).classes("text-body2")

                # Skipped duplicates
                if skipped_names:
                    with ui.expansion(
                        f"Skipped duplicates ({len(skipped_names)})", icon="content_copy",
                    ).classes("w-full"):
                        for name in skipped_names:
                            with ui.row().classes("items-center gap-1 ml-4"):
                                ui.icon("block", size="xs").classes("text-warning")
                                ui.label(name).classes("text-body2 text-secondary")

                with ui.row().classes("gap-3 mt-2"):
                    ui.button(
                        "View Products", icon="inventory_2",
                        on_click=lambda: ui.navigate.to("/products"),
                    ).props("color=primary")
                    ui.button(
                        "Run Research", icon="search",
                        on_click=lambda: ui.navigate.to("/research"),
                    ).props("color=positive")

        # Option 1: Import default file
        with ui.card().classes("w-full p-4 mb-4"):
            ui.label("Import Default File").classes("text-subtitle1 font-bold mb-2")
            file_exists = DEFAULT_EXCEL.exists()
            if file_exists:
                ui.label(f"Found: {DEFAULT_EXCEL.name}").classes("text-body2 text-secondary mb-2")

                def import_default():
                    status_container.clear()
                    results_container.clear()
                    with status_container:
                        ui.label("Parsing Excel file...").classes("text-body2 text-primary")
                    try:
                        data = parse_excel(str(DEFAULT_EXCEL))
                        status_container.clear()
                        _do_import(data)
                    except Exception as e:
                        status_container.clear()
                        with status_container:
                            ui.label(f"Error parsing file: {e}").classes("text-negative")

                ui.button(
                    "Import Default Spreadsheet",
                    icon="upload_file",
                    on_click=import_default,
                ).props("color=primary")
            else:
                ui.label(
                    f"Default file not found at: {DEFAULT_EXCEL}"
                ).classes("text-body2 text-warning")

        # Option 2: Upload file
        with ui.card().classes("w-full p-4"):
            ui.label("Upload Excel File").classes("text-subtitle1 font-bold mb-2")
            ui.label("Select an .xlsx file with the Verlumen format.").classes(
                "text-body2 text-secondary mb-2"
            )

            async def handle_upload(e):
                status_container.clear()
                results_container.clear()
                with status_container:
                    ui.label("Parsing uploaded file...").classes("text-body2 text-primary")
                try:
                    file_content = e.content.read()
                    data = parse_excel(file_content)
                    status_container.clear()
                    _do_import(data)
                except Exception as exc:
                    status_container.clear()
                    with status_container:
                        ui.label(f"Error parsing upload: {exc}").classes("text-negative")

            ui.upload(
                label="Choose Excel file",
                auto_upload=True,
                on_upload=handle_upload,
            ).props('accept=".xlsx" max-file-size=10485760').classes("w-full")
