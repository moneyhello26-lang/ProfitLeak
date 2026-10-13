"""PostgreSQL records. Financial values always use Decimal backed by NUMERIC."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RecordMixin


class Business(RecordMixin, Base):
    __tablename__ = "businesses"
    __table_args__ = (CheckConstraint("currency = 'KZT'", name="currency_kzt"),)

    name: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3), default="KZT", server_default="KZT")
    timezone: Mapped[str] = mapped_column(
        String(50), default="Asia/Almaty", server_default="Asia/Almaty"
    )


class Product(RecordMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("business_id", "external_id", name="uq_products_business_external"),
        UniqueConstraint("business_id", "id", name="uq_products_business_id"),
    )

    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="RESTRICT"))
    external_id: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100))


class ImportBatch(RecordMixin, Base):
    __tablename__ = "imports"
    __table_args__ = (
        UniqueConstraint("business_id", "kind", "file_sha256", name="uq_imports_business_file"),
        UniqueConstraint("business_id", "id", name="uq_imports_business_id"),
        CheckConstraint("kind IN ('sales', 'expenses', 'products')", name="kind"),
        CheckConstraint("status IN ('processing', 'confirmed', 'failed')", name="status"),
        CheckConstraint("row_count >= 0", name="row_count"),
        CheckConstraint("file_sha256 ~ '^[0-9a-f]{64}$'", name="file_sha256"),
    )

    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="RESTRICT"))
    filename: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(20))
    file_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="processing")
    row_count: Mapped[int] = mapped_column(default=0, server_default="0")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Sale(RecordMixin, Base):
    __tablename__ = "sales"
    __table_args__ = (
        ForeignKeyConstraint(
            ["business_id", "product_id"],
            ["products.business_id", "products.id"],
            name="fk_sales_business_product",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["business_id", "import_id"],
            ["imports.business_id", "imports.id"],
            name="fk_sales_business_import",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("import_id", "source_row", name="uq_sales_import_row"),
        CheckConstraint("source_row > 0", name="source_row"),
        CheckConstraint("record_type IN ('sale', 'return')", name="record_type"),
        CheckConstraint("quantity > 0 AND quantity <> 'NaN'::numeric", name="quantity"),
        CheckConstraint("unit_price >= 0 AND unit_price <> 'NaN'::numeric", name="unit_price"),
        CheckConstraint(
            "unit_cost IS NULL OR (unit_cost >= 0 AND unit_cost <> 'NaN'::numeric)",
            name="unit_cost",
        ),
        Index("ix_sales_business_date", "business_id", "date"),
        Index("ix_sales_business_product_date", "business_id", "product_id", "date"),
    )

    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="RESTRICT"))
    product_id: Mapped[UUID]
    import_id: Mapped[UUID]
    source_row: Mapped[int]
    date: Mapped[date]
    record_type: Mapped[str] = mapped_column(String(10), default="sale", server_default="sale")
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))


class Expense(RecordMixin, Base):
    __tablename__ = "expenses"
    __table_args__ = (
        ForeignKeyConstraint(
            ["business_id", "import_id"],
            ["imports.business_id", "imports.id"],
            name="fk_expenses_business_import",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("import_id", "source_row", name="uq_expenses_import_row"),
        CheckConstraint("source_row > 0", name="source_row"),
        CheckConstraint("record_type IN ('expense', 'refund')", name="record_type"),
        CheckConstraint("amount >= 0 AND amount <> 'NaN'::numeric", name="amount"),
        Index("ix_expenses_business_date", "business_id", "date"),
        Index("ix_expenses_business_category_date", "business_id", "category", "date"),
    )

    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="RESTRICT"))
    import_id: Mapped[UUID]
    source_row: Mapped[int]
    date: Mapped[date]
    record_type: Mapped[str] = mapped_column(
        String(10), default="expense", server_default="expense"
    )
    category: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))


class Insight(RecordMixin, Base):
    __tablename__ = "insights"
    __table_args__ = (
        CheckConstraint(
            "type IN ('EXPENSE_SPIKE', 'MARGIN_DROP', 'LOW_PROFIT_PRODUCT', "
            "'SALES_DROP', 'POSSIBLE_DUPLICATE')",
            name="type",
        ),
        CheckConstraint("severity IN ('low', 'medium', 'high')", name="severity"),
        CheckConstraint("confidence IN ('low', 'medium', 'high')", name="confidence"),
        CheckConstraint("period_start <= period_end", name="period"),
        CheckConstraint(
            "(estimated_savings IS NULL AND estimate_type IS NULL) OR "
            "(estimated_savings IS NOT NULL AND estimated_savings >= 0 "
            "AND estimated_savings <> 'NaN'::numeric "
            "AND estimate_type IS NOT NULL AND estimate_type = 'scenario')",
            name="savings",
        ),
        Index("ix_insights_business_created", "business_id", "created_at"),
    )

    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="RESTRICT"))
    type: Mapped[str] = mapped_column(String(30))
    severity: Mapped[str] = mapped_column(String(10))
    confidence: Mapped[str] = mapped_column(String(10))
    period_start: Mapped[date]
    period_end: Mapped[date]
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    estimated_savings: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    estimate_type: Mapped[str | None] = mapped_column(String(20))
    recommendation: Mapped[str] = mapped_column(Text)
