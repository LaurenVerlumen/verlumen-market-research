"""Search session model -- tracks each Amazon search run."""
from datetime import datetime

from sqlalchemy import Integer, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.database import Base


class SearchSession(Base):
    __tablename__ = "search_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False)
    search_query: Mapped[str] = mapped_column(Text, nullable=False)
    amazon_domain: Mapped[str | None] = mapped_column(Text, default="amazon.com")
    total_results: Mapped[int | None] = mapped_column(Integer, nullable=True)
    organic_results: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sponsored_results: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_reviews: Mapped[int | None] = mapped_column(Integer, nullable=True)
    serpapi_search_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="search_sessions")
    amazon_competitors = relationship("AmazonCompetitor", back_populates="search_session")

    def __repr__(self) -> str:
        return f"<SearchSession id={self.id} query={self.search_query!r}>"
