"""Amazon competitor model -- a single competitor product from Amazon search results."""
from datetime import datetime

from sqlalchemy import Integer, Float, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.database import Base


class AmazonCompetitor(Base):
    __tablename__ = "amazon_competitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False)
    search_session_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("search_sessions.id"), nullable=True
    )
    asin: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_currency: Mapped[str | None] = mapped_column(Text, default="USD")
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bought_last_month: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_prime: Mapped[bool] = mapped_column(Boolean, default=False)
    badge: Mapped[str | None] = mapped_column(Text, nullable=True)
    bsr_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bsr_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    amazon_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_sponsored: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="amazon_competitors")
    search_session = relationship("SearchSession", back_populates="amazon_competitors")

    def __repr__(self) -> str:
        return f"<AmazonCompetitor id={self.id} asin={self.asin!r}>"
