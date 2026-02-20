"""Database engine, session factory, and base model."""
import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import DATABASE_URL

logger = logging.getLogger(__name__)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_session():
    """Return a new database session."""
    return SessionLocal()


def _migrate_columns():
    """Add new columns to existing tables if missing."""
    inspector = inspect(engine)
    if "products" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("products")}
        if "local_image_path" not in columns:
            logger.info("Adding local_image_path column to products table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE products ADD COLUMN local_image_path TEXT"
                ))
    if "amazon_competitors" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("amazon_competitors")}
        if "match_score" not in columns:
            logger.info("Adding match_score column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN match_score FLOAT"
                ))


def init_db():
    """Create all tables defined by Base subclasses."""
    # Import all models so they register with Base.metadata
    import src.models.category  # noqa: F401
    import src.models.product  # noqa: F401
    import src.models.search_session  # noqa: F401
    import src.models.amazon_competitor  # noqa: F401
    import src.models.search_cache_model  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_columns()
