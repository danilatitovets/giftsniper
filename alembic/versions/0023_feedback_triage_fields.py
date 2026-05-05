"""feedback triage fields

Revision ID: 0023_feedback_triage_fields
Revises: 0022_user_activity_tracking
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_feedback_triage_fields"
down_revision = "0022_user_activity_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("feedback_items", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.add_column("feedback_items", sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True))
    op.add_column("feedback_items", sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal"))
    op.create_foreign_key(
        "fk_feedback_items_reviewed_by_user_id_users",
        "feedback_items",
        "users",
        ["reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_feedback_items_priority", "feedback_items", ["priority"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_feedback_items_priority", table_name="feedback_items")
    op.drop_constraint("fk_feedback_items_reviewed_by_user_id_users", "feedback_items", type_="foreignkey")
    op.drop_column("feedback_items", "priority")
    op.drop_column("feedback_items", "reviewed_by_user_id")
    op.drop_column("feedback_items", "reviewed_at")
