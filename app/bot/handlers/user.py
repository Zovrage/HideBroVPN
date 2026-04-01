from __future__ import annotations

import re
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import DeviceCb, MainMenuCb, PlanActionCb, ReferralCb, RewardChoiceCb, SubscriptionCb, TariffCb
from app.bot.keyboards import (
    devices_manage_keyboard,
    invite_link_keyboard,
    invite_menu_keyboard,
    main_menu_keyboard,
    plan_actions_keyboard,
    reward_choice_keyboard,
    subscription_actions_keyboard,
    subscriptions_keyboard,
    tariffs_keyboard,
)
from app.bot.texts import (
    devices_text,
    invite_link_text,
    invite_text,
    main_menu_text,
    payment_canceled_text,
    payment_created_text,
    payment_pending_text,
    payment_success_text,
    plan_details_text,
    subscription_details_text,
    subscriptions_list_text,
    tariffs_text,
    trial_success_text,
)
from app.bot.ui import replace_callback_message
from app.core.config import Settings
from app.db.models import PaymentAction, UserProfile
from app.domain.plans import get_plan
from app.services.business import BusinessService, ReferralRewardEvent
from app.services.errors import NotFoundError, PaymentGatewayError, RemnawaveAPIError, TrialAlreadyUsedError

router = Router(name="user")


REF_PATTERN = re.compile(r"^ref_(\d+)$")


def _parse_referral_arg(command: CommandObject | None) -> int | None:
    if not command or not command.args:
        return None
    match = REF_PATTERN.match(command.args.strip())
    if not match:
        return None
    return int(match.group(1))


def _mode_to_action(mode: str) -> PaymentAction:
    return PaymentAction.EXTEND if mode == "extend" else PaymentAction.CREATE


async def _ensure_profile(business: BusinessService, tg_user) -> UserProfile:
    return await business.get_or_create_profile(tg_user, referral_telegram_id=None)


async def _render_main_message(
    *,
    business: BusinessService,
    settings: Settings,
    profile: UserProfile,
) -> tuple[str, object]:
    active_count = await business.count_active_subscriptions(profile.id)
    text = main_menu_text(profile, active_count)
    keyboard = main_menu_keyboard(support_username=settings.support_username)
    return text, keyboard


async def _send_referral_event_notification(
    *,
    bot: Bot,
    business: BusinessService,
    event: ReferralRewardEvent,
) -> None:
    if event.kind == "auto_applied":
        await bot.send_message(
            chat_id=event.referrer_telegram_id,
            text=(
                "Ваш приглашённый пользователь оплатил подписку.\n\n"
                f"Бонус +{event.bonus_days} дней уже начислен автоматически."
            ),
        )
        return

    if event.kind == "choice_required":
        subscriptions = await business.get_subscriptions_by_ids(event.candidate_subscription_ids)
        if len(subscriptions) < 2:
            return
        await bot.send_message(
            chat_id=event.referrer_telegram_id,
            text=(
                "Ваш приглашённый пользователь оплатил подписку.\n\n"
                f"Выберите ключ для бонуса +{event.bonus_days} дней."
            ),
            reply_markup=reward_choice_keyboard(event.referral_id, subscriptions),
        )
        return

    if event.kind == "no_subscription":
        await bot.send_message(
            chat_id=event.referrer_telegram_id,
            text=(
                "Ваш приглашённый пользователь оплатил подписку, но у вас нет активных ключей для продления.\n"
                "Бонус не был применён."
            ),
        )


async def _send_pending_referral_choices(
    *,
    bot: Bot,
    business: BusinessService,
    referrer_telegram_id: int,
) -> None:
    events = await business.get_pending_referral_choices_for_referrer(
        referrer_telegram_id=referrer_telegram_id
    )
    for event in events:
        await _send_referral_event_notification(bot=bot, business=business, event=event)


@router.message(CommandStart())
async def start_handler(
    message: Message,
    command: CommandObject | None,
    business: BusinessService,
    settings: Settings,
) -> None:
    referral_telegram_id = _parse_referral_arg(command)
    profile = await business.get_or_create_profile(message.from_user, referral_telegram_id=referral_telegram_id)

    text, keyboard = await _render_main_message(business=business, settings=settings, profile=profile)
    await message.answer(text=text, reply_markup=keyboard, disable_web_page_preview=True)
    await _send_pending_referral_choices(
        bot=message.bot,
        business=business,
        referrer_telegram_id=message.from_user.id,
    )


