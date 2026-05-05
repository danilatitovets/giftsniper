"""analysis_results precision pricing / brain fields

Revision ID: 0025_precision_pricing_fields
Revises: 0024_gift_identity_fields
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0025_precision_pricing_fields"
down_revision = "0024_gift_identity_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analysis_results", sa.Column("safe_buy_price_ton", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("aggressive_buy_price_ton", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("quick_flip_list_price_ton", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("normal_list_price_ton", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("high_list_price_ton", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("downside_price_ton", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("upside_price_ton", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("time_to_sell_estimate", sa.String(length=64), nullable=True))
    op.add_column("analysis_results", sa.Column("decision_type", sa.String(length=32), nullable=True))
    op.add_column("analysis_results", sa.Column("decision_summary", sa.String(length=512), nullable=True))
    op.add_column("analysis_results", sa.Column("rarity_score", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("liquidity_adjusted_rarity_score", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("trait_opportunity_score", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("market_intelligence_json", sa.Text(), nullable=True))
    op.add_column("analysis_results", sa.Column("precision_plan_json", sa.Text(), nullable=True))
    op.add_column("analysis_results", sa.Column("decision_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_results", "decision_json")
    op.drop_column("analysis_results", "precision_plan_json")
    op.drop_column("analysis_results", "market_intelligence_json")
    op.drop_column("analysis_results", "trait_opportunity_score")
    op.drop_column("analysis_results", "liquidity_adjusted_rarity_score")
    op.drop_column("analysis_results", "rarity_score")
    op.drop_column("analysis_results", "decision_summary")
    op.drop_column("analysis_results", "decision_type")
    op.drop_column("analysis_results", "time_to_sell_estimate")
    op.drop_column("analysis_results", "upside_price_ton")
    op.drop_column("analysis_results", "downside_price_ton")
    op.drop_column("analysis_results", "high_list_price_ton")
    op.drop_column("analysis_results", "normal_list_price_ton")
    op.drop_column("analysis_results", "quick_flip_list_price_ton")
    op.drop_column("analysis_results", "aggressive_buy_price_ton")
    op.drop_column("analysis_results", "safe_buy_price_ton")
