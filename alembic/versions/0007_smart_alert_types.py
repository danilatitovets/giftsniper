"""smart alert types

Revision ID: 0007_smart_alert_types
Revises: 0006_user_universe_collections
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_smart_alert_types"
down_revision = "0006_user_universe_collections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("alert_rules", "collection", existing_type=sa.String(length=255), nullable=True)
    op.add_column("alert_rules", sa.Column("alert_type", sa.String(length=32), nullable=False, server_default="price"))
    op.add_column("alert_rules", sa.Column("threshold_value", sa.Float(), nullable=True))
    op.add_column("alert_rules", sa.Column("threshold_type", sa.String(length=32), nullable=True))
    op.add_column("alert_rules", sa.Column("cooldown_minutes", sa.Integer(), nullable=True))
    op.add_column("alert_rules", sa.Column("last_payload_hash", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("alert_rules", "last_payload_hash")
    op.drop_column("alert_rules", "cooldown_minutes")
    op.drop_column("alert_rules", "threshold_type")
    op.drop_column("alert_rules", "threshold_value")
    op.drop_column("alert_rules", "alert_type")
    op.alter_column("alert_rules", "collection", existing_type=sa.String(length=255), nullable=False)
