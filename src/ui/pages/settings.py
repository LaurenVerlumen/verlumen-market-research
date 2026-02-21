"""Settings page - configure API keys and app preferences."""
import asyncio
import os

from nicegui import ui
from sqlalchemy import func
from sqlalchemy.orm import joinedload

import config
from config import (
    BASE_DIR, SERPAPI_KEY,
    SP_API_REFRESH_TOKEN, SP_API_LWA_APP_ID, SP_API_LWA_CLIENT_SECRET,
    SP_API_AWS_ACCESS_KEY, SP_API_AWS_SECRET_KEY, SP_API_ROLE_ARN,
    AMAZON_DEPARTMENTS, AMAZON_DEPARTMENT_DEFAULT,
)
from src.models import Category, Product, get_session
from src.services import AmazonSearchService
from src.services.sp_api_client import SPAPIClient
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

        # Amazon SP-API configuration
        with ui.card().classes("w-full p-4 mb-4"):
            ui.label("Amazon SP-API Configuration").classes("text-subtitle1 font-bold mb-2")
            ui.label(
                "Connect your Amazon Seller account for brand enrichment."
            ).classes("text-body2 text-secondary mb-3")

            sp_configured = bool(SP_API_REFRESH_TOKEN and SP_API_LWA_APP_ID)
            with ui.row().classes("items-center gap-2 mb-3"):
                ui.label("Status:").classes("text-body2 font-medium")
                if sp_configured:
                    ui.label("Configured").classes("text-body2 text-positive")
                    ui.icon("check_circle").classes("text-positive")
                else:
                    ui.label("Not configured").classes("text-body2 text-secondary")
                    ui.icon("warning").classes("text-warning")

            _sp_fields = [
                ("SP_API_REFRESH_TOKEN", "Refresh Token", SP_API_REFRESH_TOKEN),
                ("SP_API_LWA_APP_ID", "LWA App ID", SP_API_LWA_APP_ID),
                ("SP_API_LWA_CLIENT_SECRET", "LWA Client Secret", SP_API_LWA_CLIENT_SECRET),
                ("SP_API_AWS_ACCESS_KEY", "AWS Access Key", SP_API_AWS_ACCESS_KEY),
                ("SP_API_AWS_SECRET_KEY", "AWS Secret Key", SP_API_AWS_SECRET_KEY),
                ("SP_API_ROLE_ARN", "Role ARN", SP_API_ROLE_ARN),
            ]

            sp_inputs = {}
            for env_key, label_text, current_val in _sp_fields:
                with ui.row().classes("items-center gap-2 w-full"):
                    ui.label(label_text).classes("text-body2 font-medium").style("min-width:150px")
                    if current_val:
                        ui.label(_mask_key(current_val)).classes("text-caption text-secondary")
                    sp_inputs[env_key] = ui.input(
                        label=label_text,
                        password=True,
                        password_toggle_button=True,
                        value="",
                        placeholder=f"Enter {label_text}",
                    ).classes("flex-1")

            sp_validation_label = ui.label("").classes("text-body2 mt-1")

            async def _save_and_validate_sp_api():
                # Check that at least one field has a value (new or existing)
                has_any_new = any(sp_inputs[k].value.strip() for k in sp_inputs)
                if not has_any_new and not sp_configured:
                    ui.notify("Please fill in at least the required credentials.", type="warning")
                    return

                # Save each non-empty input to .env and update os.environ / config
                for env_key, label_text, current_val in _sp_fields:
                    new_val = sp_inputs[env_key].value.strip()
                    if new_val:
                        _update_env_file(env_key, new_val)
                        os.environ[env_key] = new_val
                        setattr(config, env_key, new_val)

                sp_validation_label.text = "Saved. Validating..."
                ui.notify("Credentials saved!", type="positive")

                # Clear inputs after save
                for inp in sp_inputs.values():
                    inp.value = ""

                # Validate using SPAPIClient
                try:
                    client = SPAPIClient()
                    loop = asyncio.get_event_loop()
                    valid = await loop.run_in_executor(None, client.validate_credentials)
                    if valid:
                        sp_validation_label.text = "Credentials are valid!"
                        sp_validation_label.classes("text-positive", remove="text-negative")
                    else:
                        sp_validation_label.text = "Validation failed - check your credentials."
                        sp_validation_label.classes("text-negative", remove="text-positive")
                except Exception as exc:
                    sp_validation_label.text = f"Validation error: {exc}"
                    sp_validation_label.classes("text-negative", remove="text-positive")

            ui.button(
                "Save & Validate", icon="verified",
                on_click=_save_and_validate_sp_api,
            ).props("color=primary").classes("mt-2")

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

        # Category Management (hierarchical tree)
        with ui.card().classes("w-full p-4 mb-4"):
            ui.label("Category Management").classes("text-subtitle1 font-bold mb-2")
            ui.label(
                "Manage product categories as a hierarchy. "
                "Each category can have subcategories and its own Amazon department."
            ).classes("text-body2 text-secondary mb-3")

            category_tree_container = ui.column().classes("w-full")

            def refresh_categories():
                """Reload the category tree from the database and update sidebar nav."""
                from src.ui.layout import refresh_nav_categories
                refresh_nav_categories()
                _render_category_tree(category_tree_container)

            _render_category_tree(category_tree_container, on_refresh=refresh_categories)

        # Scheduled Research
        with ui.card().classes("w-full p-4 mb-4"):
            ui.label("Scheduled Research").classes("text-subtitle1 font-bold mb-2")
            ui.label(
                "Automatically research products on a schedule. "
                "The scheduler runs in the background and researches all products "
                "with status 'imported' or 'researched'."
            ).classes("text-body2 text-secondary mb-3")

            from src.services.scheduler import (
                load_config as load_schedule_config,
                save_config as save_schedule_config,
                restart_scheduler,
                run_now as scheduler_run_now,
                get_scheduler_status,
            )

            sched_status = get_scheduler_status()

            # Status display
            sched_status_container = ui.column().classes("w-full mb-3")

            def _refresh_sched_status():
                sched_status_container.clear()
                status = get_scheduler_status()
                with sched_status_container:
                    with ui.row().classes("gap-6 items-center"):
                        if status["running"]:
                            ui.icon("schedule").classes("text-positive")
                            ui.label("Scheduler is running").classes("text-body2 text-positive")
                        else:
                            ui.icon("schedule").classes("text-grey-5")
                            ui.label("Scheduler is stopped").classes("text-body2 text-secondary")

                    with ui.row().classes("gap-6 mt-1"):
                        if status["last_run"]:
                            ui.label(f"Last run: {status['last_run']}").classes(
                                "text-caption text-secondary"
                            )
                            ui.label(
                                f"Products researched: {status['products_researched']}"
                            ).classes("text-caption text-secondary")
                        else:
                            ui.label("Never run").classes("text-caption text-secondary")

            _refresh_sched_status()

            # Configuration controls
            sched_cfg = load_schedule_config()

            enabled_switch = ui.switch(
                "Enable scheduled research",
                value=sched_cfg.get("enabled", False),
            )

            with ui.row().classes("gap-4 items-end w-full mt-2"):
                freq_select = ui.select(
                    label="Frequency",
                    options=["daily", "weekly", "monthly"],
                    value=sched_cfg.get("frequency", "weekly"),
                ).classes("w-40")

                hour_select = ui.select(
                    label="Hour (0-23)",
                    options={h: f"{h:02d}:00" for h in range(24)},
                    value=sched_cfg.get("hour", 2),
                ).classes("w-32")

                dow_options = {
                    "mon": "Monday",
                    "tue": "Tuesday",
                    "wed": "Wednesday",
                    "thu": "Thursday",
                    "fri": "Friday",
                    "sat": "Saturday",
                    "sun": "Sunday",
                }
                dow_select = ui.select(
                    label="Day of week",
                    options=dow_options,
                    value=sched_cfg.get("day_of_week", "mon"),
                ).classes("w-40")

            # Show/hide day-of-week based on frequency
            def _update_dow_visibility():
                dow_select.visible = freq_select.value == "weekly"

            freq_select.on("update:model-value", lambda _: _update_dow_visibility())
            _update_dow_visibility()

            def _save_schedule():
                cfg = load_schedule_config()
                cfg["enabled"] = enabled_switch.value
                cfg["frequency"] = freq_select.value
                cfg["hour"] = hour_select.value
                cfg["day_of_week"] = dow_select.value
                save_schedule_config(cfg)
                restart_scheduler()
                _refresh_sched_status()
                ui.notify("Schedule saved and scheduler restarted.", type="positive")

            async def _run_now():
                ui.notify("Starting research run...", type="info")
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, scheduler_run_now)
                _refresh_sched_status()
                ui.notify("Research run complete!", type="positive")

            with ui.row().classes("gap-2 mt-3"):
                ui.button(
                    "Save Schedule", icon="save", on_click=_save_schedule,
                ).props("color=primary")
                ui.button(
                    "Run Now", icon="play_arrow", on_click=_run_now,
                ).props("outlined color=primary")

        # About
        with ui.card().classes("w-full p-4"):
            ui.label("About").classes("text-subtitle1 font-bold mb-2")
            ui.label("Verlumen Market Research Tool").classes("text-body2")
            ui.label(
                "Automates Amazon competition analysis for wood/Montessori toy products. "
                "Import products from Alibaba, search Amazon via SerpAPI, and export analysis reports."
            ).classes("text-body2 text-secondary")


