from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from app.db.models import UserProfile, UserSubscription
from app.domain.plans import TariffPlan
from app.services.remnawave import RemnawaveDevice

EMOJI_SHIELD = "\U0001F6E1\ufe0f"
EMOJI_LINK = "\U0001F517"
RUBLE = "\u20bd"


def _safe_nickname(profile: UserProfile) -> str:
    if profile.username:
        return f"@{escape(profile.username)}"
    if profile.first_name:
        return escape(profile.first_name)
    return "не указан"


def _fmt_dt(dt: datetime, tz: str) -> str:
    local = dt.astimezone(ZoneInfo(tz))
    return local.strftime("%d.%m.%Y %H:%M")


def main_menu_text(profile: UserProfile, active_subscriptions_count: int) -> str:
    return (
        f"<blockquote>{EMOJI_SHIELD}HideBroVPN - стабильный VPN для работы, игр и путешествий.</blockquote>\n\n"
        f"ID: <code>{profile.telegram_id}</code>\n"
        f"Имя пользователя: {_safe_nickname(profile)}\n"
        f"Активные подписки: <b>{active_subscriptions_count}</b>"
    )


def tariffs_text(*, include_trial: bool, mode: str) -> str:
    if mode == "extend":
        return "Выберите срок продления для вашей подписки:"

    if include_trial:
        return "Выберите тариф для подключения. Пробный тариф доступен только один раз."
    return "Выберите тариф для подключения. Пробный тариф уже использован."


def plan_details_text(plan: TariffPlan, *, mode: str) -> str:
    action = "Продление" if mode == "extend" else "Подключение"
    return (
        f"<b>{action}</b>\n"
        f"Тариф: {plan.emoji} {escape(plan.title)}\n"
        f"Срок: <b>{plan.days} дней</b>\n"
        f"Стоимость: <b>{plan.price_rub} {RUBLE}</b>\n\n"
        "Нажмите \"Оплатить \U0001F4B3\", затем \"Проверить оплату \u2705\"."
    )


def payment_created_text(plan: TariffPlan, payment_url: str | None) -> str:
    if payment_url:
        return (
            f"Заказ на тариф {plan.emoji} <b>{escape(plan.title)}</b> создан.\n"
            f"Сумма: <b>{plan.price_rub} {RUBLE}</b>\n\n"
            f"Ссылка на оплату: <a href=\"{escape(payment_url)}\">Оплатить заказ</a>"
        )
    return (
        f"Заказ на тариф {plan.emoji} <b>{escape(plan.title)}</b> создан.\n"
        "Платежный провайдер не вернул ссылку оплаты. Обратитесь в поддержку."
    )


def payment_success_text(subscription: UserSubscription, tz: str) -> str:
    return (
        "Оплата подтверждена, подписка активирована.\n"
        f"Ключ: <code>{escape(subscription.remna_username)}</code>\n"
        f"Действует до: <b>{_fmt_dt(subscription.expire_at, tz)}</b>\n"
        f"Ссылка: <a href=\"{escape(subscription.subscription_url)}\">Подключиться</a>"
    )


def payment_pending_text() -> str:
    return "Оплата пока не подтверждена. Если вы уже оплатили, подождите 5-20 секунд и нажмите \"Проверить оплату \u2705\" ещё раз."


def payment_canceled_text() -> str:
    return "Платёж отменён или не завершён. Можно снова нажать \"Оплатить \U0001F4B3\" и пройти оплату."


def trial_success_text(subscription: UserSubscription, tz: str) -> str:
    return (
        "Пробный доступ на 3 дня активирован.\n"
        f"Ключ: <code>{escape(subscription.remna_username)}</code>\n"
        f"Действует до: <b>{_fmt_dt(subscription.expire_at, tz)}</b>\n"
        f"Ссылка: <a href=\"{escape(subscription.subscription_url)}\">Подключиться</a>"
    )


