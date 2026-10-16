"""Add user accounts, revocable sessions and business memberships.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def record_columns():
    return (
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        *record_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "business_memberships",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        *record_columns(),
        sa.CheckConstraint(
            "role IN ('owner', 'analyst', 'viewer')", name=op.f("ck_business_memberships_role")
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            ondelete="CASCADE",
            name=op.f("fk_business_memberships_business_id_businesses"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_business_memberships_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_memberships")),
        sa.UniqueConstraint("business_id", "user_id", name="uq_business_memberships_business_user"),
    )
    op.create_index("ix_business_memberships_user_id", "business_memberships", ["user_id"])
    op.create_table(
        "user_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        *record_columns(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_user_sessions_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_sessions_token_hash")),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    bootstrap = op.create_table(
        "account_bootstrap",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("claimed_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint("id = 1", name=op.f("ck_account_bootstrap_singleton")),
        sa.ForeignKeyConstraint(
            ["claimed_by"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_account_bootstrap_claimed_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_bootstrap")),
    )
    op.bulk_insert(bootstrap, [{"id": 1, "claimed_by": None}])


def downgrade() -> None:
    op.drop_table("account_bootstrap")
    op.drop_index("ix_user_sessions_user_id", "user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_business_memberships_user_id", "business_memberships")
    op.drop_table("business_memberships")
    op.drop_table("users")
