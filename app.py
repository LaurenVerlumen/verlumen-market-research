"""Verlumen Market Research Tool - Main entry point."""
from nicegui import ui

from config import APP_TITLE, APP_PORT
from src.models import init_db
from src.ui.pages.dashboard import dashboard_page
from src.ui.pages.import_page import import_page
from src.ui.pages.products import products_page
from src.ui.pages.product_detail import product_detail_page
from src.ui.pages.research import research_page
from src.ui.pages.export_page import export_page
from src.ui.pages.settings import settings_page

# Initialize database tables on startup
init_db()


@ui.page("/")
def index():
    dashboard_page()


@ui.page("/import")
def import_view():
    import_page()


@ui.page("/products")
def products_view():
    products_page()


@ui.page("/products/{product_id}")
def product_detail_view(product_id: int):
    product_detail_page(product_id)


@ui.page("/research")
def research_view():
    research_page()


@ui.page("/export")
def export_view():
    export_page()


@ui.page("/settings")
def settings_view():
    settings_page()


ui.run(
    title=APP_TITLE,
    port=APP_PORT,
    reload=False,
    dark=False,
)
