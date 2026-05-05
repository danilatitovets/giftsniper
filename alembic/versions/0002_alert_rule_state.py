"""alert rule state

Revision ID: 0002_alert_rule_state
Revises: 0001_initial
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_alert_rule_state"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alert_rules", sa.Column("last_checked_at", sa.DateTime(), nullable=True))
    op.add_column("alert_rules", sa.Column("last_triggered_at", sa.DateTime(), nullable=True))
    op.add_column("alert_rules", sa.Column("last_value_ton", sa.Float(), nullable=True))
    op.add_column("alert_rules", sa.Column("last_is_triggered", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("alert_rules", sa.Column("trigger_count", sa.Integer(), nullable=False, server_default="0"))
    op.alter_column("alert_rules", "last_is_triggered", server_default=None)
    op.alter_column("alert_rules", "trigger_count", server_default=None)


def downgrade() -> None:
    op.drop_column("alert_rules", "trigger_count")
    op.drop_column("alert_rules", "last_is_triggered")
    op.drop_column("alert_rules", "last_value_ton")
    op.drop_column("alert_rules", "last_triggered_at")
    op.drop_column("alert_rules", "last_checked_at")
