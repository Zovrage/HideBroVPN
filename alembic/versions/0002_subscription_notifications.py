"""subscription notifications fields

Revision ID: 0002_subscription_notifications
Revises: 0001_initial
Create Date: 2026-04-03 12:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_subscription_notifications"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_subscriptions",
        sa.Column("notified_3d_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_subscriptions",
        sa.Column("notified_1d_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_subscriptions",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_subscriptions", "deleted_at")
    op.drop_column("user_subscriptions", "notified_1d_at")
    op.drop_column("user_subscriptions", "notified_3d_at")
