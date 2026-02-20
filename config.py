"""Application configuration."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "verlumen.db"
EXPORTS_DIR = DATA_DIR / "exports"
IMAGES_DIR = DATA_DIR / "images"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
EXPORTS_DIR.mkdir(exist_ok=True)
IMAGES_DIR.mkdir(exist_ok=True)

# Database
DATABASE_URL = f"sqlite:///{DB_PATH}"

# SerpAPI
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

# Amazon settings
AMAZON_DOMAIN = "amazon.com"
AMAZON_MARKETPLACE = "US"

# Amazon department mapping: category name (case-insensitive) → SerpAPI amazon_department
# "aps" means "All Departments" (no filter)
AMAZON_DEPARTMENT_MAP: dict[str, str] = {
    "juegos 3 anos": "toys-and-games",
    "juegos baby": "baby-products",
    "puzzles": "toys-and-games",
    "montessori": "toys-and-games",
    "toys": "toys-and-games",
    "baby": "baby-products",
    "arts & crafts": "arts-crafts-sewing",
    "arts and crafts": "arts-crafts-sewing",
    "outdoor": "toys-and-games",
    "educational": "toys-and-games",
    "wooden toys": "toys-and-games",
}
# Default department for categories not in the map (Verlumen is a toy company)
AMAZON_DEPARTMENT_DEFAULT = "toys-and-games"

# All available Amazon departments for the Settings UI dropdown
AMAZON_DEPARTMENTS: dict[str, str] = {
    "aps": "All Departments",
    "toys-and-games": "Toys & Games",
    "baby-products": "Baby",
    "arts-crafts-sewing": "Arts, Crafts & Sewing",
    "office-products": "Office Products",
    "home-garden": "Home & Garden",
    "sporting-goods": "Sports & Outdoors",
}

# App settings
APP_TITLE = "Verlumen Market Research"
APP_PORT = 8080
