"""Persist demo metadata independently of per-account business identifiers.

Revision ID: 0005
Revises: 0004
"""

from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column("is_demo", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    businesses = sa.table(
        "businesses", sa.column("id", sa.Uuid()), sa.column("is_demo", sa.Boolean())
    )
    op.execute(
        businesses.update()
        .where(businesses.c.id == UUID("99d4acb9-bdac-531b-9e03-e29a32d92a85"))
        .values(is_demo=True)
    )


def downgrade() -> None:
    op.drop_column("businesses", "is_demo")
