"""analysis profit fields

Revision ID: 0003_analysis_profit_fields
Revises: 0002_alert_rule_state
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_analysis_profit_fields"
down_revision = "0002_alert_rule_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analysis_results", sa.Column("buy_zone_min_ton", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("buy_zone_max_ton", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("list_price_ton", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("stop_price_ton", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("marketplace_fee_percent", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("expected_net_sale_ton", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("expected_profit_ton", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("expected_roi_percent", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("liquidity_score", sa.Integer(), nullable=True))
    op.add_column("analysis_results", sa.Column("risk_score", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_results", "risk_score")
    op.drop_column("analysis_results", "liquidity_score")
    op.drop_column("analysis_results", "expected_roi_percent")
    op.drop_column("analysis_results", "expected_profit_ton")
    op.drop_column("analysis_results", "expected_net_sale_ton")
    op.drop_column("analysis_results", "marketplace_fee_percent")
    op.drop_column("analysis_results", "stop_price_ton")
    op.drop_column("analysis_results", "list_price_ton")
    op.drop_column("analysis_results", "buy_zone_max_ton")
    op.drop_column("analysis_results", "buy_zone_min_ton")
