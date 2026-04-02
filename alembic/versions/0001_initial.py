"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-03-30 23:20:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    payment_action = postgresql.ENUM("CREATE", "EXTEND", name="payment_action")
    payment_status = postgresql.ENUM("PENDING", "SUCCEEDED", "CANCELED", name="payment_status")
    payment_action.create(op.get_bind(), checkfirst=True)
    payment_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("referred_by_id", sa.Integer(), nullable=True),
        sa.Column("free_trial_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("has_any_paid_purchase", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["referred_by_id"], ["user_profiles.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_user_profiles_telegram_id", "user_profiles", ["telegram_id"], unique=True)
    op.create_index("ix_user_profiles_username", "user_profiles", ["username"], unique=False)

    op.create_table(
        "user_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("remna_uuid", sa.String(length=64), nullable=False),
        sa.Column("remna_short_uuid", sa.String(length=64), nullable=True),
        sa.Column("remna_username", sa.String(length=64), nullable=False),
        sa.Column("subscription_url", sa.Text(), nullable=False),
        sa.Column("expire_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_trial", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["user_profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_subscriptions_user_id", "user_subscriptions", ["user_id"], unique=False)
    op.create_index("ix_user_subscriptions_expire_at", "user_subscriptions", ["expire_at"], unique=False)
    op.create_index("ix_user_subscriptions_remna_uuid", "user_subscriptions", ["remna_uuid"], unique=True)
    op.create_index("ix_user_subscriptions_remna_short_uuid", "user_subscriptions", ["remna_short_uuid"], unique=True)
    op.create_index("ix_user_subscriptions_remna_username", "user_subscriptions", ["remna_username"], unique=True)

    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("referrer_id", sa.Integer(), nullable=False),
        sa.Column("invited_id", sa.Integer(), nullable=False),
        sa.Column("bonus_days", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("reward_locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rewarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reward_subscription_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["referrer_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reward_subscription_id"], ["user_subscriptions.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("invited_id", name="uq_referrals_invited_once"),
    )
    op.create_index("ix_referrals_referrer_id", "referrals", ["referrer_id"], unique=False)
    op.create_index("ix_referrals_invited_id", "referrals", ["invited_id"], unique=False)

    op.create_table(
        "payment_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("plan_code", sa.String(length=16), nullable=False),
        sa.Column(
            "action_type",
            postgresql.ENUM("CREATE", "EXTEND", name="payment_action", create_type=False),
            nullable=False,
        ),
        sa.Column("amount_rub", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("PENDING", "SUCCEEDED", "CANCELED", name="payment_status", create_type=False),
            nullable=False,
        ),
        sa.Column("gateway", sa.String(length=32), nullable=False),
        sa.Column("gateway_payment_id", sa.String(length=128), nullable=True),
        sa.Column("payment_url", sa.Text(), nullable=True),
        sa.Column("is_processed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["user_subscriptions.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_payment_orders_user_id", "payment_orders", ["user_id"], unique=False)
    op.create_index("ix_payment_orders_subscription_id", "payment_orders", ["subscription_id"], unique=False)
    op.create_index("ix_payment_orders_gateway_payment_id", "payment_orders", ["gateway_payment_id"], unique=True)

    op.create_table(
        "admin_grants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("admin_user_id", sa.Integer(), nullable=True),
        sa.Column("target_user_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["admin_user_id"], ["user_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_user_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["user_subscriptions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_admin_grants_target_user_id", "admin_grants", ["target_user_id"], unique=False)
    op.create_index("ix_admin_grants_subscription_id", "admin_grants", ["subscription_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_admin_grants_subscription_id", table_name="admin_grants")
    op.drop_index("ix_admin_grants_target_user_id", table_name="admin_grants")
    op.drop_table("admin_grants")

    op.drop_index("ix_payment_orders_gateway_payment_id", table_name="payment_orders")
    op.drop_index("ix_payment_orders_subscription_id", table_name="payment_orders")
    op.drop_index("ix_payment_orders_user_id", table_name="payment_orders")
    op.drop_table("payment_orders")

    op.drop_index("ix_referrals_invited_id", table_name="referrals")
    op.drop_index("ix_referrals_referrer_id", table_name="referrals")
    op.drop_table("referrals")

    op.drop_index("ix_user_subscriptions_remna_username", table_name="user_subscriptions")
    op.drop_index("ix_user_subscriptions_remna_short_uuid", table_name="user_subscriptions")
    op.drop_index("ix_user_subscriptions_remna_uuid", table_name="user_subscriptions")
    op.drop_index("ix_user_subscriptions_expire_at", table_name="user_subscriptions")
    op.drop_index("ix_user_subscriptions_user_id", table_name="user_subscriptions")
    op.drop_table("user_subscriptions")

    op.drop_index("ix_user_profiles_username", table_name="user_profiles")
    op.drop_index("ix_user_profiles_telegram_id", table_name="user_profiles")
    op.drop_table("user_profiles")

    sa.Enum(name="payment_action").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="payment_status").drop(op.get_bind(), checkfirst=True)
