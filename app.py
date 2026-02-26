"""Verlumen Market Research Tool - Main entry point."""
from nicegui import app, ui

from config import APP_TITLE, APP_PORT, APP_HOST, IMAGES_DIR
from src.services.db_backup import startup_backup, shutdown_backup, backup_to_sql
from src.models import init_db
from src.ui.pages.dashboard import dashboard_page
from src.ui.pages.products import products_page
from src.ui.pages.product_detail import product_detail_page
from src.ui.pages.export_page import export_page
from src.ui.pages.recycle_bin import recycle_bin_page
from src.ui.pages.settings import settings_page
from src.ui.pages.marketplace_gap import marketplace_gap_page

# Restore DB from backup if missing, then create a fresh backup
startup_backup()

# Initialize database tables on startup
init_db()

# Start background scheduler (if enabled in config)
from src.services.scheduler import start_scheduler
start_scheduler()

# Backup DB on shutdown
app.on_shutdown(shutdown_backup)

# Periodic auto-backup every 30 minutes
import asyncio

async def _periodic_backup():
    while True:
        await asyncio.sleep(30 * 60)
        backup_to_sql()

app.on_startup(lambda: asyncio.create_task(_periodic_backup()))

# Serve locally-saved product images
app.add_static_files("/images", str(IMAGES_DIR))


@ui.page("/")
def index():
    dashboard_page()


@ui.page("/products")
def products_view(
    category: str | None = None,
    category_id: int | None = None,
    search: str | None = None,
):
    products_page(category=category, category_id=category_id, search=search)


@ui.page("/products/{product_id}")
def product_detail_view(product_id: int):
    product_detail_page(product_id)


@ui.page("/export")
def export_view():
    export_page()


@ui.page("/marketplace-gap")
def marketplace_gap_view():
    marketplace_gap_page()


@ui.page("/recycle-bin")
def recycle_bin_view():
    recycle_bin_page()


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
