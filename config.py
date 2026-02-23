"""Application configuration."""
import json
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
DEPARTMENT_MAPPING_FILE = DATA_DIR / "department_mapping.json"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
EXPORTS_DIR.mkdir(exist_ok=True)
IMAGES_DIR.mkdir(exist_ok=True)

# Database
DATABASE_URL = f"sqlite:///{DB_PATH}"

# SerpAPI
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

# Anthropic API (for AI GTM Brief)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Amazon SP-API credentials
SP_API_REFRESH_TOKEN = os.getenv("SP_API_REFRESH_TOKEN", "")
SP_API_LWA_APP_ID = os.getenv("SP_API_LWA_APP_ID", "")
SP_API_LWA_CLIENT_SECRET = os.getenv("SP_API_LWA_CLIENT_SECRET", "")
SP_API_AWS_ACCESS_KEY = os.getenv("SP_API_AWS_ACCESS_KEY", "")
SP_API_AWS_SECRET_KEY = os.getenv("SP_API_AWS_SECRET_KEY", "")
SP_API_ROLE_ARN = os.getenv("SP_API_ROLE_ARN", "")

# Amazon settings
AMAZON_DOMAIN = "amazon.com"
AMAZON_MARKETPLACE = "US"

# Supported Amazon marketplaces for research
AMAZON_MARKETPLACES = {
    "amazon.com": {"label": "US (amazon.com)", "currency": "USD", "flag": "\U0001f1fa\U0001f1f8"},
    "amazon.co.uk": {"label": "UK (amazon.co.uk)", "currency": "GBP", "flag": "\U0001f1ec\U0001f1e7"},
    "amazon.de": {"label": "Germany (amazon.de)", "currency": "EUR", "flag": "\U0001f1e9\U0001f1ea"},
    "amazon.ca": {"label": "Canada (amazon.ca)", "currency": "CAD", "flag": "\U0001f1e8\U0001f1e6"},
    "amazon.co.jp": {"label": "Japan (amazon.co.jp)", "currency": "JPY", "flag": "\U0001f1ef\U0001f1f5"},
    "amazon.es": {"label": "Spain (amazon.es)", "currency": "EUR", "flag": "\U0001f1ea\U0001f1f8"},
    "amazon.fr": {"label": "France (amazon.fr)", "currency": "EUR", "flag": "\U0001f1eb\U0001f1f7"},
    "amazon.it": {"label": "Italy (amazon.it)", "currency": "EUR", "flag": "\U0001f1ee\U0001f1f9"},
}

# Amazon department mapping: category name (case-insensitive) → SerpAPI amazon_department
# "aps" means "All Departments" (no filter)
_DEFAULT_DEPARTMENT_MAP: dict[str, str] = {
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


def _load_department_map() -> dict[str, str]:
    """Load department mapping from JSON file, falling back to defaults."""
    mapping = dict(_DEFAULT_DEPARTMENT_MAP)
    if DEPARTMENT_MAPPING_FILE.exists():
        try:
            with open(DEPARTMENT_MAPPING_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                mapping.update(saved)
        except (json.JSONDecodeError, OSError):
            pass
    return mapping


def save_department_map(mapping: dict[str, str]) -> None:
    """Persist the department mapping to a JSON file."""
    try:
        with open(DEPARTMENT_MAPPING_FILE, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


AMAZON_DEPARTMENT_MAP: dict[str, str] = _load_department_map()
# Default department for categories not in the map (Verlumen is a toy company)
AMAZON_DEPARTMENT_DEFAULT = "toys-and-games"

# All available Amazon departments for the Settings UI dropdown
AMAZON_DEPARTMENTS: dict[str, str] = {
    "aps": "All Departments",
    "toys-and-games": "Toys & Games",
    "baby-products": "Baby",
    "arts-crafts-sewing": "Arts, Crafts & Sewing",
    "home-garden": "Home & Kitchen",
    "sporting-goods": "Sports & Outdoors",
    "office-products": "Office Products",
    "books": "Books",
    "electronics": "Electronics",
    "fashion": "Clothing, Shoes & Jewelry",
    "beauty": "Beauty & Personal Care",
    "hpc": "Health, Household & Baby Care",
    "pets": "Pet Supplies",
    "grocery": "Grocery & Gourmet Food",
    "garden": "Patio, Lawn & Garden",
    "tools": "Tools & Home Improvement",
    "automotive": "Automotive",
    "musical-instruments": "Musical Instruments",
    "handmade": "Handmade",
    "industrial": "Industrial & Scientific",
    "software": "Software",
    "videogames": "Video Games",
    "gift-cards": "Gift Cards",
    "collectibles": "Collectibles & Fine Art",
    "appliances": "Appliances",
}

# App settings
APP_TITLE = "Verlumen Market Research"
APP_PORT = 8080
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
