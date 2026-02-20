"""Verlumen Market Research Tool - Main entry point."""
from nicegui import app, ui

from config import APP_TITLE, APP_PORT, IMAGES_DIR
from src.models import init_db
from src.ui.pages.dashboard import dashboard_page
from src.ui.pages.products import products_page
from src.ui.pages.product_detail import product_detail_page
from src.ui.pages.export_page import export_page
from src.ui.pages.settings import settings_page

# Initialize database tables on startup
init_db()

# Serve locally-saved product images
app.add_static_files("/images", str(IMAGES_DIR))


@ui.page("/")
def index():
    dashboard_page()


@ui.page("/products")
def products_view():
    products_page()


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


ui.run(
    title=APP_TITLE,
    port=APP_PORT,
    reload=False,
    dark=False,
)
