from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from aiogram.types import User
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models import (
    AdminGrant,
    PaymentAction,
    PaymentOrder,
    PaymentStatus,
    Referral,
    UserProfile,
    UserSubscription,
)
from app.domain.plans import TariffPlan, get_plan
from app.services.errors import (
    AccessDeniedError,
    NotFoundError,
    TrialAlreadyUsedError,
)
from app.services.payments import BasePaymentGateway, map_gateway_status
from app.services.remnawave import RemnawaveClient, RemnawaveDevice

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReferralRewardEvent:
    kind: Literal["auto_applied", "choice_required", "no_subscription"]
    referral_id: int
    referrer_telegram_id: int
    invited_telegram_id: int
    bonus_days: int
    candidate_subscription_ids: list[int]
    applied_subscription_id: int | None = None


@dataclass(slots=True)
class PaymentCreationResult:
    order: PaymentOrder
    plan: TariffPlan


@dataclass(slots=True)
class PaymentProcessingResult:
    state: Literal["not_found", "pending", "canceled", "succeeded", "already_processed"]
    order: PaymentOrder | None
    subscription: UserSubscription | None = None
    referral_event: ReferralRewardEvent | None = None


class BusinessService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        remnawave: RemnawaveClient,
        payments: BasePaymentGateway,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._remnawave = remnawave
        self._payments = payments
        self._settings = settings

    @staticmethod
    def _now() -> datetime:
        return datetime.now(tz=timezone.utc)

    async def get_or_create_profile(self, tg_user: User, referral_telegram_id: int | None = None) -> UserProfile:
        async with self._session_factory() as session:
            profile = await session.scalar(
                select(UserProfile).where(UserProfile.telegram_id == tg_user.id)
            )

            is_new = False
            if profile is None:
                profile = UserProfile(
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                )
                session.add(profile)
                await session.flush()
                is_new = True
            else:
                profile.username = tg_user.username
                profile.first_name = tg_user.first_name

            if is_new and referral_telegram_id and referral_telegram_id != tg_user.id:
                referrer = await session.scalar(
                    select(UserProfile).where(UserProfile.telegram_id == referral_telegram_id)
                )
                if referrer:
                    profile.referred_by_id = referrer.id
                    session.add(
                        Referral(
                            referrer_id=referrer.id,
                            invited_id=profile.id,
                            bonus_days=self._settings.referral_bonus_days,
                        )
                    )

            await session.commit()
            await session.refresh(profile)
            return profile

    async def get_profile_by_telegram_id(self, telegram_id: int) -> UserProfile | None:
        async with self._session_factory() as session:
            return await session.scalar(select(UserProfile).where(UserProfile.telegram_id == telegram_id))

    async def find_profile_by_identifier(self, identifier: str) -> UserProfile | None:
        raw = identifier.strip()
        if not raw:
            return None

        async with self._session_factory() as session:
            if raw.isdigit():
                return await session.scalar(
                    select(UserProfile).where(UserProfile.telegram_id == int(raw))
                )

            normalized = raw.lstrip("@").lower()
            return await session.scalar(
                select(UserProfile).where(func.lower(UserProfile.username) == normalized)
            )

    async def list_all_telegram_ids(self) -> list[int]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(UserProfile.telegram_id).order_by(UserProfile.id)
            )
            return [int(telegram_id) for telegram_id in rows]

    async def count_active_subscriptions(self, user_id: int) -> int:
        now = self._now()
        async with self._session_factory() as session:
            count = await session.scalar(
                select(func.count(UserSubscription.id)).where(
                    UserSubscription.user_id == user_id,
                    UserSubscription.is_active.is_(True),
                    UserSubscription.expire_at > now,
                )
            )
            return int(count or 0)

    @staticmethod
    def _apply_remote_to_subscription(subscription: UserSubscription, remote_user) -> None:
        subscription.remna_username = remote_user.username
        subscription.remna_short_uuid = remote_user.short_uuid
        subscription.subscription_url = remote_user.subscription_url
        subscription.expire_at = remote_user.expire_at

    async def list_user_subscriptions(self, user_id: int, *, refresh_remote: bool = False) -> list[UserSubscription]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(UserSubscription)
                .where(UserSubscription.user_id == user_id)
                .order_by(desc(UserSubscription.expire_at), desc(UserSubscription.id))
            )
            subscriptions = list(rows)

        if not refresh_remote:
            return subscriptions

        for subscription in subscriptions:
            try:
                remote = await self._remnawave.get_user(user_uuid=subscription.remna_uuid)
            except Exception:
                continue
            self._apply_remote_to_subscription(subscription, remote)
        return subscriptions

    async def get_user_subscription(
        self,
        *,
        user_id: int,
        subscription_id: int,
        refresh_remote: bool = False,
    ) -> UserSubscription:
        async with self._session_factory() as session:
            subscription = await session.scalar(
                select(UserSubscription).where(
                    UserSubscription.id == subscription_id,
                    UserSubscription.user_id == user_id,
                )
            )
            if not subscription:
                raise NotFoundError("Подписка не найдена")

        if refresh_remote:
            try:
                remote = await self._remnawave.get_user(user_uuid=subscription.remna_uuid)
            except Exception:
                return subscription
            self._apply_remote_to_subscription(subscription, remote)

        return subscription
    async def activate_trial(self, *, user_id: int, device_limit: int | None = None) -> UserSubscription:
        now = self._now()
        expire_at = now + timedelta(days=self._settings.free_trial_days)
        effective_limit = self._settings.device_limit if device_limit is None else device_limit

        async with self._session_factory() as session:
            profile = await session.scalar(
                select(UserProfile).where(UserProfile.id == user_id).with_for_update()
            )
            if not profile:
                raise NotFoundError("РџСЂРѕС„РёР»СЊ РЅРµ РЅР°Р№РґРµРЅ")
            if profile.free_trial_used_at is not None:
                raise TrialAlreadyUsedError("РџСЂРѕР±РЅС‹Р№ С‚Р°СЂРёС„ СѓР¶Рµ Р±С‹Р» Р°РєС‚РёРІРёСЂРѕРІР°РЅ")

            remna_user = await self._remnawave.create_user(
                expire_at=expire_at,
                telegram_id=profile.telegram_id,
                device_limit=effective_limit,
            )

            subscription = UserSubscription(
                user_id=profile.id,
                remna_uuid=remna_user.uuid,
                remna_short_uuid=remna_user.short_uuid,
                remna_username=remna_user.username,
                subscription_url=remna_user.subscription_url,
                expire_at=remna_user.expire_at,
                device_limit=effective_limit,
                is_trial=True,
                is_active=True,
            )
            session.add(subscription)
            profile.free_trial_used_at = now

            await session.commit()
            await session.refresh(subscription)
            return subscription

    async def create_payment_order(
        self,
        *,
        user_id: int,
        plan_code: str,
        action: PaymentAction,
        subscription_id: int | None,
        device_limit: int | None = None,
    ) -> PaymentCreationResult:
        plan = get_plan(plan_code)
        if plan.is_trial:
            raise ValueError("РџСЂРѕР±РЅС‹Р№ С‚Р°СЂРёС„ РЅРµ С‚СЂРµР±СѓРµС‚ РѕРїР»Р°С‚С‹")

        async with self._session_factory() as session:
            profile = await session.scalar(select(UserProfile).where(UserProfile.id == user_id))
            if not profile:
                raise NotFoundError("РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°Р№РґРµРЅ")

            if action == PaymentAction.EXTEND:
                if not subscription_id:
                    raise NotFoundError("РќРµ РїРµСЂРµРґР°РЅР° РїРѕРґРїРёСЃРєР° РґР»СЏ РїСЂРѕРґР»РµРЅРёСЏ")
                target = await session.scalar(
                    select(UserSubscription).where(
                        UserSubscription.id == subscription_id,
                        UserSubscription.user_id == user_id,
                    )
                )
                if not target:
                    raise NotFoundError("РџРѕРґРїРёСЃРєР° РґР»СЏ РїСЂРѕРґР»РµРЅРёСЏ РЅРµ РЅР°Р№РґРµРЅР°")

            order = PaymentOrder(
                user_id=user_id,
                subscription_id=subscription_id,
                plan_code=plan.code,
                action_type=action,
                amount_rub=plan.price_rub,
                status=PaymentStatus.PENDING,
                gateway=self._payments.provider_name,
                extra_payload={
                    "plan": plan.code,
                    "action": action.value,
                    "device_limit": device_limit,
                },
            )
            session.add(order)
            await session.flush()

            payment_result = await self._payments.create_payment(
                local_order_id=order.id,
                amount_rub=plan.price_rub,
                description=f"HideBroVPN: {plan.title}",
                metadata={
                    "user_id": str(user_id),
                    "plan": plan.code,
                    "action": action.value,
                    "subscription_id": str(subscription_id or 0),
                    "device_limit": str(device_limit or 0),
                },
            )
            order.gateway_payment_id = payment_result.gateway_payment_id
            order.payment_url = payment_result.payment_url
            order.status = PaymentStatus(map_gateway_status(payment_result.status))

            await session.commit()
            await session.refresh(order)
            return PaymentCreationResult(order=order, plan=plan)

    async def check_and_process_payment(
        self,
        *,
        user_id: int,
        plan_code: str,
        action: PaymentAction,
        subscription_id: int | None,
    ) -> PaymentProcessingResult:
        now = self._now()
        filters = [
            PaymentOrder.user_id == user_id,
            PaymentOrder.plan_code == plan_code,
            PaymentOrder.action_type == action,
        ]
        if subscription_id is None:
            filters.append(PaymentOrder.subscription_id.is_(None))
        else:
            filters.append(PaymentOrder.subscription_id == subscription_id)

        async with self._session_factory() as session:
            order = await session.scalar(
                select(PaymentOrder)
                .where(*filters)
                .order_by(desc(PaymentOrder.id))
                .limit(1)
                .with_for_update()
            )

            if not order:
                return PaymentProcessingResult(state="not_found", order=None)

            if order.status == PaymentStatus.SUCCEEDED and order.is_processed:
                subscription = await self._get_subscription_for_order(session, order)
                return PaymentProcessingResult(
                    state="already_processed",
                    order=order,
                    subscription=subscription,
                )

            if not order.gateway_payment_id:
                return PaymentProcessingResult(state="pending", order=order)

            gateway_status = await self._payments.check_payment(
                gateway_payment_id=order.gateway_payment_id
            )
            mapped = PaymentStatus(map_gateway_status(gateway_status.status))
            order.status = mapped

            if mapped == PaymentStatus.SUCCEEDED and gateway_status.paid_at:
                order.paid_at = gateway_status.paid_at

            if mapped == PaymentStatus.CANCELED:
                await session.commit()
                return PaymentProcessingResult(state="canceled", order=order)

            if mapped != PaymentStatus.SUCCEEDED:
                await session.commit()
                return PaymentProcessingResult(state="pending", order=order)

            if order.is_processed:
                subscription = await self._get_subscription_for_order(session, order)
                await session.commit()
                return PaymentProcessingResult(
                    state="already_processed",
                    order=order,
                    subscription=subscription,
                )

            subscription = await self._fulfill_paid_order(session=session, order=order, now=now)
            order.is_processed = True

            referral_event = await self._process_referral_after_first_paid(
                session=session,
                invited_user_id=user_id,
                now=now,
            )

            await session.commit()
            return PaymentProcessingResult(
                state="succeeded",
                order=order,
                subscription=subscription,
                referral_event=referral_event,
            )

    async def _fulfill_paid_order(
        self,
        *,
        session: AsyncSession,
        order: PaymentOrder,
        now: datetime,
    ) -> UserSubscription:
        plan = get_plan(order.plan_code)

        if order.action_type == PaymentAction.CREATE:
            profile = await session.scalar(
                select(UserProfile).where(UserProfile.id == order.user_id).with_for_update()
            )
            if not profile:
                raise NotFoundError("РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°Р№РґРµРЅ")

            raw_limit = order.extra_payload.get("device_limit") if order.extra_payload else None
            try:
                effective_limit = int(raw_limit) if raw_limit else self._settings.device_limit
            except (TypeError, ValueError):
                effective_limit = self._settings.device_limit

            expire_at = now + timedelta(days=plan.days)
            remna_user = await self._remnawave.create_user(
                expire_at=expire_at,
                telegram_id=profile.telegram_id,
                device_limit=effective_limit,
            )

            subscription = UserSubscription(
                user_id=order.user_id,
                remna_uuid=remna_user.uuid,
                remna_short_uuid=remna_user.short_uuid,
                remna_username=remna_user.username,
                subscription_url=remna_user.subscription_url,
                expire_at=remna_user.expire_at,
                device_limit=effective_limit,
                is_trial=False,
                is_active=True,
            )
            session.add(subscription)
            await session.flush()
            order.subscription_id = subscription.id
            return subscription

        if order.action_type == PaymentAction.EXTEND:
            if not order.subscription_id:
                raise NotFoundError("Р”Р»СЏ РїСЂРѕРґР»РµРЅРёСЏ РЅРµ РЅР°Р№РґРµРЅР° РїРѕРґРїРёСЃРєР°")

            subscription = await session.scalar(
                select(UserSubscription)
                .where(
                    UserSubscription.id == order.subscription_id,
                    UserSubscription.user_id == order.user_id,
                )
                .with_for_update()
            )
            if not subscription:
                raise NotFoundError("РџРѕРґРїРёСЃРєР° РґР»СЏ РїСЂРѕРґР»РµРЅРёСЏ РЅРµ РЅР°Р№РґРµРЅР°")

            base_date = subscription.expire_at if subscription.expire_at > now else now
            new_expire = base_date + timedelta(days=plan.days)
            remna_user = await self._remnawave.extend_user(
                user_uuid=subscription.remna_uuid,
                new_expire_at=new_expire,
                device_limit=subscription.device_limit,
            )
            subscription.expire_at = remna_user.expire_at
            subscription.subscription_url = remna_user.subscription_url
            subscription.is_active = True
            return subscription

        raise ValueError(f"РќРµРёР·РІРµСЃС‚РЅРѕРµ РґРµР№СЃС‚РІРёРµ Р·Р°РєР°Р·Р°: {order.action_type}")

    async def _get_subscription_for_order(
        self,
        session: AsyncSession,
        order: PaymentOrder,
    ) -> UserSubscription | None:
        if not order.subscription_id:
            return None
        return await session.scalar(
            select(UserSubscription).where(UserSubscription.id == order.subscription_id)
        )

    async def _process_referral_after_first_paid(
        self,
        *,
        session: AsyncSession,
        invited_user_id: int,
        now: datetime,
    ) -> ReferralRewardEvent | None:
        invited_profile = await session.scalar(
            select(UserProfile).where(UserProfile.id == invited_user_id).with_for_update()
        )
        if not invited_profile:
            return None

        if invited_profile.has_any_paid_purchase:
            return None

        invited_profile.has_any_paid_purchase = True

        referral = await session.scalar(
            select(Referral)
            .where(
                Referral.invited_id == invited_user_id,
                Referral.reward_locked_at.is_(None),
                Referral.rewarded_at.is_(None),
            )
            .with_for_update()
        )
        if not referral:
            return None

        referral.reward_locked_at = now

        referrer = await session.scalar(
            select(UserProfile).where(UserProfile.id == referral.referrer_id)
        )
        invited = await session.scalar(select(UserProfile).where(UserProfile.id == referral.invited_id))
        if not referrer or not invited:
            return None

        ref_subscriptions = list(
            await session.scalars(
                select(UserSubscription)
                .where(UserSubscription.user_id == referrer.id)
                .order_by(desc(UserSubscription.expire_at), desc(UserSubscription.id))
            )
        )

        if not ref_subscriptions:
            referral.rewarded_at = now
            return ReferralRewardEvent(
                kind="no_subscription",
                referral_id=referral.id,
                referrer_telegram_id=referrer.telegram_id,
                invited_telegram_id=invited.telegram_id,
                bonus_days=referral.bonus_days,
                candidate_subscription_ids=[],
            )

        if len(ref_subscriptions) == 1:
            updated = await self._extend_subscription_days(
                session=session,
                subscription=ref_subscriptions[0],
                days=referral.bonus_days,
                now=now,
            )
            referral.rewarded_at = now
            referral.reward_subscription_id = updated.id
            return ReferralRewardEvent(
                kind="auto_applied",
                referral_id=referral.id,
                referrer_telegram_id=referrer.telegram_id,
                invited_telegram_id=invited.telegram_id,
                bonus_days=referral.bonus_days,
                candidate_subscription_ids=[updated.id],
                applied_subscription_id=updated.id,
            )

        return ReferralRewardEvent(
            kind="choice_required",
            referral_id=referral.id,
            referrer_telegram_id=referrer.telegram_id,
            invited_telegram_id=invited.telegram_id,
            bonus_days=referral.bonus_days,
            candidate_subscription_ids=[sub.id for sub in ref_subscriptions],
        )

    async def apply_referral_reward_choice(
        self,
        *,
        referrer_telegram_id: int,
        referral_id: int,
        subscription_id: int,
    ) -> UserSubscription:
        now = self._now()
        async with self._session_factory() as session:
            referrer = await session.scalar(
                select(UserProfile).where(UserProfile.telegram_id == referrer_telegram_id)
            )
            if not referrer:
                raise AccessDeniedError("РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°Р№РґРµРЅ")

            referral = await session.scalar(
                select(Referral)
                .where(
                    Referral.id == referral_id,
                    Referral.referrer_id == referrer.id,
                    Referral.reward_locked_at.is_not(None),
                    Referral.rewarded_at.is_(None),
                )
                .with_for_update()
            )
            if not referral:
                raise NotFoundError("Р‘РѕРЅСѓСЃ СѓР¶Рµ РёСЃРїРѕР»СЊР·РѕРІР°РЅ РёР»Рё РЅРµРґРѕСЃС‚СѓРїРµРЅ")

            subscription = await session.scalar(
                select(UserSubscription)
                .where(
                    UserSubscription.id == subscription_id,
                    UserSubscription.user_id == referrer.id,
                )
                .with_for_update()
            )
            if not subscription:
                raise NotFoundError("РџРѕРґРїРёСЃРєР° РґР»СЏ Р±РѕРЅСѓСЃР° РЅРµ РЅР°Р№РґРµРЅР°")

            updated = await self._extend_subscription_days(
                session=session,
                subscription=subscription,
                days=referral.bonus_days,
                now=now,
            )

            referral.rewarded_at = now
            referral.reward_subscription_id = updated.id
            await session.commit()
            return updated

    async def _extend_subscription_days(
        self,
        *,
        session: AsyncSession,
        subscription: UserSubscription,
        days: int,
        now: datetime,
    ) -> UserSubscription:
        base_date = subscription.expire_at if subscription.expire_at > now else now
        new_expire = base_date + timedelta(days=days)

        remna_user = await self._remnawave.extend_user(
            user_uuid=subscription.remna_uuid,
            new_expire_at=new_expire,
            device_limit=subscription.device_limit,
        )
        subscription.expire_at = remna_user.expire_at
        subscription.subscription_url = remna_user.subscription_url
        subscription.is_active = True
        return subscription

    async def get_subscription_devices(
        self,
        *,
        user_id: int,
        subscription_id: int,
    ) -> tuple[UserSubscription, int, list[RemnawaveDevice]]:
        subscription = await self.get_user_subscription(
            user_id=user_id,
            subscription_id=subscription_id,
            refresh_remote=True,
        )
        total, devices = await self._remnawave.get_user_devices(user_uuid=subscription.remna_uuid)
        return subscription, total, devices

    async def detach_subscription_device(
        self,
        *,
        user_id: int,
        subscription_id: int,
        device_index: int,
    ) -> tuple[UserSubscription, RemnawaveDevice, int, list[RemnawaveDevice]]:
        if device_index < 1:
            raise NotFoundError("Устройство не найдено")

        subscription = await self.get_user_subscription(
            user_id=user_id,
            subscription_id=subscription_id,
            refresh_remote=True,
        )

        _, devices = await self._remnawave.get_user_devices(user_uuid=subscription.remna_uuid)
        if device_index > len(devices):
            raise NotFoundError("Устройство не найдено")

        removed_device = devices[device_index - 1]
        total, updated_devices = await self._remnawave.delete_user_device(
            user_uuid=subscription.remna_uuid,
            hwid=removed_device.hwid,
        )
        return subscription, removed_device, total, updated_devices
    async def get_admin_stats(self) -> dict[str, int]:
        now = self._now()
        async with self._session_factory() as session:
            users_total = int(await session.scalar(select(func.count(UserProfile.id))) or 0)
            subscriptions_total = int(await session.scalar(select(func.count(UserSubscription.id))) or 0)
            active_subscriptions = int(
                await session.scalar(
                    select(func.count(UserSubscription.id)).where(
                        UserSubscription.is_active.is_(True),
                        UserSubscription.expire_at > now,
                    )
                )
                or 0
            )
            paid_orders = int(
                await session.scalar(
                    select(func.count(PaymentOrder.id)).where(
                        PaymentOrder.status == PaymentStatus.SUCCEEDED,
                        PaymentOrder.is_processed.is_(True),
                    )
                )
                or 0
            )
            total_revenue = int(
                await session.scalar(
                    select(func.coalesce(func.sum(PaymentOrder.amount_rub), 0)).where(
                        PaymentOrder.status == PaymentStatus.SUCCEEDED,
                        PaymentOrder.is_processed.is_(True),
                    )
                )
                or 0
            )

        return {
            "users_total": users_total,
            "subscriptions_total": subscriptions_total,
            "active_subscriptions": active_subscriptions,
            "paid_orders": paid_orders,
            "total_revenue": total_revenue,
        }

    async def admin_issue_subscription(
        self,
        *,
        admin_telegram_id: int,
        target_identifier: str,
        days: int,
    ) -> tuple[UserProfile, UserSubscription]:
        now = self._now()
        target = await self.find_profile_by_identifier(target_identifier)
        if not target:
            raise NotFoundError("РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РїРѕ ID/username РЅРµ РЅР°Р№РґРµРЅ")

        expire_at = now + timedelta(days=days)

        async with self._session_factory() as session:
            admin_profile = await session.scalar(
                select(UserProfile).where(UserProfile.telegram_id == admin_telegram_id)
            )

            locked_target = await session.scalar(
                select(UserProfile).where(UserProfile.id == target.id).with_for_update()
            )
            if not locked_target:
                raise NotFoundError("РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°Р№РґРµРЅ")

            remna_user = await self._remnawave.create_user(
                expire_at=expire_at,
                telegram_id=locked_target.telegram_id,
            )

            subscription = UserSubscription(
                user_id=locked_target.id,
                remna_uuid=remna_user.uuid,
                remna_short_uuid=remna_user.short_uuid,
                remna_username=remna_user.username,
                subscription_url=remna_user.subscription_url,
                expire_at=remna_user.expire_at,
                device_limit=self._settings.device_limit,
                is_trial=False,
                is_active=True,
            )
            session.add(subscription)
            await session.flush()

            session.add(
                AdminGrant(
                    admin_user_id=admin_profile.id if admin_profile else None,
                    target_user_id=locked_target.id,
                    subscription_id=subscription.id,
                    days=days,
                )
            )
            await session.commit()
            await session.refresh(locked_target)
            await session.refresh(subscription)
            return locked_target, subscription

    async def get_subscriptions_by_ids(self, ids: list[int]) -> list[UserSubscription]:
        if not ids:
            return []
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(UserSubscription)
                .where(UserSubscription.id.in_(ids))
                .order_by(desc(UserSubscription.expire_at))
            )
            return list(rows)

    async def get_pending_referral_choices_for_referrer(
        self,
        *,
        referrer_telegram_id: int,
    ) -> list[ReferralRewardEvent]:
        async with self._session_factory() as session:
            referrer = await session.scalar(
                select(UserProfile).where(UserProfile.telegram_id == referrer_telegram_id)
            )
            if not referrer:
                return []

            referrals = list(
                await session.scalars(
                    select(Referral)
                    .where(
                        Referral.referrer_id == referrer.id,
                        Referral.reward_locked_at.is_not(None),
                        Referral.rewarded_at.is_(None),
                    )
                    .order_by(desc(Referral.id))
                )
            )
            if not referrals:
                return []

            subscriptions = list(
                await session.scalars(
                    select(UserSubscription)
                    .where(UserSubscription.user_id == referrer.id)
                    .order_by(desc(UserSubscription.expire_at), desc(UserSubscription.id))
                )
            )
            if len(subscriptions) < 2:
                return []

            events: list[ReferralRewardEvent] = []
            for referral in referrals:
                invited = await session.scalar(select(UserProfile).where(UserProfile.id == referral.invited_id))
                if not invited:
                    continue
                events.append(
                    ReferralRewardEvent(
                        kind="choice_required",
                        referral_id=referral.id,
                        referrer_telegram_id=referrer.telegram_id,
                        invited_telegram_id=invited.telegram_id,
                        bonus_days=referral.bonus_days,
                        candidate_subscription_ids=[s.id for s in subscriptions],
                    )
                )
            return events