@router.callback_query(MainMenuCb.filter())
async def main_menu_callback(
    callback: CallbackQuery,
    callback_data: MainMenuCb,
    business: BusinessService,
    settings: Settings,
) -> None:
    profile = await _ensure_profile(business, callback.from_user)

    if callback_data.action == "main":
        text, keyboard = await _render_main_message(business=business, settings=settings, profile=profile)
        await replace_callback_message(callback, text=text, reply_markup=keyboard)
        return

    if callback_data.action == "connect":
        include_trial = profile.free_trial_used_at is None
        await replace_callback_message(
            callback,
            text=tariffs_text(include_trial=include_trial, mode="new"),
            reply_markup=tariffs_keyboard(
                mode="new",
                include_trial=include_trial,
                back_to_subscriptions=False,
            ),
        )
        return

    if callback_data.action == "subscriptions":
        subscriptions = await business.list_user_subscriptions(profile.id, refresh_remote=True)
        await replace_callback_message(
            callback,
            text=subscriptions_list_text(subscriptions, settings.timezone),
            reply_markup=subscriptions_keyboard(subscriptions),
        )
        return

    if callback_data.action == "referral":
        await replace_callback_message(
            callback,
            text=invite_text(),
            reply_markup=invite_menu_keyboard(),
        )


@router.callback_query(TariffCb.filter())
async def tariff_select_callback(
    callback: CallbackQuery,
    callback_data: TariffCb,
    business: BusinessService,
    settings: Settings,
) -> None:
    plan = get_plan(callback_data.plan)
    profile = await _ensure_profile(business, callback.from_user)

    if plan.is_trial:
        try:
            subscription = await business.activate_trial(user_id=profile.id)
        except TrialAlreadyUsedError:
            await replace_callback_message(
                callback,
                text="Пробный тариф уже был выдан ранее. Выберите платный тариф.",
                reply_markup=tariffs_keyboard(
                    mode="new",
                    include_trial=False,
                    back_to_subscriptions=False,
                ),
            )
            return
        except RemnawaveAPIError:
            await replace_callback_message(
                callback,
                text="Не удалось создать пробный ключ. Попробуйте чуть позже или обратитесь в поддержку.",
                reply_markup=main_menu_keyboard(support_username=settings.support_username),
            )
            return

        text, keyboard = await _render_main_message(business=business, settings=settings, profile=profile)
        await replace_callback_message(
            callback,
            text=f"{trial_success_text(subscription, settings.timezone)}\n\n{text}",
            reply_markup=keyboard,
        )
        return

    await replace_callback_message(
        callback,
        text=plan_details_text(plan, mode=callback_data.mode),
        reply_markup=plan_actions_keyboard(
            plan_code=plan.code,
            mode=callback_data.mode,
            sub_id=callback_data.sub,
        ),
    )


