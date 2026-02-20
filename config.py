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

# App settings
APP_TITLE = "Verlumen Market Research"
APP_PORT = 8080
