"""Cash is recorded independently of accrual sales and expenses."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RecordMixin
from app.db.types import ExactDecimal


class CashAccount(RecordMixin, Base):
    __tablename__ = "cash_accounts"
    __table_args__ = (UniqueConstraint("business_id", "id"),)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id"))
    name: Mapped[str] = mapped_column(String(120))
    opening_date: Mapped[date]
    opening_balance: Mapped[Decimal] = mapped_column(ExactDecimal())


class CashEntry(RecordMixin, Base):
    __tablename__ = "cash_entries"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "account_id"],
                             ["cash_accounts.business_id", "cash_accounts.id"],
                             name="fk_cash_entries_source"),
        ForeignKeyConstraint(["business_id", "destination_id"],
                             ["cash_accounts.business_id", "cash_accounts.id"],
                             name="fk_cash_entries_destination"),
        UniqueConstraint("business_id", "account_id", "reference"),
        CheckConstraint("amount > 0", name="positive_amount"),
        CheckConstraint("kind IN ('income', 'expense', 'transfer')", name="kind"),
        CheckConstraint("(kind = 'transfer' AND destination_id IS NOT NULL "
                        "AND destination_id != account_id) OR "
                        "(kind != 'transfer' AND destination_id IS NULL)", name="destination"),
    )
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id"))
    account_id: Mapped[UUID]
    destination_id: Mapped[UUID | None]
    date: Mapped[date]
    kind: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal] = mapped_column(ExactDecimal())
    category: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), default="")
    reference: Mapped[str | None] = mapped_column(String(160))


class PlannedPayment(RecordMixin, Base):
    __tablename__ = "planned_payments"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "account_id"],
                             ["cash_accounts.business_id", "cash_accounts.id"]),
        CheckConstraint("amount > 0", name="positive_amount"),
        CheckConstraint("kind IN ('income', 'expense')", name="kind"),
        CheckConstraint("status IN ('pending', 'paid', 'cancelled')", name="status"),
        CheckConstraint("recurrence IN ('none', 'weekly', 'monthly')", name="recurrence"),
        CheckConstraint("recurrence_day IS NULL OR recurrence_day BETWEEN 1 AND 31",
                        name="recurrence_day"),
    )
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id"))
    account_id: Mapped[UUID]
    due_date: Mapped[date]
    kind: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal] = mapped_column(ExactDecimal())
    category: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), default="")
    recurrence: Mapped[str] = mapped_column(String(10), default="none")
    recurrence_day: Mapped[int | None]
    status: Mapped[str] = mapped_column(String(10), default="pending")


class CashBudget(RecordMixin, Base):
    __tablename__ = "cash_budgets"
    __table_args__ = (
        UniqueConstraint("business_id", "month", "category"),
        CheckConstraint("amount >= 0", name="nonnegative_amount"),
    )
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id"))
    month: Mapped[date]
    category: Mapped[str] = mapped_column(String(100))
    amount: Mapped[Decimal] = mapped_column(ExactDecimal())
