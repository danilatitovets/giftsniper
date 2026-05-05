"""user notification settings

Revision ID: 0010_user_notification_settings
Revises: 0009_smart_alert_events
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_user_notification_settings"
down_revision = "0009_smart_alert_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_notification_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("delivery_mode", sa.String(length=16), nullable=False, server_default="smart"),
        sa.Column("quiet_hours_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("quiet_hours_start", sa.String(length=8), nullable=True),
        sa.Column("quiet_hours_end", sa.String(length=8), nullable=True),
        sa.Column("digest_interval_minutes", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("min_severity_to_notify", sa.String(length=16), nullable=False, server_default="warning"),
        sa.Column("critical_ignore_quiet_hours", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_user_notification_settings_user_id", "user_notification_settings", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_notification_settings_user_id", table_name="user_notification_settings")
    op.drop_table("user_notification_settings")
