"""feedback items

Revision ID: 0021_feedback_items
Revises: 0020_beta_invites
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_feedback_items"
down_revision = "0020_beta_invites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("message", sa.String(length=4000), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="new"),
        sa.Column("admin_note", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_feedback_items_user_id", "feedback_items", ["user_id"], unique=False)
    op.create_index("ix_feedback_items_type", "feedback_items", ["type"], unique=False)
    op.create_index("ix_feedback_items_status", "feedback_items", ["status"], unique=False)
    op.create_index("ix_feedback_items_created_at", "feedback_items", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_feedback_items_created_at", table_name="feedback_items")
    op.drop_index("ix_feedback_items_status", table_name="feedback_items")
    op.drop_index("ix_feedback_items_type", table_name="feedback_items")
    op.drop_index("ix_feedback_items_user_id", table_name="feedback_items")
    op.drop_table("feedback_items")
