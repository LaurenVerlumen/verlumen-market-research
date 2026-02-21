"""Shared layout: header, sidebar navigation, and content area."""
from pathlib import Path
from urllib.parse import quote

from nicegui import app, ui

from src.models.database import get_session
from src.models.category import Category

# Serve the public directory for static assets (logo, images)
_PUBLIC_DIR = Path(__file__).resolve().parent.parent.parent / "public"
app.add_static_files("/public", str(_PUBLIC_DIR))

# Global reference so other pages (e.g. Settings) can call refresh_nav_categories()
_nav_categories_refreshable = None


# JavaScript to highlight the current sidebar nav link on page load.
_ACTIVE_NAV_JS = """
(function() {
    var path = window.location.pathname;
    var search = window.location.search;
    var full = path + search;
    var links = document.querySelectorAll('.q-drawer a[href]');
    links.forEach(function(a) {
        var href = a.getAttribute('href');
        var isActive = false;
        if (href.indexOf('?') !== -1) {
            isActive = (full === href);
        } else if (href === '/') {
            isActive = (path === '/');
        } else if (href === '/products') {
            isActive = (path === '/products' && search === '');
        } else {
            isActive = path.startsWith(href);
        }
        if (isActive) {
            var row = a.querySelector('.row, .q-item');
            if (row) {
                row.style.background = '#E8E0D6';
                row.style.borderLeft = '3px solid #A08968';
            }
            a.querySelectorAll('.text-secondary').forEach(function(child) {
                child.style.color = '#4A4443';
                child.style.fontWeight = '600';
            });
        }
    });
})();
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
        drawer.props("width=220 bordered")
        ui.element("div").classes("h-3")

        _nav_link("Dashboard", "dashboard", "/")
        _nav_link("Products", "inventory_2", "/products")

        # Refreshable category sub-links
        @ui.refreshable
        def _category_nav():
            categories = _load_categories()
            if categories:
                with ui.column().classes("w-full pl-6 gap-0"):
                    for cat in categories:
                        _nav_sub_link(cat["name"], cat["count"])

        _category_nav()
        _nav_categories_refreshable = _category_nav

        _nav_link("Export", "file_download", "/export")
        _nav_link("Settings", "settings", "/settings")

    # Highlight active sidebar nav link after page loads
    ui.timer(0.1, lambda: ui.run_javascript(_ACTIVE_NAV_JS), once=True)

    # Main content container
    content = ui.column().classes("w-full p-4 max-w-7xl mx-auto gap-4")
    return content


def refresh_nav_categories():
    """Refresh the category sub-links in the sidebar. Call from any page."""
    global _nav_categories_refreshable
    if _nav_categories_refreshable is not None:
        try:
            _nav_categories_refreshable.refresh()
        except Exception:
            pass


def _load_categories() -> list[dict]:
    """Load categories with product counts for the nav."""
    from src.models import Product
    db = get_session()
    try:
        cats = db.query(Category).order_by(Category.name).all()
        result = []
        for c in cats:
            count = db.query(Product).filter(Product.category_id == c.id).count()
            result.append({"name": c.name, "count": count})
        return result
    finally:
        db.close()


def _nav_link(label: str, icon: str, path: str):
    """Render a main sidebar nav item."""
    with ui.link(target=path).classes("no-underline w-full"):
        with ui.row().classes(
            "items-center gap-3 px-4 py-2 rounded-lg w-full "
            "hover:bg-blue-50 cursor-pointer"
        ):
            ui.icon(icon).classes("text-secondary")
            ui.label(label).classes("text-body1 text-secondary")


def _nav_sub_link(name: str, count: int):
    """Render a category sub-link under Products."""
    encoded_path = f"/products?category={quote(name)}"
    with ui.link(target=encoded_path).classes("no-underline w-full"):
        with ui.row().classes(
            "items-center gap-2 px-3 py-1 rounded w-full "
            "hover:bg-blue-50 cursor-pointer"
        ).style("min-height: 32px"):
            ui.icon("label", size="xs").classes("text-accent")
            ui.label(name).classes("text-body2 text-secondary flex-1")
            ui.badge(str(count), color="grey-4").props(
                "rounded dense"
            ).classes("text-grey-8")
