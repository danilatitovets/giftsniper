"""trade journal accuracy tags and realized metrics

Revision ID: 0027_trade_journal_accuracy_tags
Revises: 0026_trade_journal
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0027_trade_journal_accuracy_tags"
down_revision = "0026_trade_journal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trade_journal", sa.Column("accuracy_tags_json", sa.JSON(), nullable=True))
    op.add_column("trade_journal", sa.Column("realized_profit_ton", sa.Float(), nullable=True))
    op.add_column("trade_journal", sa.Column("realized_roi_percent", sa.Float(), nullable=True))
    op.add_column("trade_journal", sa.Column("hold_time_hours", sa.Float(), nullable=True))
    op.add_column("trade_journal", sa.Column("prediction_error_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("trade_journal", "prediction_error_json")
    op.drop_column("trade_journal", "hold_time_hours")
    op.drop_column("trade_journal", "realized_roi_percent")
    op.drop_column("trade_journal", "realized_profit_ton")
    op.drop_column("trade_journal", "accuracy_tags_json")
