"""link feedback items to signal snapshots

Revision ID: 0029_feedback_signal_link
Revises: 0028_signal_snapshots
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0029_feedback_signal_link"
down_revision = "0028_signal_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("feedback_items") as batch:
        batch.alter_column("type", existing_type=sa.String(length=16), type_=sa.String(length=32), existing_nullable=False)
    op.add_column("feedback_items", sa.Column("signal_snapshot_id", sa.Integer(), nullable=True))
    op.add_column("feedback_items", sa.Column("signal_rating", sa.String(length=32), nullable=True))
    op.add_column("feedback_items", sa.Column("outcome_hint", sa.String(length=64), nullable=True))
    op.add_column("feedback_items", sa.Column("reviewer_note", sa.String(length=2000), nullable=True))
    op.create_foreign_key(
        "fk_feedback_items_signal_snapshot_id",
        "feedback_items",
        "signal_snapshots",
        ["signal_snapshot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_feedback_items_signal_snapshot_id", "feedback_items", ["signal_snapshot_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_feedback_items_signal_snapshot_id", table_name="feedback_items")
    op.drop_constraint("fk_feedback_items_signal_snapshot_id", "feedback_items", type_="foreignkey")
    op.drop_column("feedback_items", "reviewer_note")
    op.drop_column("feedback_items", "outcome_hint")
    op.drop_column("feedback_items", "signal_rating")
    op.drop_column("feedback_items", "signal_snapshot_id")
    with op.batch_alter_table("feedback_items") as batch:
        batch.alter_column("type", existing_type=sa.String(length=32), type_=sa.String(length=16), existing_nullable=False)
