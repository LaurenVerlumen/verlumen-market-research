"""Verlumen Market Research Tool - Main entry point."""
from nicegui import app, ui

from config import APP_TITLE, APP_PORT, APP_HOST, IMAGES_DIR
from src.models import init_db
from src.ui.pages.dashboard import dashboard_page
from src.ui.pages.products import products_page
from src.ui.pages.product_detail import product_detail_page
from src.ui.pages.export_page import export_page
from src.ui.pages.settings import settings_page

# Initialize database tables on startup
init_db()

# Start background scheduler (if enabled in config)
from src.services.scheduler import start_scheduler
start_scheduler()

# Serve locally-saved product images
app.add_static_files("/images", str(IMAGES_DIR))


@ui.page("/")
def index():
    dashboard_page()


@ui.page("/products")
def products_view(category: str | None = None, search: str | None = None):
    products_page(category=category, search=search)


@ui.page("/products/{product_id}")
def product_detail_view(product_id: int):
    product_detail_page(product_id)


@ui.page("/export")
def export_view():
    export_page()


@ui.page("/settings")
def settings_view():
    settings_page()


# Backward-compatibility redirects for old bookmarks
@ui.page("/import")
def import_redirect():
    ui.navigate.to("/products")


@ui.page("/research")
def research_redirect():
    ui.navigate.to("/products")


@ui.page("/evaluation")
def evaluation_redirect():
    ui.navigate.to("/products")


@app.get("/_health")
async def health_check():
    return {"status": "ok", "app": "verlumen-market-research"}


ui.run(
    title=APP_TITLE,
    host=APP_HOST,
    port=APP_PORT,
    reload=False,
    dark=False,
)
