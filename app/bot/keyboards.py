from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    AdminIssueCb,
    AdminMenuCb,
    DeviceCb,
    DeviceTierCb,
    MainMenuCb,
    PlanActionCb,
    ReferralCb,
    RewardChoiceCb,
    SubscriptionCb,
    TariffCb,
)
from app.db.models import UserSubscription
from app.domain.plans import PAID_PLAN_CODES, PLANS, get_plan_price
from app.services.remnawave import RemnawaveDevice

RUBLE = "\u20bd"


def main_menu_keyboard(*, support_username: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Купить подписку", callback_data=MainMenuCb(action="connect").pack()))
    kb.row(InlineKeyboardButton(text="📂 Мои подписки", callback_data=MainMenuCb(action="subscriptions").pack()))
    kb.row(InlineKeyboardButton(text="👥 Пригласить друга", callback_data=MainMenuCb(action="referral").pack()))
    kb.row(
        InlineKeyboardButton(
            text="🎧 Тех поддержка",
            url=f"https://t.me/{support_username}",
        )
    )
    return kb.as_markup()


def device_tiers_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📱 1 устройство", callback_data=DeviceTierCb(limit=1).pack()))
    kb.row(InlineKeyboardButton(text="📱 3 устройства", callback_data=DeviceTierCb(limit=3).pack()))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data=MainMenuCb(action="main").pack()))
    return kb.as_markup()


def tariffs_keyboard(
    *,
    mode: str,
    sub_id: int = 0,
    include_trial: bool = True,
    device_limit: int = 1,
    back_to_subscriptions: bool = False,
    back_to_subscription_id: int | None = None,
    back_to_connect: bool = False,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for code, plan in PLANS.items():
        if plan.is_trial and not include_trial:
            continue
        if not include_trial and code not in PAID_PLAN_CODES:
            continue

        device_suffix = ""
        if device_limit > 0:
            device_suffix = (
                f"{device_limit} устройство" if device_limit == 1 else f"{device_limit} устройства"
            )
        if plan.is_trial:
            text = f"🎁 {plan.title}" + (f" - {device_suffix}" if device_suffix else "")
        else:
            price_rub = get_plan_price(plan.code, device_limit if device_limit > 0 else 1)
            text = f"💳 {plan.title} - {price_rub} {RUBLE}" + (
                f" - {device_suffix}" if device_suffix else ""
            )

        kb.row(
            InlineKeyboardButton(
                text=text,
                callback_data=TariffCb(plan=code, mode=mode, sub=sub_id, limit=device_limit).pack(),
            )
        )

    if back_to_subscription_id and back_to_subscription_id > 0:
        back_callback = SubscriptionCb(action="open", sub=back_to_subscription_id).pack()
    else:
        if back_to_connect:
            back_action = "connect"
        else:
            back_action = "subscriptions" if back_to_subscriptions else "main"
        back_callback = MainMenuCb(action=back_action).pack()

    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data=back_callback))
    return kb.as_markup()


def plan_actions_keyboard(
    *,
    plan_code: str,
    mode: str,
    sub_id: int = 0,
    payment_url: str | None = None,
    device_limit: int = 0,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    if payment_url:
        kb.row(InlineKeyboardButton(text="💳 Оплатить заказ", url=payment_url))
    else:
        kb.row(
            InlineKeyboardButton(
                text="💳 Оплатить",
                callback_data=PlanActionCb(
                    action="pay", plan=plan_code, mode=mode, sub=sub_id, limit=device_limit
                ).pack(),
            )
        )

    kb.row(
        InlineKeyboardButton(
            text="✅ Проверить оплату",
            callback_data=PlanActionCb(
                action="check", plan=plan_code, mode=mode, sub=sub_id, limit=device_limit
            ).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="◀️ Назад",
            callback_data=PlanActionCb(
                action="back", plan=plan_code, mode=mode, sub=sub_id, limit=device_limit
            ).pack(),
        )
    )
    return kb.as_markup()


def subscriptions_keyboard(subscriptions: list[UserSubscription]) -> InlineKeyboardMarkup:
    """List screen: one button per subscription + back."""
    kb = InlineKeyboardBuilder()
    for subscription in subscriptions:
        kb.row(
            InlineKeyboardButton(
                text=f"🔑 {subscription.remna_username}",
                callback_data=SubscriptionCb(action="open", sub=subscription.id).pack(),
            )
        )

    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data=MainMenuCb(action="main").pack()))
    return kb.as_markup()


