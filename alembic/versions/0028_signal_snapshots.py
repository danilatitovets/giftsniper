"""signal snapshots for production accuracy loop

Revision ID: 0028_signal_snapshots
Revises: 0027_trade_journal_accuracy_tags
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0028_signal_snapshots"
down_revision = "0027_trade_journal_accuracy_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signal_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_command", sa.String(length=32), nullable=False),
        sa.Column("collection", sa.String(length=255), nullable=False),
        sa.Column("number", sa.Integer(), nullable=True),
        sa.Column("nft_address", sa.String(length=256), nullable=True),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("input_text", sa.String(length=2000), nullable=True),
        sa.Column("decision_type", sa.String(length=32), nullable=True),
        sa.Column("recommendation", sa.String(length=64), nullable=True),
        sa.Column("tier", sa.String(length=64), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("safe_buy_price_ton", sa.Float(), nullable=True),
        sa.Column("max_buy_price_ton", sa.Float(), nullable=True),
        sa.Column("list_price_ton", sa.Float(), nullable=True),
        sa.Column("quick_sell_price_ton", sa.Float(), nullable=True),
        sa.Column("stop_loss_price_ton", sa.Float(), nullable=True),
        sa.Column("expected_profit_ton", sa.Float(), nullable=True),
        sa.Column("expected_roi_percent", sa.Float(), nullable=True),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=True),
        sa.Column("liquidity_score", sa.Integer(), nullable=True),
        sa.Column("market_regime", sa.String(length=32), nullable=True),
        sa.Column("source_quality", sa.String(length=255), nullable=True),
        sa.Column("freshness_label", sa.String(length=32), nullable=True),
        sa.Column("has_recent_sales", sa.Boolean(), nullable=True),
        sa.Column("has_trait_sales", sa.Boolean(), nullable=True),
        sa.Column("important_trait_detected", sa.Boolean(), nullable=True),
        sa.Column("warning_flags_json", sa.JSON(), nullable=True),
        sa.Column("analysis_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_signal_snapshots_user_id", "signal_snapshots", ["user_id"], unique=False)
    op.create_index("ix_signal_snapshots_source_command", "signal_snapshots", ["source_command"], unique=False)
    op.create_index("ix_signal_snapshots_decision_type", "signal_snapshots", ["decision_type"], unique=False)
    op.create_index("ix_signal_snapshots_created_at", "signal_snapshots", ["created_at"], unique=False)
    op.create_index("ix_signal_snapshots_collection", "signal_snapshots", ["collection"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_signal_snapshots_collection", table_name="signal_snapshots")
    op.drop_index("ix_signal_snapshots_created_at", table_name="signal_snapshots")
    op.drop_index("ix_signal_snapshots_decision_type", table_name="signal_snapshots")
    op.drop_index("ix_signal_snapshots_source_command", table_name="signal_snapshots")
    op.drop_index("ix_signal_snapshots_user_id", table_name="signal_snapshots")
    op.drop_table("signal_snapshots")
