"""Review analysis model - stores mined review insights per competitor."""
from datetime import datetime

from sqlalchemy import Integer, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.database import Base


class ReviewAnalysis(Base):
    __tablename__ = "review_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    asin: Mapped[str] = mapped_column(Text, nullable=False)
    competitor_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    aspects_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of aspect objects
    raw_insights_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # Full SerpAPI response
    ai_synthesis: Mapped[str | None] = mapped_column(Text, nullable=True)  # Per-competitor synthesis
    product_synthesis: Mapped[str | None] = mapped_column(Text, nullable=True)  # Aggregate synthesis across all competitors
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_reviews: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    product = relationship("Product")
