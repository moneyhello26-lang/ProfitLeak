"""Track human review independently of recomputed financial evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("insights") as batch:
        batch.add_column(sa.Column("workflow_status", sa.String(20),
                                   nullable=False, server_default="new"))
        batch.add_column(sa.Column("workflow_note", sa.Text(), nullable=False, server_default=""))
        batch.add_column(
            sa.Column("workflow_updated_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_check_constraint(
            "workflow_status", "workflow_status IN ('new', 'in_progress', 'reviewed', 'dismissed')"
        )


def downgrade() -> None:
    with op.batch_alter_table("insights") as batch:
        batch.drop_constraint("workflow_status", type_="check")
        batch.drop_column("workflow_updated_at")
        batch.drop_column("workflow_note")
        batch.drop_column("workflow_status")
