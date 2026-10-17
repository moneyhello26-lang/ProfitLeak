"""Independent cash ledger, payment calendar and monthly budgets."""

import sqlalchemy as sa
from alembic import op

from app.db.types import ExactDecimal, UTCDateTime

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def common_columns():
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", UTCDateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("business_id", sa.Uuid(), sa.ForeignKey("businesses.id"), nullable=False),
    ]


def upgrade():
    op.create_table(
        "cash_accounts", *common_columns(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("opening_date", sa.Date(), nullable=False),
        sa.Column("opening_balance", ExactDecimal(), nullable=False),
        sa.UniqueConstraint("business_id", "id"),
    )
    op.create_table(
        "cash_entries", *common_columns(),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("destination_id", sa.Uuid()),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("amount", ExactDecimal(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("reference", sa.String(160)),
        sa.ForeignKeyConstraint(["business_id", "account_id"],
                                ["cash_accounts.business_id", "cash_accounts.id"],
                                name="fk_cash_entries_source"),
        sa.ForeignKeyConstraint(["business_id", "destination_id"],
                                ["cash_accounts.business_id", "cash_accounts.id"],
                                name="fk_cash_entries_destination"),
        sa.UniqueConstraint("business_id", "account_id", "reference"),
        sa.CheckConstraint("amount > 0", name="positive_amount"),
        sa.CheckConstraint("kind IN ('income', 'expense', 'transfer')", name="kind"),
        sa.CheckConstraint("(kind = 'transfer' AND destination_id IS NOT NULL "
                           "AND destination_id != account_id) OR "
                           "(kind != 'transfer' AND destination_id IS NULL)", name="destination"),
    )
    op.create_table(
        "planned_payments", *common_columns(),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("amount", ExactDecimal(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("recurrence", sa.String(10), nullable=False),
        sa.Column("recurrence_day", sa.Integer()),
        sa.Column("status", sa.String(10), nullable=False),
        sa.ForeignKeyConstraint(["business_id", "account_id"],
                                ["cash_accounts.business_id", "cash_accounts.id"]),
        sa.CheckConstraint("amount > 0", name="positive_amount"),
        sa.CheckConstraint("kind IN ('income', 'expense')", name="kind"),
        sa.CheckConstraint("status IN ('pending', 'paid', 'cancelled')", name="status"),
        sa.CheckConstraint("recurrence IN ('none', 'weekly', 'monthly')", name="recurrence"),
        sa.CheckConstraint("recurrence_day IS NULL OR recurrence_day BETWEEN 1 AND 31",
                           name="recurrence_day"),
    )
    op.create_table(
        "cash_budgets", *common_columns(),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("amount", ExactDecimal(), nullable=False),
        sa.UniqueConstraint("business_id", "month", "category"),
        sa.CheckConstraint("amount >= 0", name="nonnegative_amount"),
    )


def downgrade():
    for name in ("cash_budgets", "planned_payments", "cash_entries", "cash_accounts"):
        op.drop_table(name)