def subscription_actions_keyboard(subscription: UserSubscription) -> InlineKeyboardMarkup:
    """Details screen for one subscription."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="🔌 Подключиться",
            url=subscription.subscription_url,
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="📘 Инструкция",
            callback_data=SubscriptionCb(action="instruction", sub=subscription.id).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="📱 Устройства",
            callback_data=SubscriptionCb(action="devices", sub=subscription.id).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="🔄 Продлить",
            callback_data=SubscriptionCb(action="extend", sub=subscription.id).pack(),
        )
    )
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data=MainMenuCb(action="subscriptions").pack()))
    return kb.as_markup()


def subscription_instruction_devices_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="📱 Android",
            callback_data=SubscriptionCb(action="instruction_android", sub=subscription_id).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="📱 iPhone / iPad",
            callback_data=SubscriptionCb(action="instruction_ios", sub=subscription_id).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="🖥️ Windows",
            callback_data=SubscriptionCb(action="instruction_windows", sub=subscription_id).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="💻 macOS",
            callback_data=SubscriptionCb(action="instruction_macos", sub=subscription_id).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="◀️ Назад к подписке",
            callback_data=SubscriptionCb(action="open", sub=subscription_id).pack(),
        )
    )
    return kb.as_markup()


def subscription_instruction_keyboard(subscription_id: int, subscription_url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔌 Подключиться", url=subscription_url))
    kb.row(
        InlineKeyboardButton(
            text="📱 Выбрать устройство",
            callback_data=SubscriptionCb(action="instruction", sub=subscription_id).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="◀️ Назад к подписке",
            callback_data=SubscriptionCb(action="open", sub=subscription_id).pack(),
        )
    )
    return kb.as_markup()


def devices_manage_keyboard(subscription_id: int, devices: list[RemnawaveDevice]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for idx, device in enumerate(devices, start=1):
        platform = device.platform or "Unknown"
        model = device.device_model or "Unknown"
        caption = f"Отключить {idx}: {platform}/{model}"
        kb.row(
            InlineKeyboardButton(
                text=f"❌ {caption}"[:60],
                callback_data=DeviceCb(action="detach", sub=subscription_id, idx=idx).pack(),
            )
        )

    kb.row(
        InlineKeyboardButton(
            text="◀️ Назад",
            callback_data=SubscriptionCb(action="open", sub=subscription_id).pack(),
        )
    )
    return kb.as_markup()


def devices_back_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data=MainMenuCb(action="subscriptions").pack()))
    return kb.as_markup()


def invite_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔗 Ваша ссылка", callback_data=ReferralCb(action="link").pack()))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data=MainMenuCb(action="main").pack()))
    return kb.as_markup()


def invite_link_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data=MainMenuCb(action="referral").pack()))
    return kb.as_markup()


def expired_subscription_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="🔄 Продлить",
            callback_data=SubscriptionCb(action="extend", sub=subscription_id).pack(),
        )
    )
    kb.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data=MainMenuCb(action="main").pack()))
    return kb.as_markup()


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📊 Статистика", callback_data=AdminMenuCb(action="stats").pack()))
    kb.row(InlineKeyboardButton(text="🎁 Выдача подписок", callback_data=AdminMenuCb(action="issue").pack()))
    kb.row(InlineKeyboardButton(text="🔄 Продлить подписку", callback_data=AdminMenuCb(action="extend").pack()))
    kb.row(InlineKeyboardButton(text="📣 Рассылка", callback_data=AdminMenuCb(action="broadcast").pack()))
    kb.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data=AdminMenuCb(action="main").pack()))
    return kb.as_markup()


def admin_issue_prompt_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data=AdminMenuCb(action="back").pack()))
    return kb.as_markup()


def admin_issue_device_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📱 1 устройство", callback_data=AdminIssueCb(action="limit", value="1").pack()))
    kb.row(InlineKeyboardButton(text="📱 3 устройства", callback_data=AdminIssueCb(action="limit", value="3").pack()))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data=AdminMenuCb(action="back").pack()))
    return kb.as_markup()


def admin_issue_months_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for months in _admin_extend_month_options():
        kb.row(
            InlineKeyboardButton(
                text=f"🗓️ {_month_label(months)}",
                callback_data=AdminIssueCb(action="issue_months", value=str(months)).pack(),
            )
        )
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data=AdminMenuCb(action="back").pack()))
    return kb.as_markup()


def admin_extend_subscriptions_keyboard(subscriptions: list[UserSubscription]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for subscription in subscriptions:
        kb.row(
            InlineKeyboardButton(
                text=f"🔑 {subscription.remna_username}"[:64],
                callback_data=AdminIssueCb(action="extend_pick", value=str(subscription.id)).pack(),
            )
        )
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data=AdminMenuCb(action="back").pack()))
    return kb.as_markup()


def admin_extend_months_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for months in _admin_extend_month_options():
        kb.row(
            InlineKeyboardButton(
                text=f"🗓️ {_month_label(months)}",
                callback_data=AdminIssueCb(action="extend_months", value=str(months)).pack(),
            )
        )
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data=AdminMenuCb(action="back").pack()))
    return kb.as_markup()


def _admin_extend_month_options() -> list[int]:
    months_options: set[int] = set()
    for code, plan in PLANS.items():
        if plan.is_trial:
            continue
        if not code.startswith("m"):
            continue
        raw = code[1:]
        if not raw.isdigit():
            continue
        months_options.add(int(raw))
    return sorted(months_options)


def _month_label(months: int) -> str:
    rem10 = months % 10
    rem100 = months % 100
    if rem10 == 1 and rem100 != 11:
        suffix = "месяц"
    elif rem10 in (2, 3, 4) and rem100 not in (12, 13, 14):
        suffix = "месяца"
    else:
        suffix = "месяцев"
    return f"{months} {suffix}"


def reward_choice_keyboard(referral_id: int, subscriptions: list[UserSubscription]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for subscription in subscriptions:
        kb.row(
            InlineKeyboardButton(
                text=f"🔑 {subscription.remna_username}",
                callback_data=RewardChoiceCb(referral_id=referral_id, sub=subscription.id).pack(),
            )
        )
    return kb.as_markup()
