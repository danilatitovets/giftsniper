"""smart alert incidents

Revision ID: 0011_smart_alert_incidents
Revises: 0010_user_notification_settings
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_smart_alert_incidents"
down_revision = "0010_user_notification_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "smart_alert_incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alert_type", sa.String(length=32), nullable=False),
        sa.Column("collection", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("recovered_at", sa.DateTime(), nullable=True),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_payload_hash", sa.String(length=128), nullable=True),
        sa.Column("escalation_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.String(length=4000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_smart_alert_incidents_user_id", "smart_alert_incidents", ["user_id"], unique=False)
    op.create_index("ix_smart_alert_incidents_alert_type", "smart_alert_incidents", ["alert_type"], unique=False)
    op.create_index("ix_smart_alert_incidents_collection", "smart_alert_incidents", ["collection"], unique=False)
    op.create_index("ix_smart_alert_incidents_status", "smart_alert_incidents", ["status"], unique=False)
    op.create_index("ix_smart_alert_incidents_severity", "smart_alert_incidents", ["severity"], unique=False)
    op.create_index("ix_smart_alert_incidents_last_seen_at", "smart_alert_incidents", ["last_seen_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_smart_alert_incidents_last_seen_at", table_name="smart_alert_incidents")
    op.drop_index("ix_smart_alert_incidents_severity", table_name="smart_alert_incidents")
    op.drop_index("ix_smart_alert_incidents_status", table_name="smart_alert_incidents")
    op.drop_index("ix_smart_alert_incidents_collection", table_name="smart_alert_incidents")
    op.drop_index("ix_smart_alert_incidents_alert_type", table_name="smart_alert_incidents")
    op.drop_index("ix_smart_alert_incidents_user_id", table_name="smart_alert_incidents")
    op.drop_table("smart_alert_incidents")
