from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    AdminIssueCb,
    AdminMenuCb,
    DeviceCb,
    MainMenuCb,
    PlanActionCb,
    ReferralCb,
    RewardChoiceCb,
    SubscriptionCb,
    TariffCb,
)
from app.db.models import UserSubscription
from app.domain.plans import PAID_PLAN_CODES, PLANS
from app.services.remnawave import RemnawaveDevice

EMOJI_CONNECT = "\U0001F6DC"
EMOJI_SUBS = "\U0001F4E6"
EMOJI_REF = "\U0001F517"
EMOJI_SUPPORT = "\U0001F3A7"
EMOJI_BACK = "\U0001F519"
EMOJI_PAY = "\U0001F4B3"
EMOJI_CHECK = "\u2705"
EMOJI_EXTEND = "\u267b\ufe0f"
EMOJI_DEVICES = "\U0001F4F1"
EMOJI_GIFT = "\U0001F381"
EMOJI_DISCONNECT = "\u274c"
RUBLE = "\u20bd"


def main_menu_keyboard(*, support_username: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=f"Подключиться {EMOJI_CONNECT}", callback_data=MainMenuCb(action="connect").pack()))
    kb.row(InlineKeyboardButton(text=f"Мои подписки {EMOJI_SUBS}", callback_data=MainMenuCb(action="subscriptions").pack()))
    kb.row(InlineKeyboardButton(text=f"Пригласить друга {EMOJI_REF}", callback_data=MainMenuCb(action="referral").pack()))
    kb.row(
        InlineKeyboardButton(
            text=f"Тех поддержка {EMOJI_SUPPORT}",
            url=f"https://t.me/{support_username}",
        )
    )
    return kb.as_markup()


def tariffs_keyboard(
    *,
    mode: str,
    sub_id: int = 0,
    include_trial: bool = True,
    back_to_subscriptions: bool = False,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for code, plan in PLANS.items():
        if plan.is_trial and not include_trial:
            continue
        if not include_trial and code not in PAID_PLAN_CODES:
            continue

        if plan.is_trial:
            text = f"{plan.emoji} {plan.title}"
        else:
            text = f"{plan.emoji} {plan.title} - {plan.price_rub} {RUBLE}"

        kb.row(
            InlineKeyboardButton(
                text=text,
                callback_data=TariffCb(plan=code, mode=mode, sub=sub_id).pack(),
            )
        )

    back_action = "subscriptions" if back_to_subscriptions else "main"
    kb.row(InlineKeyboardButton(text=f"Назад {EMOJI_BACK}", callback_data=MainMenuCb(action=back_action).pack()))
    return kb.as_markup()


def plan_actions_keyboard(*, plan_code: str, mode: str, sub_id: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text=f"Оплатить {EMOJI_PAY}",
            callback_data=PlanActionCb(action="pay", plan=plan_code, mode=mode, sub=sub_id).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=f"Проверить оплату {EMOJI_CHECK}",
            callback_data=PlanActionCb(action="check", plan=plan_code, mode=mode, sub=sub_id).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=f"Назад {EMOJI_BACK}",
            callback_data=PlanActionCb(action="back", plan=plan_code, mode=mode, sub=sub_id).pack(),
        )
    )
    return kb.as_markup()


def subscriptions_keyboard(subscriptions: list[UserSubscription]) -> InlineKeyboardMarkup:
    """List screen: one button per subscription + back."""
    kb = InlineKeyboardBuilder()
    for subscription in subscriptions:
        kb.row(
            InlineKeyboardButton(
                text=subscription.remna_username,
                callback_data=SubscriptionCb(action="open", sub=subscription.id).pack(),
            )
        )

    kb.row(InlineKeyboardButton(text=f"Назад {EMOJI_BACK}", callback_data=MainMenuCb(action="main").pack()))
    return kb.as_markup()


def subscription_actions_keyboard(subscription: UserSubscription) -> InlineKeyboardMarkup:
    """Details screen for one subscription."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text=f"Подключиться {EMOJI_CONNECT}",
            url=subscription.subscription_url,
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=f"Устройства {EMOJI_DEVICES}",
            callback_data=SubscriptionCb(action="devices", sub=subscription.id).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=f"Продлить {EMOJI_EXTEND}",
            callback_data=SubscriptionCb(action="extend", sub=subscription.id).pack(),
        )
    )
    kb.row(InlineKeyboardButton(text=f"Назад {EMOJI_BACK}", callback_data=MainMenuCb(action="subscriptions").pack()))
    return kb.as_markup()


def devices_manage_keyboard(subscription_id: int, devices: list[RemnawaveDevice]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for idx, device in enumerate(devices, start=1):
        platform = device.platform or "Unknown"
        model = device.device_model or "Unknown"
        caption = f"{EMOJI_DISCONNECT} Отключить {idx}: {platform}/{model}"
        kb.row(
            InlineKeyboardButton(
                text=caption[:60],
                callback_data=DeviceCb(action="detach", sub=subscription_id, idx=idx).pack(),
            )
        )

    kb.row(
        InlineKeyboardButton(
            text=f"Назад {EMOJI_BACK}",
            callback_data=SubscriptionCb(action="open", sub=subscription_id).pack(),
        )
    )
    return kb.as_markup()


def devices_back_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=f"Назад {EMOJI_BACK}", callback_data=MainMenuCb(action="subscriptions").pack()))
    return kb.as_markup()


def invite_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=f"Ваша ссылка {EMOJI_REF}", callback_data=ReferralCb(action="link").pack()))
    kb.row(InlineKeyboardButton(text=f"Назад {EMOJI_BACK}", callback_data=MainMenuCb(action="main").pack()))
    return kb.as_markup()


def invite_link_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=f"Назад {EMOJI_BACK}", callback_data=MainMenuCb(action="referral").pack()))
    return kb.as_markup()


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Статистика", callback_data=AdminMenuCb(action="stats").pack()))
    kb.row(InlineKeyboardButton(text=f"Выдача ключей {EMOJI_GIFT}", callback_data=AdminMenuCb(action="issue").pack()))
    kb.row(InlineKeyboardButton(text="Главное меню", callback_data=AdminMenuCb(action="main").pack()))
    return kb.as_markup()


def admin_issue_prompt_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=f"Назад {EMOJI_BACK}", callback_data=AdminMenuCb(action="back").pack()))
    return kb.as_markup()


def admin_issue_days_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="3 дня", callback_data=AdminIssueCb(action="days", value="3").pack()))
    kb.row(InlineKeyboardButton(text="30 дней", callback_data=AdminIssueCb(action="days", value="30").pack()))
    kb.row(InlineKeyboardButton(text="90 дней", callback_data=AdminIssueCb(action="days", value="90").pack()))
    kb.row(InlineKeyboardButton(text="180 дней", callback_data=AdminIssueCb(action="days", value="180").pack()))
    kb.row(InlineKeyboardButton(text="365 дней", callback_data=AdminIssueCb(action="days", value="365").pack()))
    kb.row(InlineKeyboardButton(text=f"Назад {EMOJI_BACK}", callback_data=AdminMenuCb(action="back").pack()))
    return kb.as_markup()


def reward_choice_keyboard(referral_id: int, subscriptions: list[UserSubscription]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for subscription in subscriptions:
        kb.row(
            InlineKeyboardButton(
                text=f"Ключ #{subscription.id}",
                callback_data=RewardChoiceCb(referral_id=referral_id, sub=subscription.id).pack(),
            )
        )
    return kb.as_markup()