def subscriptions_text(subscriptions: list[UserSubscription], tz: str) -> str:
    if not subscriptions:
        return "У вас пока нет подписок. Нажмите \"Подключиться \U0001F6DC\", чтобы создать первую."

    lines = ["<b>Ваши подписки:</b>"]
    for index, subscription in enumerate(subscriptions, start=1):
        lines.append(
            "\n"
            f"<b>#{index} • {escape(subscription.remna_username)}</b>\n"
            f"Срок до: <b>{_fmt_dt(subscription.expire_at, tz)}</b>\n"
            f"Ссылка: <a href=\"{escape(subscription.subscription_url)}\">Открыть</a>\n"
            f"<code>{escape(subscription.subscription_url)}</code>"
        )
    return "\n".join(lines)


def devices_text(
    subscription: UserSubscription,
    total: int,
    devices: list[RemnawaveDevice],
    tz: str,
    limit: int,
) -> str:
    header = (
        f"<b>Устройства ключа {escape(subscription.remna_username)}</b>\n"
        f"Использовано: <b>{total}/{limit}</b>"
    )
    if not devices:
        return header + "\n\nПока нет привязанных устройств."

    lines = [header, ""]
    for idx, device in enumerate(devices, start=1):
        platform = escape(device.platform or "Unknown")
        model = escape(device.device_model or "Unknown")
        created = _fmt_dt(device.created_at, tz)
        lines.append(f"{idx}. {platform} / {model} ({created})")
    return "\n".join(lines)


def invite_text() -> str:
    return (
        "Приглашайте друзей и получайте +5 дней к своей подписке за их первую покупку.\n"
        "Бонус за одного приглашённого начисляется только один раз."
    )


def invite_link_text(link: str) -> str:
    return (
        f"Нажмите на ссылку чтобы скопировать {EMOJI_LINK}\n"
        f"<code>{escape(link)}</code>"
    )


def admin_text() -> str:
    return "<b>Админ-панель HideBroVPN</b>"


def admin_stats_text(stats: dict[str, int]) -> str:
    return (
        "<b>Статистика</b>\n"
        f"Пользователей: <b>{stats['users_total']}</b>\n"
        f"Подписок всего: <b>{stats['subscriptions_total']}</b>\n"
        f"Активных подписок: <b>{stats['active_subscriptions']}</b>\n"
        f"Успешных оплат: <b>{stats['paid_orders']}</b>\n"
        f"Выручка: <b>{stats['total_revenue']} {RUBLE}</b>"
    )


def admin_issue_target_prompt() -> str:
    return "Отправьте ID пользователя или @username, кому нужно выдать бесплатный ключ."


def admin_issue_days_prompt(identifier: str) -> str:
    return f"Получатель: <b>{escape(identifier)}</b>\nВыберите срок выдачи:"


def admin_issue_success_text(target: UserProfile, subscription: UserSubscription, tz: str) -> str:
    label = f"@{target.username}" if target.username else str(target.telegram_id)
    return (
        f"Ключ выдан пользователю <b>{escape(label)}</b>.\n"
        f"До: <b>{_fmt_dt(subscription.expire_at, tz)}</b>\n"
        f"Ссылка: <a href=\"{escape(subscription.subscription_url)}\">Открыть</a>"
    )


def subscriptions_list_text(subscriptions: list[UserSubscription], tz: str) -> str:
    if not subscriptions:
        return "У вас пока нет подписок. Нажмите «Подключиться 🛜», чтобы создать первую."

    lines = ["<b>Мои подписки</b>", "Выберите подписку из списка ниже:"]
    for index, subscription in enumerate(subscriptions, start=1):
        lines.append(
            f"{index}. <code>{escape(subscription.remna_username)}</code> — до <b>{_fmt_dt(subscription.expire_at, tz)}</b>"
        )
    return "\n".join(lines)


def subscription_details_text(subscription: UserSubscription, tz: str) -> str:
    return (
        f"<b>Подписка: {escape(subscription.remna_username)}</b>\n"
        f"Срок до: <b>{_fmt_dt(subscription.expire_at, tz)}</b>\n"
        f"Ссылка: <a href=\"{escape(subscription.subscription_url)}\">Открыть</a>\n"
        f"<code>{escape(subscription.subscription_url)}</code>"
    )
