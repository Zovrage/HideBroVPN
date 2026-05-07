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
        f"ID: <code>{profile.telegram_id}</code>\n\n"
        f"Имя пользователя: {_safe_nickname(profile)}\n\n"
        f"Активные подписки: <b>{active_subscriptions_count}</b>"
    )


def _device_limit_label(limit: int | None) -> str:
    if limit is None:
        return ""
    if limit == 1:
        return "на 1 устройство"
    return f"на {limit} устройства"


def _device_limit_short_label(limit: int | None) -> str:
    if limit is None:
        return ""
    if limit == 1:
        return "1 устройство"
    return f"{limit} устройства"


def connect_device_tier_text() -> str:
    return "Выберите вариант подписки по числу устройств:"


def tariffs_text(*, include_trial: bool, mode: str, device_limit: int | None = None) -> str:
    limit_label = _device_limit_label(device_limit)
    if mode == "extend":
        return "Выберите срок продления для вашей подписки:"

    if include_trial:
        return (
            "Выберите тариф для подключения"
            + (f" {limit_label}" if limit_label else "")
            + ". Пробный тариф доступен только один раз."
        )
    return (
        "Выберите тариф для подключения"
        + (f" {limit_label}" if limit_label else "")
        + ". Пробный тариф уже использован."
    )


def plan_details_text(plan: TariffPlan, *, mode: str, amount_rub: int) -> str:
    action = "Продление" if mode == "extend" else "Подключение"
    return (
        f"<b>{action}</b>\n\n"
        f"Тариф: {escape(plan.title)}\n\n"
        f"Срок: <b>{plan.days} дней</b>\n\n"
        f"Стоимость: <b>{amount_rub} {RUBLE}</b>\n\n"
        "Нажмите «Оплатить», затем кнопку «Оплатить заказ», и после оплаты нажмите «Проверить оплату»."
    )


def payment_created_text(plan: TariffPlan, amount_rub: int, payment_url: str | None) -> str:
    if payment_url:
        return (
            f"Заказ на тариф <b>{escape(plan.title)}</b> создан.\n\n"
            f"Сумма: <b>{amount_rub} {RUBLE}</b>\n\n"
            "Для оплаты используйте кнопку «Оплатить заказ» ниже."
        )
    return (
        f"Заказ на тариф <b>{escape(plan.title)}</b> создан.\n\n"
        "Платежный провайдер не вернул ссылку оплаты. Обратитесь в поддержку."
    )


def payment_pending_text() -> str:
    return "Оплата пока не подтверждена. Если вы уже оплатили, подождите 5-20 секунд и нажмите «Проверить оплату» ещё раз."


def payment_canceled_text() -> str:
    return "Платеж отменен или не завершен. Можно снова нажать «Оплатить» и пройти оплату."


def trial_success_text(subscription: UserSubscription, tz: str) -> str:
    return (
        "Пробный доступ на 3 дня активирован.\n\n"
        f"Ключ: <code>{escape(subscription.remna_username)}</code>\n\n"
        f"Действует до: <b>{_fmt_dt(subscription.expire_at, tz)}</b>"
    )


def subscriptions_text(subscriptions: list[UserSubscription], tz: str) -> str:
    if not subscriptions:
        return "У вас пока нет подписок. Нажмите «Подключиться», чтобы создать первую."

    lines = ["<b>Ваши подписки:</b>"]
    for index, subscription in enumerate(subscriptions, start=1):
        lines.append(
            "\n\n"
            f"<b>#{index} • {escape(subscription.remna_username)}</b>\n\n"
            f"Срок до: <b>{_fmt_dt(subscription.expire_at, tz)}</b>"
        )
    return "\n\n".join(lines)


