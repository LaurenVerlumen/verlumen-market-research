"""Database engine, session factory, and base model."""
import logging
from contextlib import contextmanager

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


@contextmanager
def with_db():
    """Context manager that yields a DB session and auto-closes it.

    Usage::

        with with_db() as db:
            products = db.query(Product).all()
        # session is closed automatically, even on exception
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _migrate_categories_hierarchy():
    """Migrate categories table to support hierarchical tree (parent_id, level, etc.).

    SQLite cannot ALTER TABLE to drop UNIQUE constraints, so we recreate the table.
    """
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if "categories" not in tables:
        return  # Table doesn't exist yet; create_all will handle it

    columns = {col["name"] for col in inspector.get_columns("categories")}
    if "parent_id" in columns:
        return  # Already migrated

    logger.info("Migrating categories table to hierarchical model...")

    # Check if a previous migration was interrupted
    if "_categories_old" not in tables:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE categories RENAME TO _categories_old"))
        logger.info("Renamed categories -> _categories_old")

    # Import model so Base.metadata knows about the new schema
    import src.models.category  # noqa: F401

    # Create the new categories table from the updated model
    from src.models.category import Category
    Category.__table__.create(bind=engine, checkfirst=True)
    logger.info("Created new categories table with hierarchy columns")

    # Copy data from old table (all become root-level)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO categories (id, name, description, created_at, parent_id, level, sort_order, amazon_department)
            SELECT id, name, description, created_at, NULL, 0, 0, NULL
            FROM _categories_old
        """))
        logger.info("Copied existing categories as root-level nodes")

        # Migrate department mappings from config into amazon_department column
        from config import AMAZON_DEPARTMENT_MAP
        for cat_name_lower, dept in AMAZON_DEPARTMENT_MAP.items():
            conn.execute(
                text("UPDATE categories SET amazon_department = :dept WHERE LOWER(name) = :name"),
                {"dept": dept, "name": cat_name_lower},
            )

        conn.execute(text("DROP TABLE _categories_old"))
        logger.info("Dropped _categories_old")

    logger.info("Categories hierarchy migration complete")


