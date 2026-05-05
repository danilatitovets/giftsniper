"""incident operator controls

Revision ID: 0013_incident_operator_controls
Revises: 0012_alert_event_incident
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_incident_operator_controls"
down_revision = "0012_alert_event_incident"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("smart_alert_incidents", sa.Column("acknowledged_at", sa.DateTime(), nullable=True))
    op.add_column("smart_alert_incidents", sa.Column("acknowledged_by_user_id", sa.Integer(), nullable=True))
    op.add_column("smart_alert_incidents", sa.Column("muted_until", sa.DateTime(), nullable=True))
    op.add_column("smart_alert_incidents", sa.Column("mute_reason", sa.String(length=4000), nullable=True))
    op.add_column("smart_alert_incidents", sa.Column("resolved_manually_at", sa.DateTime(), nullable=True))
    op.add_column("smart_alert_incidents", sa.Column("resolved_note", sa.String(length=4000), nullable=True))
    op.add_column("smart_alert_incidents", sa.Column("is_false_positive", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("smart_alert_incidents", sa.Column("false_positive_note", sa.String(length=4000), nullable=True))
    op.create_foreign_key(
        "fk_smart_alert_incidents_ack_user",
        "smart_alert_incidents",
        "users",
        ["acknowledged_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_smart_alert_incidents_acknowledged_at", "smart_alert_incidents", ["acknowledged_at"], unique=False)
    op.create_index("ix_smart_alert_incidents_muted_until", "smart_alert_incidents", ["muted_until"], unique=False)
    op.create_index("ix_smart_alert_incidents_is_false_positive", "smart_alert_incidents", ["is_false_positive"], unique=False)

    op.create_table(
        "smart_alert_incident_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), sa.ForeignKey("smart_alert_incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("note", sa.String(length=4000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_smart_alert_incident_actions_incident_id", "smart_alert_incident_actions", ["incident_id"], unique=False)
    op.create_index("ix_smart_alert_incident_actions_user_id", "smart_alert_incident_actions", ["user_id"], unique=False)
    op.create_index("ix_smart_alert_incident_actions_action_type", "smart_alert_incident_actions", ["action_type"], unique=False)
    op.create_index("ix_smart_alert_incident_actions_created_at", "smart_alert_incident_actions", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_smart_alert_incident_actions_created_at", table_name="smart_alert_incident_actions")
    op.drop_index("ix_smart_alert_incident_actions_action_type", table_name="smart_alert_incident_actions")
    op.drop_index("ix_smart_alert_incident_actions_user_id", table_name="smart_alert_incident_actions")
    op.drop_index("ix_smart_alert_incident_actions_incident_id", table_name="smart_alert_incident_actions")
    op.drop_table("smart_alert_incident_actions")

    op.drop_index("ix_smart_alert_incidents_is_false_positive", table_name="smart_alert_incidents")
    op.drop_index("ix_smart_alert_incidents_muted_until", table_name="smart_alert_incidents")
    op.drop_index("ix_smart_alert_incidents_acknowledged_at", table_name="smart_alert_incidents")
    op.drop_constraint("fk_smart_alert_incidents_ack_user", "smart_alert_incidents", type_="foreignkey")
    op.drop_column("smart_alert_incidents", "false_positive_note")
    op.drop_column("smart_alert_incidents", "is_false_positive")
    op.drop_column("smart_alert_incidents", "resolved_note")
    op.drop_column("smart_alert_incidents", "resolved_manually_at")
    op.drop_column("smart_alert_incidents", "mute_reason")
    op.drop_column("smart_alert_incidents", "muted_until")
    op.drop_column("smart_alert_incidents", "acknowledged_by_user_id")
    op.drop_column("smart_alert_incidents", "acknowledged_at")
