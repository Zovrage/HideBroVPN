from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    CANCELED = "canceled"


class PaymentAction(str, enum.Enum):
    CREATE = "create"
    EXTEND = "extend"


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    referred_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )
    free_trial_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    has_any_paid_purchase: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    subscriptions: Mapped[list[UserSubscription]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    outgoing_referrals: Mapped[list[Referral]] = relationship(
        back_populates="referrer", foreign_keys="Referral.referrer_id", cascade="all, delete-orphan"
    )
    incoming_referral: Mapped[Referral | None] = relationship(
        back_populates="invited", foreign_keys="Referral.invited_id", uselist=False
    )


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)

    remna_uuid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    remna_short_uuid: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    remna_username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    subscription_url: Mapped[str] = mapped_column(Text)

    expire_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    device_limit: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    is_trial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[UserProfile] = relationship(back_populates="subscriptions")
    payments: Mapped[list[PaymentOrder]] = relationship(back_populates="subscription")


class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = (UniqueConstraint("invited_id", name="uq_referrals_invited_once"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    invited_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)

    bonus_days: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    reward_locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rewarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reward_subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_subscriptions.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    referrer: Mapped[UserProfile] = relationship(back_populates="outgoing_referrals", foreign_keys=[referrer_id])
    invited: Mapped[UserProfile] = relationship(back_populates="incoming_referral", foreign_keys=[invited_id])


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_subscriptions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    plan_code: Mapped[str] = mapped_column(String(16), nullable=False)
    action_type: Mapped[PaymentAction] = mapped_column(Enum(PaymentAction, name="payment_action"), nullable=False)
    amount_rub: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"), default=PaymentStatus.PENDING, nullable=False
    )
    gateway: Mapped[str] = mapped_column(String(32), nullable=False)
    gateway_payment_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    payment_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[UserProfile] = relationship()
    subscription: Mapped[UserSubscription | None] = relationship(back_populates="payments")


class AdminGrant(Base):
    __tablename__ = "admin_grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )
    target_user_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("user_subscriptions.id", ondelete="CASCADE"), index=True)
    days: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

