"""smart alert event incident link

Revision ID: 0012_alert_event_incident
Revises: 0011_smart_alert_incidents
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_alert_event_incident"
down_revision = "0011_smart_alert_incidents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("smart_alert_events", sa.Column("incident_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_smart_alert_events_incident_id",
        "smart_alert_events",
        "smart_alert_incidents",
        ["incident_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_smart_alert_events_incident_id", "smart_alert_events", ["incident_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_smart_alert_events_incident_id", table_name="smart_alert_events")
    op.drop_constraint("fk_smart_alert_events_incident_id", "smart_alert_events", type_="foreignkey")
    op.drop_column("smart_alert_events", "incident_id")
