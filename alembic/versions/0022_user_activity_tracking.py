"""user activity tracking and product events

Revision ID: 0022_user_activity_tracking
Revises: 0021_feedback_items
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0022_user_activity_tracking"
down_revision = "0021_feedback_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("first_seen_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("last_seen_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("command_count", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "product_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("command", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.String(length=4000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_product_events_user_id", "product_events", ["user_id"], unique=False)
    op.create_index("ix_product_events_event_type", "product_events", ["event_type"], unique=False)
    op.create_index("ix_product_events_command", "product_events", ["command"], unique=False)
    op.create_index("ix_product_events_created_at", "product_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_product_events_created_at", table_name="product_events")
    op.drop_index("ix_product_events_command", table_name="product_events")
    op.drop_index("ix_product_events_event_type", table_name="product_events")
    op.drop_index("ix_product_events_user_id", table_name="product_events")
    op.drop_table("product_events")

    op.drop_column("users", "command_count")
    op.drop_column("users", "last_seen_at")
    op.drop_column("users", "first_seen_at")