@router.callback_query(PlanActionCb.filter())
async def plan_action_callback(
    callback: CallbackQuery,
    callback_data: PlanActionCb,
    business: BusinessService,
    settings: Settings,
) -> None:
    profile = await _ensure_profile(business, callback.from_user)
    plan = get_plan(callback_data.plan)

    if callback_data.action == "back":
        if callback_data.mode == "extend":
            if callback_data.sub > 0:
                try:
                    subscription = await business.get_user_subscription(
                        user_id=profile.id,
                        subscription_id=callback_data.sub,
                        refresh_remote=True,
                    )
                except NotFoundError:
                    subscriptions = await business.list_user_subscriptions(profile.id, refresh_remote=True)
                    await replace_callback_message(
                        callback,
                        text=subscriptions_list_text(subscriptions, settings.timezone),
                        reply_markup=subscriptions_keyboard(subscriptions),
                    )
                else:
                    await replace_callback_message(
                        callback,
                        text=subscription_details_text(subscription, settings.timezone),
                        reply_markup=subscription_actions_keyboard(subscription),
                    )
                return

            subscriptions = await business.list_user_subscriptions(profile.id, refresh_remote=True)
            await replace_callback_message(
                callback,
                text=subscriptions_list_text(subscriptions, settings.timezone),
                reply_markup=subscriptions_keyboard(subscriptions),
            )
            return

        include_trial = profile.free_trial_used_at is None
        await replace_callback_message(
            callback,
            text=tariffs_text(include_trial=include_trial, mode="new"),
            reply_markup=tariffs_keyboard(mode="new", include_trial=include_trial),
        )
        return

    action_type = _mode_to_action(callback_data.mode)
    target_subscription_id = callback_data.sub if callback_data.sub > 0 else None

    if callback_data.action == "pay":
        try:
            created = await business.create_payment_order(
                user_id=profile.id,
                plan_code=plan.code,
                action=action_type,
                subscription_id=target_subscription_id,
            )
        except (NotFoundError, PaymentGatewayError, RemnawaveAPIError, ValueError) as exc:
            await replace_callback_message(
                callback,
                text=str(exc),
                reply_markup=main_menu_keyboard(support_username=settings.support_username),
            )
            return

        await replace_callback_message(
            callback,
            text=payment_created_text(created.plan, created.order.payment_url),
            reply_markup=plan_actions_keyboard(
                plan_code=plan.code,
                mode=callback_data.mode,
                sub_id=callback_data.sub,
            ),
        )
        return

    if callback_data.action == "check":
        try:
            result = await business.check_and_process_payment(
                user_id=profile.id,
                plan_code=plan.code,
                action=action_type,
                subscription_id=target_subscription_id,
            )
        except (PaymentGatewayError, RemnawaveAPIError) as exc:
            await replace_callback_message(
                callback,
                text=f"Ошибка проверки оплаты: {exc}",
                reply_markup=plan_actions_keyboard(
                    plan_code=plan.code,
                    mode=callback_data.mode,
                    sub_id=callback_data.sub,
                ),
            )
            return

        if result.state == "not_found":
            await replace_callback_message(
                callback,
                text="Активный заказ не найден. Нажмите «Оплатить», чтобы создать заказ.",
                reply_markup=plan_actions_keyboard(
                    plan_code=plan.code,
                    mode=callback_data.mode,
                    sub_id=callback_data.sub,
                ),
            )
            return

        if result.state == "pending":
            await replace_callback_message(
                callback,
                text=payment_pending_text(),
                reply_markup=plan_actions_keyboard(
                    plan_code=plan.code,
                    mode=callback_data.mode,
                    sub_id=callback_data.sub,
                ),
            )
            return

        if result.state == "canceled":
            await replace_callback_message(
                callback,
                text=payment_canceled_text(),
                reply_markup=plan_actions_keyboard(
                    plan_code=plan.code,
                    mode=callback_data.mode,
                    sub_id=callback_data.sub,
                ),
            )
            return

        if result.subscription is None:
            await replace_callback_message(
                callback,
                text="Оплата подтверждена, но подписка не найдена. Напишите в поддержку.",
                reply_markup=main_menu_keyboard(support_username=settings.support_username),
            )
            return

        if result.referral_event is not None:
            await _send_referral_event_notification(
                bot=callback.bot,
                business=business,
                event=result.referral_event,
            )

        text, keyboard = await _render_main_message(business=business, settings=settings, profile=profile)
        await replace_callback_message(
            callback,
            text=f"{payment_success_text(result.subscription, settings.timezone)}\n\n{text}",
            reply_markup=keyboard,
        )


