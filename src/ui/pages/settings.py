"""Settings page - configure API keys and app preferences."""
import asyncio
import os

from nicegui import ui

import config
from config import (
    BASE_DIR, SERPAPI_KEY,
    AMAZON_DEPARTMENT_MAP, AMAZON_DEPARTMENT_DEFAULT, AMAZON_DEPARTMENTS,
    save_department_map,
)
from src.models import Category, Product, get_session
from src.services import AmazonSearchService
from src.ui.layout import build_layout


ENV_FILE = BASE_DIR / ".env"


def settings_page():
    """Render the settings page."""
    content = build_layout()

    with content:
        ui.label("Settings").classes("text-h5 font-bold")

        # SerpAPI configuration
        with ui.card().classes("w-full p-4 mb-4"):
            ui.label("SerpAPI Configuration").classes("text-subtitle1 font-bold mb-2")
            ui.label(
                "Enter your SerpAPI key to enable Amazon product research. "
                "Get a key at serpapi.com."
            ).classes("text-body2 text-secondary mb-3")

            current_key = SERPAPI_KEY or ""
            masked = _mask_key(current_key) if current_key else "Not configured"

            with ui.row().classes("items-center gap-2 mb-3"):
                ui.label("Current key:").classes("text-body2 font-medium")
                status_label = ui.label(masked).classes("text-body2 text-secondary")

                if current_key:
                    ui.icon("check_circle").classes("text-positive")
                else:
                    ui.icon("warning").classes("text-warning")

            api_input = ui.input(
                label="SerpAPI Key",
                password=True,
                password_toggle_button=True,
                value="",
                placeholder="Paste your SerpAPI key here",
            ).classes("w-full mb-2")

            validation_label = ui.label("").classes("text-body2 mt-1")

            def save_key():
                new_key = api_input.value.strip()
                if not new_key:
                    ui.notify("Please enter a key.", type="warning")
                    return

                _update_env_file("SERPAPI_KEY", new_key)
                os.environ["SERPAPI_KEY"] = new_key
                config.SERPAPI_KEY = new_key

                status_label.text = _mask_key(new_key)
                api_input.value = ""
                ui.notify("API key saved!", type="positive")

            async def validate_key():
                key = api_input.value.strip() or current_key
                if not key:
                    validation_label.text = "No key to validate."
                    return
                validation_label.text = "Validating..."
                service = AmazonSearchService(api_key=key)
                loop = asyncio.get_event_loop()
                valid = await loop.run_in_executor(None, service.check_api_key)
                if valid:
                    validation_label.text = "Key is valid!"
                    validation_label.classes("text-positive", remove="text-negative")
                    remaining = await loop.run_in_executor(None, service.get_remaining_searches)
                    if remaining is not None:
                        validation_label.text += f" ({remaining} searches remaining)"
                else:
                    validation_label.text = "Key is invalid or API is unreachable."
                    validation_label.classes("text-negative", remove="text-positive")

            with ui.row().classes("gap-2"):
                ui.button("Save Key", icon="save", on_click=save_key).props("color=primary")
                ui.button("Validate Key", icon="verified", on_click=validate_key).props("flat color=grey")

        # Database info
        with ui.card().classes("w-full p-4 mb-4"):
            ui.label("Database").classes("text-subtitle1 font-bold mb-2")
            from config import DB_PATH
            db_exists = DB_PATH.exists()
            db_size = DB_PATH.stat().st_size / 1024 if db_exists else 0

            with ui.row().classes("gap-6"):
                ui.label(f"Location: {DB_PATH}").classes("text-body2 text-secondary")
                ui.label(f"Size: {db_size:.1f} KB").classes("text-body2 text-secondary")

            def reset_db():
                from src.models import init_db
                init_db()
                ui.notify("Database tables recreated.", type="info")

            def reset_research():
                """Delete all research data (search sessions + competitors) but keep products."""
                session = get_session()
                try:
                    from src.models import AmazonCompetitor, SearchSession
                    count_comp = session.query(AmazonCompetitor).delete()
                    count_sess = session.query(SearchSession).delete()
                    session.commit()
                    ui.notify(
                        f"Research data cleared: {count_sess} sessions, "
                        f"{count_comp} competitors deleted.",
                        type="positive",
                    )
                except Exception as e:
                    session.rollback()
                    ui.notify(f"Error: {e}", type="negative")
                finally:
                    session.close()

            with ui.row().classes("gap-2 mt-2"):
                ui.button("Recreate Tables", icon="refresh", on_click=reset_db).props(
                    "flat color=grey"
                )
                ui.button(
                    "Reset All Research Data",
                    icon="delete_sweep",
                    on_click=lambda: ui.notify(
                        "Delete ALL search sessions and competitor data? Products will be kept.",
                        type="warning",
                        actions=[
                            {"label": "Confirm", "color": "negative", "handler": reset_research},
                            {"label": "Cancel", "color": "white"},
                        ],
                    ),
                ).props("flat color=negative")

        # Search Cache stats
        with ui.card().classes("w-full p-4 mb-4"):
            ui.label("Search Cache").classes("text-subtitle1 font-bold mb-2")
            ui.label(
                "Amazon search results are cached for 24 hours to reduce API usage."
            ).classes("text-body2 text-secondary mb-3")

            cache_stats_container = ui.column().classes("w-full")

            def refresh_cache_stats():
                cache_stats_container.clear()
                try:
                    from src.services.search_cache import SearchCache
                    cache = SearchCache()
                    stats = cache.get_stats()
                    with cache_stats_container:
                        with ui.row().classes("gap-6"):
                            ui.label(f"Total entries: {stats['total_entries']}").classes(
                                "text-body2 text-secondary"
                            )
                            ui.label(f"Active: {stats['active_entries']}").classes(
                                "text-body2 text-positive"
                            )
                            ui.label(f"Expired: {stats['expired_entries']}").classes(
                                "text-body2 text-warning"
                            )
                            ui.label(f"Total cache hits: {stats['total_hits']}").classes(
                                "text-body2 text-secondary"
                            )
                except Exception:
                    with cache_stats_container:
                        ui.label("Cache not available.").classes("text-body2 text-secondary")

            def clear_expired():
                try:
                    from src.services.search_cache import SearchCache
                    cache = SearchCache()
                    cleared = cache.clear_expired_cache()
                    ui.notify(f"Cleared {cleared} expired cache entries.", type="positive")
                    refresh_cache_stats()
                except Exception as e:
                    ui.notify(f"Error: {e}", type="negative")

            refresh_cache_stats()

            ui.button(
                "Clear Expired Cache", icon="cleaning_services", on_click=clear_expired,
            ).props("flat color=grey").classes("mt-2")

        # Amazon Department Mapping
        with ui.card().classes("w-full p-4 mb-4"):
            ui.label("Amazon Department Mapping").classes("text-subtitle1 font-bold mb-2")
            ui.label(
                "Map your product categories to Amazon departments. "
                "This filters search results to the correct department for better relevance."
            ).classes("text-body2 text-secondary mb-3")

            dept_container = ui.column().classes("w-full")

            # Build inverted dept options for the dropdowns
            dept_options = {v: k for k, v in AMAZON_DEPARTMENTS.items()}

            def _refresh_dept_mapping():
                dept_container.clear()
                session_d = get_session()
                try:
                    categories = session_d.query(Category).order_by(Category.name).all()
                    with dept_container:
                        if not categories:
                            ui.label("No categories found. Import products first.").classes(
                                "text-body2 text-secondary"
                            )
                            return

                        ui.label(
                            f"Default department: {AMAZON_DEPARTMENTS.get(AMAZON_DEPARTMENT_DEFAULT, AMAZON_DEPARTMENT_DEFAULT)}"
                        ).classes("text-caption text-secondary mb-2")

                        for cat in categories:
                            cat_lower = cat.name.lower()
                            current_dept = AMAZON_DEPARTMENT_MAP.get(
                                cat_lower, AMAZON_DEPARTMENT_DEFAULT
                            )
                            current_label = AMAZON_DEPARTMENTS.get(current_dept, current_dept)

                            with ui.row().classes("items-center gap-3 w-full py-1"):
                                ui.label(cat.name).classes("text-body2 font-medium").style(
                                    "min-width:200px"
                                )
                                ui.icon("arrow_forward").classes("text-grey-5")

                                def _make_handler(cname):
                                    def _on_change(e):
                                        new_dept = dept_options.get(e.value, e.value)
                                        AMAZON_DEPARTMENT_MAP[cname.lower()] = new_dept
                                        save_department_map(AMAZON_DEPARTMENT_MAP)
                                        ui.notify(
                                            f"Mapped '{cname}' -> {e.value}",
                                            type="positive",
                                        )
                                    return _on_change

                                dept_select = ui.select(
                                    options=list(AMAZON_DEPARTMENTS.values()),
                                    value=current_label,
                                    on_change=_make_handler(cat.name),
                                ).props("outlined dense").classes("w-48")
                finally:
                    session_d.close()

            _refresh_dept_mapping()

        # Category Management
        with ui.card().classes("w-full p-4 mb-4"):
            ui.label("Category Management").classes("text-subtitle1 font-bold mb-2")
            ui.label(
                "Manage product categories. Rename categories to fix typos, "
                "or delete unused ones."
            ).classes("text-body2 text-secondary mb-3")

            category_container = ui.column().classes("w-full")

            def refresh_categories():
                """Reload the category list from the database."""
                category_container.clear()
                session = get_session()
                try:
                    categories = session.query(Category).order_by(Category.name).all()
                    with category_container:
                        if not categories:
                            ui.label("No categories found.").classes(
                                "text-body2 text-secondary"
                            )
                        for cat in categories:
                            product_count = (
                                session.query(Product)
                                .filter_by(category_id=cat.id)
                                .count()
                            )
                            _build_category_row(
                                cat.id, cat.name, product_count, refresh_categories
                            )

                        # Add new category section
                        with ui.row().classes("items-center gap-2 mt-3 w-full"):
                            new_cat_input = ui.input(
                                label="New category name",
                                placeholder="Enter category name",
                            ).classes("flex-grow")

                            def add_category(inp=new_cat_input):
                                name = inp.value.strip()
                                if not name:
                                    ui.notify(
                                        "Category name cannot be empty.",
                                        type="warning",
                                    )
                                    return
                                sess = get_session()
                                try:
                                    existing = (
                                        sess.query(Category)
                                        .filter_by(name=name)
                                        .first()
                                    )
                                    if existing:
                                        ui.notify(
                                            f"Category '{name}' already exists.",
                                            type="warning",
                                        )
                                        return
                                    sess.add(Category(name=name))
                                    sess.commit()
                                    ui.notify(
                                        f"Category '{name}' added.",
                                        type="positive",
                                    )
                                    refresh_categories()
                                finally:
                                    sess.close()

                            ui.button("Add", icon="add", on_click=add_category).props(
                                "color=primary"
                            )
                finally:
                    session.close()

            refresh_categories()

        # About
        with ui.card().classes("w-full p-4"):
            ui.label("About").classes("text-subtitle1 font-bold mb-2")
            ui.label("Verlumen Market Research Tool").classes("text-body2")
            ui.label(
                "Automates Amazon competition analysis for wood/Montessori toy products. "
                "Import products from Alibaba, search Amazon via SerpAPI, and export analysis reports."
            ).classes("text-body2 text-secondary")


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def _update_env_file(key: str, value: str):
    lines = []
    found = False

    if ENV_FILE.exists():
        lines = ENV_FILE.read_text().splitlines()

    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(new_lines) + "\n")


