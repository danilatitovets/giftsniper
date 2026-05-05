"""trade journal link to signal snapshot

Revision ID: 0030_trade_signal_link
Revises: 0029_feedback_signal_link
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0030_trade_signal_link"
down_revision = "0029_feedback_signal_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trade_journal", sa.Column("signal_snapshot_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_trade_journal_signal_snapshot_id",
        "trade_journal",
        "signal_snapshots",
        ["signal_snapshot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_trade_journal_signal_snapshot_id", "trade_journal", ["signal_snapshot_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_trade_journal_signal_snapshot_id", table_name="trade_journal")
    op.drop_constraint("fk_trade_journal_signal_snapshot_id", "trade_journal", type_="foreignkey")
    op.drop_column("trade_journal", "signal_snapshot_id")
