"""smart alert states

Revision ID: 0008_smart_alert_states
Revises: 0007_smart_alert_types
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_smart_alert_states"
down_revision = "0007_smart_alert_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "smart_alert_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alert_type", sa.String(length=32), nullable=False),
        sa.Column("collection", sa.String(length=255), nullable=True),
        sa.Column("last_regime", sa.String(length=32), nullable=True),
        sa.Column("last_strength_score", sa.Float(), nullable=True),
        sa.Column("last_liquidity_score", sa.Float(), nullable=True),
        sa.Column("last_payload_hash", sa.String(length=128), nullable=True),
        sa.Column("last_sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "alert_type", "collection", name="uq_smart_alert_state_scope"),
    )
    op.create_index("ix_smart_alert_states_user_id", "smart_alert_states", ["user_id"], unique=False)
    op.create_index("ix_smart_alert_states_alert_type", "smart_alert_states", ["alert_type"], unique=False)
    op.create_index("ix_smart_alert_states_collection", "smart_alert_states", ["collection"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_smart_alert_states_collection", table_name="smart_alert_states")
    op.drop_index("ix_smart_alert_states_alert_type", table_name="smart_alert_states")
    op.drop_index("ix_smart_alert_states_user_id", table_name="smart_alert_states")
    op.drop_table("smart_alert_states")