def _render_category_tree(container, on_refresh=None):
    """Render the full category tree inside the given container."""
    container.clear()
    db = get_session()
    try:
        # Load root categories with eager-loaded children
        roots = (
            db.query(Category)
            .filter(Category.parent_id.is_(None))
            .order_by(Category.sort_order, Category.name)
            .all()
        )

        # Batch product counts: {category_id: count}
        prod_counts = dict(
            db.query(Product.category_id, func.count(Product.id))
            .group_by(Product.category_id)
            .all()
        )

        # We need to eagerly load the full tree. Use a recursive load.
        def _load_tree(cats):
            """Ensure all children are loaded while session is open."""
            for cat in cats:
                _ = cat.children  # trigger lazy load
                _load_tree(cat.children)

        _load_tree(roots)

        # Detach from session for rendering
        cat_data = _serialize_tree(roots, prod_counts)

    finally:
        db.close()

    if on_refresh is None:
        # Create a self-referencing refresh
        def on_refresh():
            _render_category_tree(container)

    with container:
        if not cat_data:
            ui.label("No categories found. They will be created when you import products.").classes(
                "text-body2 text-secondary"
            )

        for node in cat_data:
            _render_category_node(node, 0, on_refresh)

        # Add root category
        with ui.row().classes("items-center gap-2 mt-4 w-full"):
            new_root_input = ui.input(
                label="New root category",
                placeholder="e.g. Home & Kitchen",
            ).classes("flex-grow")

            def _add_root(inp=new_root_input):
                name = inp.value.strip()
                if not name:
                    ui.notify("Name cannot be empty.", type="warning")
                    return
                sess = get_session()
                try:
                    existing = sess.query(Category).filter_by(
                        name=name, parent_id=None
                    ).first()
                    if existing:
                        ui.notify(f"Root category '{name}' already exists.", type="warning")
                        return
                    sess.add(Category(name=name, level=0))
                    sess.commit()
                    ui.notify(f"Root category '{name}' added.", type="positive")
                    on_refresh()
                finally:
                    sess.close()

            ui.button("Add Root", icon="add", on_click=_add_root).props("color=primary")


