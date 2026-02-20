"""Shared layout: header, sidebar navigation, and content area."""
from pathlib import Path

from nicegui import app, ui

# Serve the public directory for static assets (logo, images)
_PUBLIC_DIR = Path(__file__).resolve().parent.parent.parent / "public"
app.add_static_files("/public", str(_PUBLIC_DIR))


NAV_ITEMS = [
    {"label": "Dashboard", "icon": "dashboard", "path": "/"},
    {"label": "Products", "icon": "inventory_2", "path": "/products"},
    {"label": "Export", "icon": "file_download", "path": "/export"},
    {"label": "Settings", "icon": "settings", "path": "/settings"},
]

# JavaScript to highlight the current sidebar nav link on page load.
# Finds <a> tags in the sidebar whose href matches the current path,
# then styles the first child row div as the active link.
_ACTIVE_NAV_JS = """
(function() {
    var path = window.location.pathname;
    var links = document.querySelectorAll('.q-drawer a[href]');
    links.forEach(function(a) {
        var href = a.getAttribute('href');
        var isActive = (href === '/' && path === '/') ||
                       (href !== '/' && path.startsWith(href));
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
    """Create the shared page layout with sidebar navigation.

    Call this at the top of every page function, then add content
    into the returned container.
    """
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
        ui.space()

    # Left drawer (sidebar nav) with logo icon at top
    with ui.left_drawer(value=True).classes("bg-grey-1") as drawer:
        drawer.props("width=220 bordered")
        with ui.column().classes("items-center py-3"):
            ui.image("/public/images/logo-icon.svg").classes("w-10")
        ui.separator().classes("mb-2")
        for item in NAV_ITEMS:
            _nav_link(item["label"], item["icon"], item["path"])

    # Highlight active sidebar nav link after page loads
    ui.timer(0.1, lambda: ui.run_javascript(_ACTIVE_NAV_JS), once=True)

    # Main content container
    content = ui.column().classes("w-full p-4 max-w-7xl mx-auto gap-4")
    return content


def _nav_link(label: str, icon: str, path: str):
    """Render a single sidebar nav item."""
    with ui.link(target=path).classes("no-underline w-full"):
        with ui.row().classes(
            "items-center gap-3 px-4 py-2 rounded-lg w-full "
            "hover:bg-blue-50 cursor-pointer"
        ):
            ui.icon(icon).classes("text-secondary")
            ui.label(label).classes("text-body1 text-secondary")
