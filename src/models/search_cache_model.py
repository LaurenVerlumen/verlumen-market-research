"""Search cache model -- stores cached Amazon search results."""
from datetime import datetime

from sqlalchemy import Integer, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from src.models.database import Base


class SearchCacheEntry(Base):
    __tablename__ = "search_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False, default="amazon.com")
    max_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        return f"<SearchCacheEntry id={self.id} query={self.query!r}>"