def devices_text(
    subscription: UserSubscription,
    total: int,
    devices: list[RemnawaveDevice],
    tz: str,
    limit: int,
) -> str:
    header = (
        f"<b>Устройства ключа {escape(subscription.remna_username)}</b>\n\n"
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
    return "\n\n".join(lines)


def invite_text() -> str:
    return (
        "Приглашайте друзей и получайте +5 дней к своей подписке, когда они переходят по вашей ссылке и запускают бота.\n\n"
        "Если у вас нет активной подписки, мы создадим новую на бонусные дни.\n\n"
        "Бонус за одного приглашенного начисляется только один раз."
    )


def invite_link_text(link: str) -> str:
    return (
        f"Нажмите на ссылку чтобы скопировать {EMOJI_LINK}\n\n"
        f"<code>{escape(link)}</code>"
    )


def admin_text() -> str:
    return "<b>Админ-панель HideBroVPN</b>"


def admin_stats_text(stats: dict[str, int]) -> str:
    return (
        "<b>Статистика</b>\n\n"
        f"Пользователей: <b>{stats['users_total']}</b>\n\n"
        f"Подписок всего: <b>{stats['subscriptions_total']}</b>\n\n"
        f"Активных подписок: <b>{stats['active_subscriptions']}</b>\n\n"
        f"Успешных оплат: <b>{stats['paid_orders']}</b>\n\n"
        f"Выручка: <b>{stats['total_revenue']} {RUBLE}</b>"
    )


def admin_issue_target_prompt() -> str:
    return "Отправьте ID пользователя или @username, кому нужно выдать подписку."


def admin_issue_device_prompt(identifier: str) -> str:
    return f"Получатель: <b>{escape(identifier)}</b>\n\nВыберите лимит устройств:"


def admin_issue_months_prompt(identifier: str) -> str:
    return f"Получатель: <b>{escape(identifier)}</b>\n\nВыберите срок выдачи в месяцах:"


def admin_issue_success_text(target: UserProfile, subscription: UserSubscription, tz: str) -> str:
    label = f"@{target.username}" if target.username else str(target.telegram_id)
    limit_label = _device_limit_short_label(subscription.device_limit)
    return (
        f"Подписка выдана пользователю <b>{escape(label)}</b>.\n\n"
        f"До: <b>{_fmt_dt(subscription.expire_at, tz)}</b>\n\n"
        f"Лимит: <b>{limit_label}</b>"
    )


def admin_extend_target_prompt() -> str:
    return "Отправьте ID пользователя или @username, чью подписку нужно продлить."


def admin_extend_choose_subscription_text(target: UserProfile, subscriptions: list[UserSubscription], tz: str) -> str:
    label = f"@{target.username}" if target.username else str(target.telegram_id)
    lines = [f"<b>Пользователь:</b> {escape(label)}", "", "Выберите подписку для продления:"]
    for index, subscription in enumerate(subscriptions, start=1):
        lines.append(
            f"{index}. <code>{escape(subscription.remna_username)}</code> — до <b>{_fmt_dt(subscription.expire_at, tz)}</b>"
        )
    return "\n".join(lines)


def admin_extend_months_prompt(subscription: UserSubscription, tz: str) -> str:
    return (
        f"Подписка: <code>{escape(subscription.remna_username)}</code>\n\n"
        f"Сейчас действует до: <b>{_fmt_dt(subscription.expire_at, tz)}</b>\n\n"
        "Выберите срок продления в месяцах:"
    )


def admin_extend_success_text(target: UserProfile, subscription: UserSubscription, months_label: str, tz: str) -> str:
    label = f"@{target.username}" if target.username else str(target.telegram_id)
    return (
        f"Подписка пользователя <b>{escape(label)}</b> продлена на <b>{months_label}</b>.\n\n"
        f"Ключ: <code>{escape(subscription.remna_username)}</code>\n\n"
        f"Новый срок: <b>{_fmt_dt(subscription.expire_at, tz)}</b>"
    )


def subscriptions_list_text(subscriptions: list[UserSubscription], tz: str) -> str:
    if not subscriptions:
        return "У вас пока нет подписок. Нажмите «Подключиться», чтобы создать первую."

    lines = ["<b>Мои подписки</b>", "Выберите подписку из списка ниже:"]
    for index, subscription in enumerate(subscriptions, start=1):
        lines.append(
            f"{index}. <code>{escape(subscription.remna_username)}</code> — до <b>{_fmt_dt(subscription.expire_at, tz)}</b>"
        )
    return "\n\n".join(lines)


def subscription_details_text(subscription: UserSubscription, tz: str) -> str:
    limit_label = _device_limit_short_label(subscription.device_limit)
    return (
        f"<b>Подписка: {escape(subscription.remna_username)}</b>\n\n"
        f"Действует до: <b>{_fmt_dt(subscription.expire_at, tz)}</b>\n\n"
        f"Лимит: <b>{limit_label}</b>\n\n"
        "Ссылка подписки (нажмите, чтобы скопировать):\n"
        f"<code>{escape(subscription.subscription_url)}</code>"
    )


def subscription_instruction_menu_text(subscription: UserSubscription) -> str:
    return (
        "<b>Инструкция по подключению</b>\n\n"
        f"Ключ: <code>{escape(subscription.remna_username)}</code>\n\n"
        "Выберите ваше устройство:"
    )


def subscription_device_instruction_text(subscription: UserSubscription, device: str) -> str:
    url = escape(subscription.subscription_url)

    if device == "android":
        return (
            "<b>Инструкция: Android</b>\n\n"
            "<b>1.</b> Установите приложение <b>v2rayNG</b> или <b>Happ</b>.\n\n"
            "<b>2.</b> Откройте импорт профиля по ссылке (URL).\n\n"
            "<b>3.</b> Вставьте ссылку подписки:\n"
            f"<code>{url}</code>\n\n"
            "<b>4.</b> Сохраните профиль и нажмите подключение."
        )

    if device == "ios":
        return (
            "<b>Инструкция: iPhone / iPad</b>\n\n"
            "<b>1.</b> Установите приложение <b>Happ</b> или <b>Shadowrocket</b>.\n\n"
            "<b>2.</b> Выберите импорт/добавление по ссылке.\n\n"
            "<b>3.</b> Вставьте ссылку подписки:\n"
            f"<code>{url}</code>\n\n"
            "<b>4.</b> Сохраните профиль и включите VPN."
        )

    if device == "windows":
        return (
            "<b>Инструкция: Windows</b>\n\n"
            "<b>1.</b> Установите <b>v2rayN</b> или <b>Happ</b>.\n\n"
            "<b>2.</b> Выберите импорт из буфера / импорт по URL.\n\n"
            "<b>3.</b> Вставьте ссылку подписки:\n"
            f"<code>{url}</code>\n\n"
            "<b>4.</b> Выберите сервер и нажмите подключение."
        )

    if device == "macos":
        return (
            "<b>Инструкция: macOS</b>\n\n"
            "<b>1.</b> Установите <b>Happ</b> или <b>FoXray</b>.\n\n"
            "<b>2.</b> Добавьте профиль через импорт по URL.\n\n"
            "<b>3.</b> Вставьте ссылку подписки:\n"
            f"<code>{url}</code>\n\n"
            "<b>4.</b> Сохраните профиль и включите подключение."
        )

    return (
        "<b>Инструкция по подключению</b>\n\n"
        "Откройте импорт по ссылке в вашем приложении и вставьте:\n"
        f"<code>{url}</code>"
    )


def admin_broadcast_prompt() -> str:
    return (
        "Отправьте одно сообщение для рассылки.\n\n"
        "Можно текст, фото, видео или медиа с подписью."
    )


def admin_broadcast_invalid_text() -> str:
    return "Поддерживается текст, фото, видео и подписи к ним. Отправьте сообщение ещё раз."


def admin_broadcast_result_text(*, total: int, success: int, failed: int) -> str:
    return (
        "<b>Рассылка завершена</b>\n\n"
        f"Всего получателей: <b>{total}</b>\n\n"
        f"Успешно: <b>{success}</b>\n\n"
        f"Ошибок: <b>{failed}</b>"
    )
