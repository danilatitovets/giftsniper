"""smart alert events

Revision ID: 0009_smart_alert_events
Revises: 0008_smart_alert_states
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_smart_alert_events"
down_revision = "0008_smart_alert_states"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "smart_alert_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alert_type", sa.String(length=32), nullable=False),
        sa.Column("collection", sa.String(length=255), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.String(length=4000), nullable=False),
        sa.Column("payload_hash", sa.String(length=128), nullable=False),
        sa.Column("is_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_batched", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_smart_alert_events_user_id", "smart_alert_events", ["user_id"], unique=False)
    op.create_index("ix_smart_alert_events_alert_type", "smart_alert_events", ["alert_type"], unique=False)
    op.create_index("ix_smart_alert_events_severity", "smart_alert_events", ["severity"], unique=False)
    op.create_index("ix_smart_alert_events_created_at", "smart_alert_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_smart_alert_events_created_at", table_name="smart_alert_events")
    op.drop_index("ix_smart_alert_events_severity", table_name="smart_alert_events")
    op.drop_index("ix_smart_alert_events_alert_type", table_name="smart_alert_events")
    op.drop_index("ix_smart_alert_events_user_id", table_name="smart_alert_events")
    op.drop_table("smart_alert_events")
