"""user roles and plans

Revision ID: 0014_user_roles_plans
Revises: 0013_incident_operator_controls
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_user_roles_plans"
down_revision = "0013_incident_operator_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(length=16), nullable=False, server_default="user"))
    op.add_column("users", sa.Column("plan", sa.String(length=16), nullable=False, server_default="free"))
    op.add_column("users", sa.Column("plan_expires_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_index("ix_users_role", "users", ["role"], unique=False)
    op.create_index("ix_users_plan", "users", ["plan"], unique=False)
    op.create_index("ix_users_is_blocked", "users", ["is_blocked"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_is_blocked", table_name="users")
    op.drop_index("ix_users_plan", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_column("users", "is_blocked")
    op.drop_column("users", "plan_expires_at")
    op.drop_column("users", "plan")
    op.drop_column("users", "role")