def _build_category_row(cat_id: int, cat_name: str, product_count: int, on_refresh):
    """Build a single category row with rename and delete controls."""
    row = ui.row().classes("items-center gap-2 w-full py-1")

    with row:
        # Display mode: name label + product count + action buttons
        name_label = ui.label(cat_name).classes("text-body1 flex-grow")
        count_badge = ui.label(
            f"{product_count} product{'s' if product_count != 1 else ''}"
        ).classes("text-body2 text-secondary")

        # Edit (rename) mode elements - hidden initially
        edit_input = ui.input(value=cat_name).classes("flex-grow")
        edit_input.visible = False

        def start_edit():
            name_label.visible = False
            count_badge.visible = False
            edit_btn.visible = False
            delete_btn.visible = False
            edit_input.visible = True
            edit_input.value = name_label.text

        def finish_edit():
            new_name = edit_input.value.strip()
            if not new_name:
                ui.notify("Category name cannot be empty.", type="warning")
                return
            if new_name == cat_name:
                # No change, just restore display mode
                _restore_display()
                return
            session = get_session()
            try:
                duplicate = (
                    session.query(Category)
                    .filter(Category.name == new_name, Category.id != cat_id)
                    .first()
                )
                if duplicate:
                    ui.notify(
                        f"Category '{new_name}' already exists.", type="warning"
                    )
                    return
                cat = session.query(Category).filter_by(id=cat_id).first()
                if cat:
                    cat.name = new_name
                    session.commit()
                    ui.notify(f"Renamed to '{new_name}'.", type="positive")
                    on_refresh()
            finally:
                session.close()

        def _restore_display():
            name_label.visible = True
            count_badge.visible = True
            edit_btn.visible = True
            delete_btn.visible = True
            edit_input.visible = False

        edit_input.on("keydown.enter", lambda: finish_edit())
        edit_input.on("blur", lambda: finish_edit())

        edit_btn = ui.button(icon="edit", on_click=start_edit).props(
            "flat dense color=grey"
        )

        def delete_category():
            session = get_session()
            try:
                cat = session.query(Category).filter_by(id=cat_id).first()
                if cat:
                    session.delete(cat)
                    session.commit()
                    ui.notify(f"Category '{cat_name}' deleted.", type="positive")
                    on_refresh()
            finally:
                session.close()

        if product_count == 0:
            delete_btn = ui.button(
                icon="delete",
                on_click=lambda: ui.notify(
                    f"Delete '{cat_name}'?",
                    type="warning",
                    actions=[
                        {
                            "label": "Confirm",
                            "color": "negative",
                            "handler": delete_category,
                        },
                        {"label": "Cancel", "color": "white"},
                    ],
                ),
            ).props("flat dense color=negative")
        else:
            delete_btn = ui.button(icon="delete").props(
                "flat dense color=grey disable"
            )
            delete_btn.tooltip(
                f"Has {product_count} product{'s' if product_count != 1 else ''}"
                " - cannot delete"
            )
