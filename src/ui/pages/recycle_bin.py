"""Recycle Bin page — view, restore, or permanently delete soft-deleted products."""
from nicegui import ui
from sqlalchemy.orm import joinedload

from src.models import Product
from src.models.category import Category
from src.models.database import get_session
from src.ui.layout import build_layout, refresh_nav_categories
from src.ui.components.helpers import page_header, product_image_src, avatar_color, HOVER_BG


def recycle_bin_page():
    """Render the Recycle Bin page."""
    with build_layout("Recycle Bin"):
        page_header(
            "Recycle Bin",
            subtitle="Deleted products can be restored or permanently removed.",
            icon="delete_sweep",
        )

        product_container = ui.column().classes("w-full gap-2")

        def refresh():
            product_container.clear()
            db = get_session()
            try:
                deleted = (
                    db.query(Product)
                    .options(joinedload(Product.category))
                    .filter(Product.status == "deleted")
                    .order_by(Product.updated_at.desc())
                    .all()
                )

                with product_container:
                    if not deleted:
                        with ui.card().classes("w-full p-8"):
                            with ui.column().classes("items-center w-full gap-2"):
                                ui.icon("check_circle", size="xl").classes("text-positive")
                                ui.label("Recycle Bin is empty").classes(
                                    "text-h6 text-secondary"
                                )
                        return

                    # Bulk actions
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label(f"{len(deleted)} deleted product{'s' if len(deleted) != 1 else ''}").classes(
                            "text-body1 text-secondary"
                        )

                        def _show_empty_dialog():
                            with ui.dialog() as dlg, ui.card():
                                ui.label("Empty Recycle Bin?").classes(
                                    "text-subtitle1 font-bold"
                                )
                                ui.label(
                                    f"This will permanently delete {len(deleted)} product(s) "
                                    "and all their research data. This cannot be undone."
                                ).classes("text-body2 text-negative")
                                with ui.row().classes("justify-end gap-2 mt-4"):
                                    ui.button("Cancel", on_click=dlg.close).props("flat")

                                    def _confirm_empty():
                                        db2 = get_session()
                                        try:
                                            db2.query(Product).filter(
                                                Product.status == "deleted"
                                            ).delete()
                                            db2.commit()
                                        finally:
                                            db2.close()
                                        dlg.close()
                                        refresh_nav_categories()
                                        refresh()

                                    ui.button(
                                        "Delete All Forever", on_click=_confirm_empty,
                                    ).props("color=negative")
                            dlg.open()

                        ui.button(
                            "Empty Recycle Bin", icon="delete_forever",
                            on_click=_show_empty_dialog,
                        ).props("color=negative outline")

                    # Product rows
                    for prod in deleted:
                        _deleted_product_row(prod, refresh)

            finally:
                db.close()

        refresh()


def _deleted_product_row(product, on_change):
    """Render a single deleted product row with restore/delete-forever actions."""
    with ui.card().classes("w-full p-3"):
        with ui.row().classes("items-center gap-4 w-full"):
            # Image / avatar
            img_src = product_image_src(product)
            if img_src:
                ui.image(img_src).classes("w-12 h-12 rounded object-cover")
            else:
                letter = product.name[0].upper() if product.name else "?"
                bg = avatar_color(product.name)
                ui.avatar(
                    letter, color=bg, text_color="white", size="48px", font_size="20px",
                ).classes("rounded")

            # Info
            with ui.column().classes("flex-1 gap-0"):
                ui.label(product.name).classes("text-body1 font-medium")
                cat_name = product.category.name if product.category else "—"
                ui.label(f"Category: {cat_name}").classes("text-caption text-secondary")

            # Actions
            with ui.row().classes("gap-2"):
                def _restore(pid=product.id):
                    db = get_session()
                    try:
                        p = db.query(Product).filter(Product.id == pid).first()
                        if p:
                            p.status = "imported"
                            db.commit()
                    finally:
                        db.close()
                    ui.notify("Product restored", type="positive")
                    refresh_nav_categories()
                    on_change()

                ui.button("Restore", icon="restore", on_click=_restore).props(
                    "color=positive outline dense"
                )

                def _show_perm_delete(pid=product.id, pname=product.name):
                    with ui.dialog() as dlg, ui.card():
                        ui.label(f'Permanently delete "{pname}"?').classes(
                            "text-subtitle1 font-bold"
                        )
                        ui.label(
                            "This will permanently remove the product and all its "
                            "research data. This cannot be undone."
                        ).classes("text-body2 text-negative")
                        with ui.row().classes("justify-end gap-2 mt-4"):
                            ui.button("Cancel", on_click=dlg.close).props("flat")

                            def _confirm(pid=pid):
                                db = get_session()
                                try:
                                    p = db.query(Product).filter(Product.id == pid).first()
                                    if p:
                                        db.delete(p)
                                        db.commit()
                                finally:
                                    db.close()
                                dlg.close()
                                refresh_nav_categories()
                                on_change()

                            ui.button(
                                "Delete Forever", on_click=_confirm,
                            ).props("color=negative")
                    dlg.open()

                ui.button(
                    "Delete Forever", icon="delete_forever", on_click=_show_perm_delete,
                ).props("color=negative flat dense")
