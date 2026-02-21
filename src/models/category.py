"""Category model - hierarchical tree with self-referencing parent."""
from datetime import datetime

from sqlalchemy import Integer, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.database import Base


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("parent_id", "name", name="uq_category_parent_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=True
    )
    level: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    amazon_department: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    parent = relationship(
        "Category", remote_side=[id], back_populates="children"
    )
    children = relationship(
        "Category",
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="Category.sort_order, Category.name",
    )
    products = relationship("Product", back_populates="category")

    def get_ancestors(self) -> list["Category"]:
        """Return list from root down to (but not including) self."""
        ancestors = []
        node = self.parent
        while node is not None:
            ancestors.append(node)
            node = node.parent
        ancestors.reverse()
        return ancestors

    def get_path(self) -> str:
        """Return breadcrumb path like 'Toys & Games > Puzzles > 3D Puzzles'."""
        parts = [a.name for a in self.get_ancestors()]
        parts.append(self.name)
        return " > ".join(parts)

    def get_descendants(self) -> list["Category"]:
        """Return all children recursively, depth-first."""
        result = []
        for child in self.children:
            result.append(child)
            result.extend(child.get_descendants())
        return result

    def get_all_ids(self) -> list[int]:
        """Return self.id + all descendant IDs (for product filtering)."""
        ids = [self.id]
        for child in self.children:
            ids.extend(child.get_all_ids())
        return ids

    def resolve_department(self) -> str:
        """Walk up tree to find nearest amazon_department, fall back to config default."""
        if self.amazon_department:
            return self.amazon_department
        node = self.parent
        while node is not None:
            if node.amazon_department:
                return node.amazon_department
            node = node.parent
        from config import AMAZON_DEPARTMENT_DEFAULT
        return AMAZON_DEPARTMENT_DEFAULT

    def __repr__(self) -> str:
        return f"<Category id={self.id} name={self.name!r} level={self.level}>"