@router.callback_query(SubscriptionCb.filter())
async def subscription_callback(
    callback: CallbackQuery,
    callback_data: SubscriptionCb,
    business: BusinessService,
    settings: Settings,
) -> None:
    profile = await _ensure_profile(business, callback.from_user)

    if callback_data.action == "open":
        try:
            subscription = await business.get_user_subscription(
                user_id=profile.id,
                subscription_id=callback_data.sub,
                refresh_remote=True,
            )
        except NotFoundError as exc:
            await replace_callback_message(
                callback,
                text=str(exc),
                reply_markup=main_menu_keyboard(support_username=settings.support_username),
            )
            return

        await replace_callback_message(
            callback,
            text=subscription_details_text(subscription, settings.timezone),
            reply_markup=subscription_actions_keyboard(subscription),
        )
        return

    if callback_data.action == "connect":
        try:
            subscription = await business.get_user_subscription(
                user_id=profile.id,
                subscription_id=callback_data.sub,
                refresh_remote=True,
            )
        except NotFoundError as exc:
            await replace_callback_message(
                callback,
                text=str(exc),
                reply_markup=main_menu_keyboard(support_username=settings.support_username),
            )
            return

        await replace_callback_message(
            callback,
            text=subscription_details_text(subscription, settings.timezone),
            reply_markup=subscription_actions_keyboard(subscription),
        )
        return

    if callback_data.action == "extend":
        await replace_callback_message(
            callback,
            text=tariffs_text(include_trial=False, mode="extend"),
            reply_markup=tariffs_keyboard(
                mode="extend",
                sub_id=callback_data.sub,
                include_trial=False,
                back_to_subscription_id=callback_data.sub,
            ),
        )
        return

    if callback_data.action == "devices":
        try:
            subscription, total, devices = await business.get_subscription_devices(
                user_id=profile.id,
                subscription_id=callback_data.sub,
            )
        except (NotFoundError, RemnawaveAPIError) as exc:
            await replace_callback_message(
                callback,
                text=str(exc),
                reply_markup=main_menu_keyboard(support_username=settings.support_username),
            )
            return

        await replace_callback_message(
            callback,
            text=devices_text(
                subscription=subscription,
                total=total,
                devices=devices,
                tz=settings.timezone,
                limit=settings.device_limit,
            ),
            reply_markup=devices_manage_keyboard(callback_data.sub, devices),
        )


@router.callback_query(DeviceCb.filter(F.action == "detach"))
async def device_detach_callback(
    callback: CallbackQuery,
    callback_data: DeviceCb,
    business: BusinessService,
    settings: Settings,
) -> None:
    profile = await _ensure_profile(business, callback.from_user)
    try:
        subscription, removed_device, total, devices = await business.detach_subscription_device(
            user_id=profile.id,
            subscription_id=callback_data.sub,
            device_index=callback_data.idx,
        )
    except (NotFoundError, RemnawaveAPIError) as exc:
        await replace_callback_message(
            callback,
            text=str(exc),
            reply_markup=main_menu_keyboard(support_username=settings.support_username),
        )
        return

    platform = removed_device.platform or "Unknown"
    model = removed_device.device_model or "Unknown"
    await replace_callback_message(
        callback,
        text=(
            f"Устройство отключено: <b>{platform} / {model}</b>\n\n"
            + devices_text(
                subscription=subscription,
                total=total,
                devices=devices,
                tz=settings.timezone,
                limit=settings.device_limit,
            )
        ),
        reply_markup=devices_manage_keyboard(callback_data.sub, devices),
    )


@router.callback_query(ReferralCb.filter(F.action == "link"))
async def referral_link_callback(
    callback: CallbackQuery,
    bot_username: str,
) -> None:
    link = f"https://t.me/{bot_username}?start=ref_{callback.from_user.id}"
    await replace_callback_message(
        callback,
        text=invite_link_text(link),
        reply_markup=invite_link_keyboard(),
    )


@router.callback_query(RewardChoiceCb.filter())
async def referral_reward_choice_callback(
    callback: CallbackQuery,
    callback_data: RewardChoiceCb,
    business: BusinessService,
    settings: Settings,
) -> None:
    try:
        subscription = await business.apply_referral_reward_choice(
            referrer_telegram_id=callback.from_user.id,
            referral_id=callback_data.referral_id,
            subscription_id=callback_data.sub,
        )
    except (NotFoundError, RemnawaveAPIError) as exc:
        await replace_callback_message(
            callback,
            text=str(exc),
            reply_markup=main_menu_keyboard(support_username=settings.support_username),
        )
        return

    await replace_callback_message(
        callback,
        text=(
            "Бонус успешно применён.\n\n"
            f"Ключ: <pre>{subscription.remna_username}</pre>\n\n"
            f"Новый срок: <b>{subscription.expire_at.astimezone(ZoneInfo(settings.timezone)).strftime('%d.%m.%Y %H:%M')}</b>"
        ),
        reply_markup=main_menu_keyboard(support_username=settings.support_username),
    )