def _seed_toys_and_games():
    """Seed the Toys & Games category tree with Amazon subcategories."""
    session = SessionLocal()
    try:
        from src.models.category import Category

        # Check if already seeded
        existing = session.query(Category).filter_by(name="Toys & Games", parent_id=None).first()
        if existing:
            return

        # Don't seed if there are already categories (user has their own)
        count = session.query(Category).count()
        if count > 0:
            # Only seed if no root "Toys & Games" exists
            pass

        # Root: Toys & Games
        toys_root = Category(
            name="Toys & Games",
            level=0,
            sort_order=0,
            amazon_department="toys-and-games",
        )
        session.add(toys_root)
        session.flush()

        subcategories = [
            "Action Figures & Statues",
            "Arts & Crafts",
            "Baby & Toddler Toys",
            "Building Toys",
            "Dolls & Accessories",
            "Dress Up & Pretend Play",
            "Electronics for Kids",
            "Games & Accessories",
            "Growing & Development",
            "Kids' Furniture Decor & Storage",
            "Learning & Education",
            "Novelty & Gag Toys",
            "Outdoor Play",
            "Party Supplies",
            "Puppets & Puppet Theaters",
            "Puzzles",
            "Sports & Outdoor Play",
            "Stuffed Animals & Plush Toys",
            "Toy Vehicles",
            "Tricycles Scooters & Wagons",
        ]

        for i, name in enumerate(subcategories):
            session.add(Category(
                name=name,
                parent_id=toys_root.id,
                level=1,
                sort_order=i,
            ))

        # Root: Baby Products
        baby_root = Category(
            name="Baby Products",
            level=0,
            sort_order=1,
            amazon_department="baby-products",
        )
        session.add(baby_root)

        session.commit()
        logger.info("Seeded Toys & Games tree with %d subcategories + Baby Products", len(subcategories))
    except Exception:
        session.rollback()
        logger.exception("Failed to seed categories")
    finally:
        session.close()


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
        if "decision_log" not in columns:
            logger.info("Adding decision_log column to products table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE products ADD COLUMN decision_log TEXT DEFAULT '[]'"
                ))
        if "profitability_data" not in columns:
            logger.info("Adding profitability_data column to products table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE products ADD COLUMN profitability_data TEXT"
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
        if "brand" not in columns:
            logger.info("Adding brand column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN brand TEXT"
                ))
        if "manufacturer" not in columns:
            logger.info("Adding manufacturer column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN manufacturer TEXT"
                ))
        if "monthly_sales" not in columns:
            logger.info("Adding monthly_sales column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN monthly_sales INTEGER"
                ))
        if "monthly_revenue" not in columns:
            logger.info("Adding monthly_revenue column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN monthly_revenue FLOAT"
                ))
        if "seller" not in columns:
            logger.info("Adding seller column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN seller TEXT"
                ))
        if "seller_country" not in columns:
            logger.info("Adding seller_country column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN seller_country TEXT"
                ))
        if "fba_fees" not in columns:
            logger.info("Adding fba_fees column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN fba_fees FLOAT"
                ))
        if "review_velocity" not in columns:
            logger.info("Adding review_velocity column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN review_velocity FLOAT"
                ))
        if "fulfillment" not in columns:
            logger.info("Adding fulfillment column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN fulfillment TEXT"
                ))
        if "active_sellers" not in columns:
            logger.info("Adding active_sellers column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN active_sellers INTEGER"
                ))
        if "listing_created_at" not in columns:
            logger.info("Adding listing_created_at column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN listing_created_at TEXT"
                ))
        if "seller_age_months" not in columns:
            logger.info("Adding seller_age_months column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN seller_age_months INTEGER"
                ))
        if "buy_box_owner" not in columns:
            logger.info("Adding buy_box_owner column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN buy_box_owner TEXT"
                ))
        if "size_tier" not in columns:
            logger.info("Adding size_tier column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN size_tier TEXT"
                ))
        if "dimensions" not in columns:
            logger.info("Adding dimensions column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN dimensions TEXT"
                ))
        if "weight" not in columns:
            logger.info("Adding weight column to amazon_competitors table")
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE amazon_competitors ADD COLUMN weight FLOAT"
                ))


def _migrate_indexes():
    """Create indexes on FK and commonly-queried columns for existing databases."""
    # Single-column indexes
    _indexes = [
        ("ix_products_category_id", "products", "category_id"),
        ("ix_amazon_competitors_product_id", "amazon_competitors", "product_id"),
        ("ix_amazon_competitors_search_session_id", "amazon_competitors", "search_session_id"),
        ("ix_amazon_competitors_position", "amazon_competitors", "position"),
        ("ix_search_sessions_product_id", "search_sessions", "product_id"),
        ("ix_categories_parent_id", "categories", "parent_id"),
    ]
    # Composite indexes
    _composite_indexes = [
        ("ix_products_status_created_at", "products", "status, created_at"),
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
        for idx_name, table, columns in _composite_indexes:
            if table not in tables:
                continue
            existing = {idx["name"] for idx in inspector.get_indexes(table)}
            if idx_name not in existing:
                logger.info("Creating index %s on %s(%s)", idx_name, table, columns)
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({columns})"
                ))


def init_db():
    """Create all tables defined by Base subclasses."""
    # Import all models so they register with Base.metadata
    import src.models.category  # noqa: F401
    import src.models.product  # noqa: F401
    import src.models.search_session  # noqa: F401
    import src.models.amazon_competitor  # noqa: F401
    import src.models.search_cache_model  # noqa: F401
    import src.models.review_analysis  # noqa: F401

    # Migrate categories table to hierarchical schema BEFORE create_all
    _migrate_categories_hierarchy()

    Base.metadata.create_all(bind=engine)
    _migrate_columns()
    _migrate_indexes()

    # Seed default category tree
    _seed_toys_and_games()
