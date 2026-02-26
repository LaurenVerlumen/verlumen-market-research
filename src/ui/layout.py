"""Shared layout: header, sidebar navigation, and content area."""
from pathlib import Path

from nicegui import app, ui
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from src.models.database import get_session
from src.models.category import Category
from src.ui.components.helpers import HOVER_BG, NAV_ACTIVE_BG, NAV_ACTIVE_BORDER, NAV_ACTIVE_TEXT

# Serve the public directory for static assets (logo, images)
_PUBLIC_DIR = Path(__file__).resolve().parent.parent.parent / "public"
app.add_static_files("/public", str(_PUBLIC_DIR))

# Global reference so other pages (e.g. Settings) can call refresh_nav_categories()
_nav_categories_refreshable = None


# JavaScript to highlight the current sidebar nav link on page load.
_ACTIVE_NAV_JS = f"""
(function() {{
    var path = window.location.pathname;
    var search = window.location.search;
    var full = path + search;
    var links = document.querySelectorAll('.q-drawer a[href]');
    links.forEach(function(a) {{
        var href = a.getAttribute('href');
        var isActive = false;
        if (href.indexOf('?') !== -1) {{
            isActive = (full === href);
        }} else if (href === '/') {{
            isActive = (path === '/');
        }} else if (href === '/products') {{
            isActive = (path === '/products' && search === '');
        }} else {{
            isActive = path.startsWith(href);
        }}
        if (isActive) {{
            var row = a.querySelector('.row, .q-item');
            if (row) {{
                row.style.background = '{NAV_ACTIVE_BG}';
                row.style.borderLeft = '3px solid {NAV_ACTIVE_BORDER}';
            }}
            a.querySelectorAll('.text-secondary').forEach(function(child) {{
                child.style.color = '{NAV_ACTIVE_TEXT}';
                child.style.fontWeight = '600';
            }});
        }}
    }});
}})();
"""


def build_layout(title: str = "Verlumen Market Research"):
    """Create the shared page layout with sidebar navigation."""
    global _nav_categories_refreshable

    ui.colors(
        primary="#4A4443",
        secondary="#5f6368",
        accent="#A08968",
        positive="#34a853",
        negative="#ea4335",
    )

    # Header with Verlumen logo
    with ui.header().classes("items-center justify-between px-4 bg-primary"):
        with ui.row().classes("items-center gap-3"):
            ui.image("/public/images/logo-white.svg").classes("w-28")
            ui.separator().props("vertical").classes("bg-white opacity-30")
            ui.label("Market Research").classes("text-subtitle1 text-white")

        # Global search
        from urllib.parse import quote
        _search = ui.input(placeholder="Search products...").classes("w-64").props(
            "dark dense standout='bg-white/10' input-class='text-white'"
        )
        _search.props('prepend-inner-icon="search"')

        def _do_global_search(e=None):
            q = _search.value
            if q and q.strip():
                ui.navigate.to(f"/products?search={quote(q.strip())}")

        _search.on("keydown.enter", _do_global_search)

        ui.space()

    # Left drawer (sidebar nav)
    with ui.left_drawer(value=True).classes("bg-grey-1") as drawer:
        drawer.props("width=260 bordered")
        ui.element("div").classes("h-3")

        _nav_link("Dashboard", "dashboard", "/")
        _nav_link("Products", "inventory_2", "/products")

        # Refreshable category sub-links (hierarchical tree)
        @ui.refreshable
        def _category_nav():
            tree = _load_category_tree()
            if tree:
                with ui.column().classes("w-full pl-4 gap-0"):
                    for node in tree:
                        _render_nav_node(node, depth=0)

        _category_nav()
        _nav_categories_refreshable = _category_nav

        _nav_link("Export", "file_download", "/export")
        _nav_link("Marketplace Gap", "compare_arrows", "/marketplace-gap")

        # Recycle Bin with deleted product count
        @ui.refreshable
        def _recycle_bin_nav():
            from src.models import Product as _P
            _db = get_session()
            try:
                _del_count = _db.query(_P).filter(_P.status == "deleted").count()
            finally:
                _db.close()
            with ui.link(target="/recycle-bin").classes("no-underline w-full"):
                with ui.row().classes(
                    "items-center gap-3 px-4 py-2 rounded-lg w-full "
                    f"{HOVER_BG} cursor-pointer"
                ):
                    ui.icon("delete_sweep").classes("text-secondary")
                    ui.label("Recycle Bin").classes("text-body1 text-secondary flex-1")
                    if _del_count > 0:
                        ui.badge(str(_del_count), color="negative").props("rounded dense")

        _recycle_bin_nav()

        _nav_link("Settings", "settings", "/settings")

        # --- Git Sync section ---
        ui.separator().classes("my-2")
        _render_sync_section()

    # Highlight active sidebar nav link after page loads
    ui.timer(0.1, lambda: ui.run_javascript(_ACTIVE_NAV_JS), once=True)

    # Main content container
    content = ui.column().classes("w-full p-6 max-w-7xl mx-auto gap-4")
    return content


