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
        if "status" not in columns:
            logger.info("Adding status column to products table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE products ADD COLUMN status TEXT DEFAULT 'imported'"
                ))
    if "amazon_competitors" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("amazon_competitors")}
        if "match_score" not in columns:
            logger.info("Adding match_score column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN match_score FLOAT"
                ))
        if "reviewed" not in columns:
            logger.info("Adding reviewed column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN reviewed BOOLEAN DEFAULT 0"
                ))


def _migrate_indexes():
    """Create indexes on FK columns for existing databases."""
    _indexes = [
        ("ix_products_category_id", "products", "category_id"),
        ("ix_amazon_competitors_product_id", "amazon_competitors", "product_id"),
        ("ix_amazon_competitors_search_session_id", "amazon_competitors", "search_session_id"),
        ("ix_search_sessions_product_id", "search_sessions", "product_id"),
    ]
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    with engine.begin() as conn:
        for idx_name, table, column in _indexes:
            if table not in tables:
                continue
            existing = {idx["name"] for idx in inspector.get_indexes(table)}
            if idx_name not in existing:
                logger.info("Creating index %s on %s.%s", idx_name, table, column)
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({column})"
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
    _migrate_indexes()
