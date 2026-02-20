"""Product model."""
from datetime import datetime

from sqlalchemy import Integer, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id"), nullable=False)
    alibaba_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    alibaba_product_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_spanish: Mapped[str | None] = mapped_column(Text, nullable=True)
    alibaba_price_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    alibaba_price_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    alibaba_price_currency: Mapped[str | None] = mapped_column(Text, default="USD")
    alibaba_moq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alibaba_supplier: Mapped[str | None] = mapped_column(Text, nullable=True)
    alibaba_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    alibaba_fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    amazon_search_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    category = relationship("Category", back_populates="products")
    amazon_competitors = relationship("AmazonCompetitor", back_populates="product")
    search_sessions = relationship("SearchSession", back_populates="product")

    def __repr__(self) -> str:
        return f"<Product id={self.id} name={self.name!r}>"