def _serialize_tree(cats, prod_counts):
    """Convert Category ORM objects to plain dicts for rendering after session close."""
    result = []
    for cat in cats:
        own_count = prod_counts.get(cat.id, 0)
        children_data = _serialize_tree(cat.children, prod_counts)
        total_count = own_count + sum(c["total_count"] for c in children_data)
        result.append({
            "id": cat.id,
            "name": cat.name,
            "level": cat.level,
            "amazon_department": cat.amazon_department,
            "own_count": own_count,
            "total_count": total_count,
            "children": children_data,
        })
    return result


def _render_category_node(node, depth, on_refresh):
    """Render a single category node in the tree with actions."""
    indent = depth * 24

    with ui.row().classes("items-center gap-2 w-full py-1").style(
        f"padding-left: {indent}px"
    ):
        # Icon
        if node["children"]:
            ui.icon("folder", size="sm").classes("text-accent")
        else:
            ui.icon("label", size="sm").classes("text-grey-6")

        # Name
        ui.label(node["name"]).classes("text-body2 font-medium flex-1")

        # Product count badge
        if node["total_count"] > 0:
            count_text = str(node["own_count"])
            if node["children"] and node["total_count"] != node["own_count"]:
                count_text = f"{node['own_count']}/{node['total_count']}"
            ui.badge(count_text, color="grey-4").props("rounded dense").classes(
                "text-grey-8"
            ).tooltip(
                f"{node['own_count']} own, {node['total_count']} total with subcategories"
            )

        # Department dropdown
        dept_options = {"": "(inherit)"}
        dept_options.update({k: v for k, v in AMAZON_DEPARTMENTS.items()})
        current_dept = node["amazon_department"] or ""

        def _make_dept_handler(cat_id):
            def _on_dept_change(e):
                sess = get_session()
                try:
                    cat = sess.query(Category).filter_by(id=cat_id).first()
                    if cat:
                        cat.amazon_department = e.value if e.value else None
                        sess.commit()
                        resolved = cat.resolve_department()
                        ui.notify(
                            f"Department: {AMAZON_DEPARTMENTS.get(resolved, resolved)}",
                            type="positive",
                        )
                finally:
                    sess.close()
            return _on_dept_change

        dept_sel = ui.select(
            options=dept_options,
            value=current_dept,
            on_change=_make_dept_handler(node["id"]),
        ).props("outlined dense").classes("w-44").tooltip(
            f"Resolved: {AMAZON_DEPARTMENTS.get(node['amazon_department'] or AMAZON_DEPARTMENT_DEFAULT, AMAZON_DEPARTMENT_DEFAULT)}"
        )

        # Add child button
        def _make_add_child(parent_id, parent_name, parent_level):
            def _add_child():
                with ui.dialog() as dlg, ui.card().classes("w-80"):
                    ui.label(f"Add subcategory under '{parent_name}'").classes(
                        "text-subtitle2 font-bold"
                    )
                    child_input = ui.input(
                        label="Subcategory name",
                        placeholder="e.g. 3D Puzzles",
                    ).classes("w-full")

                    def _do_add():
                        name = child_input.value.strip()
                        if not name:
                            ui.notify("Name cannot be empty.", type="warning")
                            return
                        sess = get_session()
                        try:
                            existing = sess.query(Category).filter_by(
                                name=name, parent_id=parent_id
                            ).first()
                            if existing:
                                ui.notify(f"'{name}' already exists under '{parent_name}'.", type="warning")
                                return
                            sess.add(Category(
                                name=name,
                                parent_id=parent_id,
                                level=parent_level + 1,
                            ))
                            sess.commit()
                            dlg.close()
                            ui.notify(f"Added '{name}' under '{parent_name}'.", type="positive")
                            on_refresh()
                        finally:
                            sess.close()

                    with ui.row().classes("justify-end gap-2 mt-3"):
                        ui.button("Cancel", on_click=dlg.close).props("flat")
                        ui.button("Add", icon="add", on_click=_do_add).props("color=primary")
                dlg.open()
            return _add_child

        ui.button(
            icon="add",
            on_click=_make_add_child(node["id"], node["name"], node["level"]),
        ).props("flat dense round color=primary size=sm").tooltip("Add subcategory")

        # Rename button
        def _make_rename(cat_id, cat_name):
            def _rename():
                with ui.dialog() as dlg, ui.card().classes("w-80"):
                    ui.label("Rename Category").classes("text-subtitle2 font-bold")
                    rename_input = ui.input(label="New name", value=cat_name).classes("w-full")

                    def _do_rename():
                        new_name = rename_input.value.strip()
                        if not new_name:
                            ui.notify("Name cannot be empty.", type="warning")
                            return
                        if new_name == cat_name:
                            dlg.close()
                            return
                        sess = get_session()
                        try:
                            cat = sess.query(Category).filter_by(id=cat_id).first()
                            if cat:
                                # Check sibling uniqueness
                                dup = sess.query(Category).filter(
                                    Category.name == new_name,
                                    Category.parent_id == cat.parent_id,
                                    Category.id != cat_id,
                                ).first()
                                if dup:
                                    ui.notify(f"'{new_name}' already exists at this level.", type="warning")
                                    return
                                cat.name = new_name
                                sess.commit()
                                dlg.close()
                                ui.notify(f"Renamed to '{new_name}'.", type="positive")
                                on_refresh()
                        finally:
                            sess.close()

                    with ui.row().classes("justify-end gap-2 mt-3"):
                        ui.button("Cancel", on_click=dlg.close).props("flat")
                        ui.button("Rename", icon="edit", on_click=_do_rename).props("color=primary")
                dlg.open()
            return _rename

        ui.button(
            icon="edit",
            on_click=_make_rename(node["id"], node["name"]),
        ).props("flat dense round color=grey size=sm").tooltip("Rename")

        # Move / re-parent button
        def _make_move(cat_id, cat_name, cat_level):
            def _move():
                # Build list of valid parent options (excluding self and descendants)
                sess = get_session()
                try:
                    cat = sess.query(Category).filter_by(id=cat_id).first()
                    if not cat:
                        return
                    excluded_ids = set(cat.get_all_ids())

                    all_cats = (
                        sess.query(Category)
                        .order_by(Category.sort_order, Category.name)
                        .all()
                    )
                    roots = [c for c in all_cats if c.parent_id is None]

                    move_options = {"root": "(Root level)"}

                    def _build_move_options(cats, depth=0):
                        for c in cats:
                            if c.id not in excluded_ids:
                                indent = "\u00A0\u00A0\u00A0\u00A0" * depth
                                move_options[str(c.id)] = f"{indent}{c.name}"
                            _build_move_options(
                                [ch for ch in c.children if ch.id not in excluded_ids],
                                depth + 1,
                            )

                    _build_move_options(roots)

                    # Current parent
                    current_val = str(cat.parent_id) if cat.parent_id else "root"
                finally:
                    sess.close()

                with ui.dialog() as dlg, ui.card().classes("w-96"):
                    ui.label(f"Move '{cat_name}'").classes("text-subtitle2 font-bold")
                    ui.label("Select a new parent category:").classes(
                        "text-body2 text-secondary"
                    )
                    parent_select = ui.select(
                        options=move_options,
                        value=current_val,
                        label="New parent",
                    ).props("outlined dense").classes("w-full")

                    def _do_move():
                        new_parent = parent_select.value
                        sess = get_session()
                        try:
                            cat = sess.query(Category).filter_by(id=cat_id).first()
                            if not cat:
                                return
                            if new_parent == "root":
                                cat.parent_id = None
                                cat.level = 0
                            else:
                                new_pid = int(new_parent)
                                parent_cat = sess.query(Category).filter_by(id=new_pid).first()
                                if not parent_cat:
                                    return
                                cat.parent_id = new_pid
                                cat.level = parent_cat.level + 1

                            # Fix levels for all descendants
                            def _fix_levels(c, lvl):
                                c.level = lvl
                                for child in c.children:
                                    _fix_levels(child, lvl + 1)

                            _fix_levels(cat, cat.level)
                            sess.commit()
                            dlg.close()
                            new_parent_name = "(Root)" if new_parent == "root" else move_options.get(new_parent, "")
                            ui.notify(
                                f"Moved '{cat_name}' under {new_parent_name}.",
                                type="positive",
                            )
                            on_refresh()
                        finally:
                            sess.close()

                    with ui.row().classes("justify-end gap-2 mt-3"):
                        ui.button("Cancel", on_click=dlg.close).props("flat")
                        ui.button("Move", icon="drive_file_move", on_click=_do_move).props(
                            "color=primary"
                        )
                dlg.open()
            return _move

        ui.button(
            icon="drive_file_move",
            on_click=_make_move(node["id"], node["name"], node["level"]),
        ).props("flat dense round color=grey size=sm").tooltip("Move to another parent")

        # Delete button
        def _make_delete(cat_id, cat_name, has_products, has_children):
            def _delete():
                if has_products:
                    ui.notify(
                        f"Cannot delete '{cat_name}' - it has products assigned.",
                        type="warning",
                    )
                    return

                msg = f"Delete '{cat_name}'?"
                if has_children:
                    msg += " This will also delete all subcategories."

                with ui.dialog() as dlg, ui.card():
                    ui.label(msg).classes("text-subtitle2 font-bold")
                    with ui.row().classes("justify-end gap-2 mt-3"):
                        ui.button("Cancel", on_click=dlg.close).props("flat")

                        def _do_delete():
                            sess = get_session()
                            try:
                                cat = sess.query(Category).filter_by(id=cat_id).first()
                                if cat:
                                    sess.delete(cat)
                                    sess.commit()
                                    dlg.close()
                                    ui.notify(f"Deleted '{cat_name}'.", type="positive")
                                    on_refresh()
                            finally:
                                sess.close()

                        ui.button("Delete", on_click=_do_delete).props("color=negative")
                dlg.open()
            return _delete

        has_products = node["total_count"] > 0
        del_btn = ui.button(
            icon="delete",
            on_click=_make_delete(
                node["id"], node["name"], has_products, bool(node["children"])
            ),
        ).props(
            f"flat dense round size=sm color={'grey' if has_products else 'negative'}"
            + (" disable" if has_products else "")
        )
        if has_products:
            del_btn.tooltip(f"Has {node['total_count']} product(s) - cannot delete")

    # Render children recursively
    for child in node["children"]:
        _render_category_node(child, depth + 1, on_refresh)


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
