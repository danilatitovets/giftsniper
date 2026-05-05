"""trade journal for prediction vs outcome QA

Revision ID: 0026_trade_journal
Revises: 0025_precision_pricing_fields
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0026_trade_journal"
down_revision = "0025_precision_pricing_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trade_journal",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("collection", sa.String(length=255), nullable=False),
        sa.Column("number", sa.Integer(), nullable=True),
        sa.Column("nft_address", sa.String(length=256), nullable=True),
        sa.Column("attributes_json", sa.JSON(), nullable=True),
        sa.Column("buy_price_ton", sa.Float(), nullable=True),
        sa.Column("buy_date", sa.DateTime(), nullable=True),
        sa.Column("sell_price_ton", sa.Float(), nullable=True),
        sa.Column("sell_date", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("prediction_json", sa.Text(), nullable=True),
        sa.Column("decision_type", sa.String(length=32), nullable=True),
        sa.Column("predicted_safe_buy_ton", sa.Float(), nullable=True),
        sa.Column("predicted_max_buy_ton", sa.Float(), nullable=True),
        sa.Column("predicted_list_price_ton", sa.Float(), nullable=True),
        sa.Column("predicted_roi_percent", sa.Float(), nullable=True),
        sa.Column("predicted_confidence", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("trade_journal")
