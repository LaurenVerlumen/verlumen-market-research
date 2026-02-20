"""Database engine, session factory, and base model."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import DATABASE_URL


engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_session():
    """Return a new database session."""
    return SessionLocal()


def init_db():
    """Create all tables defined by Base subclasses."""
    # Import all models so they register with Base.metadata
    import src.models.category  # noqa: F401
    import src.models.product  # noqa: F401
    import src.models.search_session  # noqa: F401
    import src.models.amazon_competitor  # noqa: F401

    Base.metadata.create_all(bind=engine)