def refresh_nav_categories():
    """Refresh the category sub-links in the sidebar. Call from any page."""
    global _nav_categories_refreshable
    if _nav_categories_refreshable is not None:
        try:
            _nav_categories_refreshable.refresh()
        except Exception:
            pass


def _render_sync_section():
    """Render the Git Sync button and backup status at the bottom of the sidebar."""
    import asyncio
    from src.services.db_backup import get_last_backup_time, sync_to_git, get_git_sync_status

    with ui.column().classes("w-full px-4 gap-2"):

        # Refreshable status area
        @ui.refreshable
        def _sync_status_display():
            sync_status = get_git_sync_status()
            last_backup = get_last_backup_time()

            # Last backup time
            if last_backup:
                time_str = last_backup.strftime("%H:%M")
                ui.label(f"Last backup: {time_str}").classes(
                    "text-caption text-grey-6"
                )

            # Sync status indicator
            if sync_status.get("needs_commit") or sync_status.get("needs_push"):
                with ui.row().classes("items-center gap-1"):
                    ui.icon("circle", size="xs").classes("text-warning")
                    ui.label("Unsaved changes").classes("text-caption text-warning")
            else:
                with ui.row().classes("items-center gap-1"):
                    ui.icon("check_circle", size="xs").classes("text-positive")
                    ui.label("All saved").classes("text-caption text-positive")

        _sync_status_display()

        # Sync button
        sync_btn = ui.button("Save & Backup", icon="cloud_done").props(
            "color=primary outline dense size=sm"
        ).classes("w-full")
        sync_label = ui.label("").classes("text-caption text-center w-full")

        async def _do_sync():
            sync_btn.disable()
            sync_label.text = "Saving..."
            sync_label.classes(replace="text-caption text-center w-full text-primary")

            result = await asyncio.get_event_loop().run_in_executor(None, sync_to_git)

            if result["success"]:
                sync_label.text = result["message"]
                sync_label.classes(replace="text-caption text-center w-full text-positive")
                ui.notify(result["message"], type="positive")
            else:
                sync_label.text = result["message"]
                sync_label.classes(replace="text-caption text-center w-full text-negative")
                ui.notify(result["message"], type="negative")

            # Refresh status indicator after sync
            _sync_status_display.refresh()
            sync_btn.enable()

        sync_btn.on_click(_do_sync)


def _load_category_tree() -> list[dict]:
    """Load categories as nested dicts with product counts for the nav.

    Only includes categories that have products (directly or via descendants).
    Returns: [{id, name, count, total_count, children: [...]}]
    """
    from src.models import Product
    db = get_session()
    try:
        # Single query for all product counts (exclude deleted)
        count_rows = (
            db.query(Product.category_id, func.count(Product.id))
            .filter(Product.status != "deleted")
            .group_by(Product.category_id)
            .all()
        )
        prod_counts = {cid: cnt for cid, cnt in count_rows}

        # Load root categories (eager-load the full tree to avoid N+1 queries)
        roots = (
            db.query(Category)
            .options(selectinload(Category.children, recursion_depth=-1))
            .filter(Category.parent_id.is_(None))
            .order_by(Category.sort_order, Category.name)
            .all()
        )

        def _build_node(cat):
            own_count = prod_counts.get(cat.id, 0)
            children = []
            for child in cat.children:
                child_node = _build_node(child)
                if child_node is not None:
                    children.append(child_node)
            total_count = own_count + sum(c["total_count"] for c in children)
            # Skip entirely if no products in this subtree
            if total_count == 0:
                return None
            return {
                "id": cat.id,
                "name": cat.name,
                "count": own_count,
                "total_count": total_count,
                "children": children,
            }

        result = []
        for r in roots:
            node = _build_node(r)
            if node is not None:
                result.append(node)
        return result
    finally:
        db.close()


def _render_nav_node(node, depth=0):
    """Render a category node in the sidebar nav as a simple indented link."""
    indent = depth * 16

    # Show the category itself as a clickable link
    count = node["total_count"]
    with ui.link(target=f"/products?category_id={node['id']}").classes("no-underline w-full"):
        with ui.row().classes(
            "items-center gap-2 px-3 py-1 rounded w-full "
            f"{HOVER_BG} cursor-pointer"
        ).style(f"min-height: 28px; padding-left: {indent}px"):
            icon = "folder" if node["children"] else "label"
            ui.icon(icon, size="xs").classes("text-accent")
            ui.label(node["name"]).classes("text-body2 text-secondary flex-1")
            ui.badge(str(count), color="grey-4").props(
                "rounded dense"
            ).classes("text-grey-8")

    # Render children indented below
    for child in node["children"]:
        _render_nav_node(child, depth + 1)


def _nav_link(label: str, icon: str, path: str):
    """Render a main sidebar nav item."""
    with ui.link(target=path).classes("no-underline w-full"):
        with ui.row().classes(
            "items-center gap-3 px-4 py-2 rounded-lg w-full "
            f"{HOVER_BG} cursor-pointer"
        ):
            ui.icon(icon).classes("text-secondary")
            ui.label(label).classes("text-body1 text-secondary")


