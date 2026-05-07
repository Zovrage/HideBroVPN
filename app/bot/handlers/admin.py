from __future__ import annotations

import asyncio
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import AdminIssueCb, AdminMenuCb
from app.bot.keyboards import (
    admin_extend_months_keyboard,
    admin_extend_subscriptions_keyboard,
    admin_issue_months_keyboard,
    admin_issue_device_keyboard,
    admin_issue_prompt_keyboard,
    admin_menu_keyboard,
    main_menu_keyboard,
)
from app.bot.states import AdminIssueState
from app.bot.texts import (
    admin_extend_choose_subscription_text,
    admin_extend_months_prompt,
    admin_extend_success_text,
    admin_extend_target_prompt,
    admin_broadcast_invalid_text,
    admin_broadcast_prompt,
    admin_broadcast_result_text,
    admin_issue_device_prompt,
    admin_issue_months_prompt,
    admin_issue_success_text,
    admin_issue_target_prompt,
    admin_stats_text,
    admin_text,
    main_menu_text,
)
from app.bot.ui import replace_callback_message
from app.core.config import Settings
from app.domain.plans import PLANS
from app.services.business import BusinessService
from app.services.errors import NotFoundError, RemnawaveAPIError

router = Router(name="admin")


def _is_admin(settings: Settings, telegram_id: int) -> bool:
    return telegram_id in settings.admin_ids


def _admin_month_to_days_map() -> dict[int, int]:
    result: dict[int, int] = {}
    for code, plan in PLANS.items():
        if plan.is_trial:
            continue
        if not code.startswith("m"):
            continue
        raw = code[1:]
        if not raw.isdigit():
            continue
        result[int(raw)] = plan.days
    return result


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


ADMIN_MONTH_TO_DAYS = _admin_month_to_days_map()


async def _render_user_main(
    *,
    business: BusinessService,
    settings: Settings,
    telegram_id: int,
):
    profile = await business.get_profile_by_telegram_id(telegram_id)
    if not profile:
        return "Профиль ещё не создан. Отправьте /start.", main_menu_keyboard(support_username=settings.support_username)

    active_count = await business.count_active_subscriptions(profile.id)
    return (
        main_menu_text(profile, active_count),
        main_menu_keyboard(support_username=settings.support_username),
    )


@router.message(Command("admin"))
async def admin_command(
    message: Message,
    state: FSMContext,
    settings: Settings,
) -> None:
    if not _is_admin(settings, message.from_user.id):
        return

    await state.clear()
    await message.answer(admin_text(), reply_markup=admin_menu_keyboard())


@router.callback_query(AdminMenuCb.filter())
async def admin_menu_callback(
    callback: CallbackQuery,
    callback_data: AdminMenuCb,
    state: FSMContext,
    business: BusinessService,
    settings: Settings,
) -> None:
    if not _is_admin(settings, callback.from_user.id):
        await callback.answer()
        return

    if callback_data.action == "stats":
        stats = await business.get_admin_stats()
        await replace_callback_message(
            callback,
            text=admin_stats_text(stats),
            reply_markup=admin_menu_keyboard(),
        )
        return

    if callback_data.action == "issue":
        await state.clear()
        await state.set_state(AdminIssueState.waiting_target)
        await replace_callback_message(
            callback,
            text=admin_issue_target_prompt(),
            reply_markup=admin_issue_prompt_keyboard(),
        )
        return

    if callback_data.action == "extend":
        await state.clear()
        await state.set_state(AdminIssueState.waiting_extend_target)
        await replace_callback_message(
            callback,
            text=admin_extend_target_prompt(),
            reply_markup=admin_issue_prompt_keyboard(),
        )
        return

    if callback_data.action == "broadcast":
        await state.clear()
        await state.set_state(AdminIssueState.waiting_broadcast)
        await replace_callback_message(
            callback,
            text=admin_broadcast_prompt(),
            reply_markup=admin_issue_prompt_keyboard(),
        )
        return

    if callback_data.action == "main":
        await state.clear()
        text, keyboard = await _render_user_main(
            business=business,
            settings=settings,
            telegram_id=callback.from_user.id,
        )
        await replace_callback_message(callback, text=text, reply_markup=keyboard)
        return

    if callback_data.action == "back":
        await state.clear()
        await replace_callback_message(
            callback,
            text=admin_text(),
            reply_markup=admin_menu_keyboard(),
        )


@router.message(AdminIssueState.waiting_target)
async def admin_issue_target_input(
    message: Message,
    state: FSMContext,
    business: BusinessService,
    settings: Settings,
) -> None:
    if not _is_admin(settings, message.from_user.id):
        return

    identifier = (message.text or "").strip()
    if not identifier:
        await message.answer("Отправьте ID пользователя или @username.")
        return

    target = await business.find_profile_by_identifier(identifier)
    if not target:
        await message.answer("Пользователь не найден. Проверьте ID/username и отправьте ещё раз.")
        return

    await state.update_data(target_identifier=identifier)
    await state.set_state(AdminIssueState.waiting_device_limit)
    await message.answer(
        admin_issue_device_prompt(identifier),
        reply_markup=admin_issue_device_keyboard(),
    )


@router.message(AdminIssueState.waiting_extend_target)
async def admin_extend_target_input(
    message: Message,
    state: FSMContext,
    business: BusinessService,
    settings: Settings,
) -> None:
    if not _is_admin(settings, message.from_user.id):
        return

    identifier = (message.text or "").strip()
    if not identifier:
        await message.answer("Отправьте ID пользователя или @username.")
        return

    target = await business.find_profile_by_identifier(identifier)
    if not target:
        await message.answer("Пользователь не найден. Проверьте ID/username и отправьте ещё раз.")
        return

    subscriptions = await business.list_user_subscriptions(target.id, refresh_remote=False)
    if not subscriptions:
        await state.clear()
        await message.answer(
            "У пользователя нет подписок для продления.",
            reply_markup=admin_menu_keyboard(),
        )
        return

    await state.update_data(extend_target_user_id=target.id)
    await state.set_state(AdminIssueState.waiting_extend_subscription)
    await message.answer(
        admin_extend_choose_subscription_text(target, subscriptions, settings.timezone),
        reply_markup=admin_extend_subscriptions_keyboard(subscriptions),
    )


@router.message(AdminIssueState.waiting_broadcast)
async def admin_broadcast_input(
    message: Message,
    state: FSMContext,
    business: BusinessService,
    settings: Settings,
) -> None:
    if not _is_admin(settings, message.from_user.id):
        return

    has_supported_content = bool(
        message.text or message.caption or message.photo or message.video
    )
    if not has_supported_content:
        await message.answer(
            admin_broadcast_invalid_text(),
            reply_markup=admin_issue_prompt_keyboard(),
        )
        return

    recipients = await business.list_all_telegram_ids()
    total = len(recipients)
    if total == 0:
        await state.clear()
        await message.answer(
            admin_broadcast_result_text(total=0, success=0, failed=0),
            reply_markup=admin_menu_keyboard(),
        )
        return

    progress_message = await message.answer("Запускаю рассылку...")
    success = 0
    failed = 0

    for telegram_id in recipients:
        while True:
            try:
                await message.send_copy(chat_id=telegram_id)
                success += 1
                break
            except TelegramRetryAfter as exc:
                await asyncio.sleep(float(exc.retry_after))
            except (TelegramForbiddenError, TelegramBadRequest):
                failed += 1
                break
            except Exception:
                failed += 1
                break

    await state.clear()
    await progress_message.edit_text(
        admin_broadcast_result_text(total=total, success=success, failed=failed),
        reply_markup=admin_menu_keyboard(),
    )


@router.callback_query(AdminIssueCb.filter())
async def admin_issue_months_callback(
    callback: CallbackQuery,
    callback_data: AdminIssueCb,
    state: FSMContext,
    business: BusinessService,
    settings: Settings,
) -> None:
    if not _is_admin(settings, callback.from_user.id):
        await callback.answer()
        return

    if callback_data.action == "limit":
        data = await state.get_data()
        target_identifier = data.get("target_identifier")
        if not target_identifier:
            await replace_callback_message(
                callback,
                text="Сначала укажите пользователя (ID/username).",
                reply_markup=admin_menu_keyboard(),
            )
            return

        try:
            device_limit = int(callback_data.value)
        except ValueError:
            await replace_callback_message(
                callback,
                text="Неверный лимит устройств. Попробуйте ещё раз.",
                reply_markup=admin_menu_keyboard(),
            )
            return

        await state.update_data(device_limit=device_limit)
        await state.set_state(AdminIssueState.waiting_issue_months)
        await replace_callback_message(
            callback,
            text=admin_issue_months_prompt(target_identifier),
            reply_markup=admin_issue_months_keyboard(),
        )
        return

    if callback_data.action == "extend_pick":
        data = await state.get_data()
        target_user_id = data.get("extend_target_user_id")
        if target_user_id is None:
            await replace_callback_message(
                callback,
                text="Сначала укажите пользователя для продления подписки.",
                reply_markup=admin_menu_keyboard(),
            )
            return

        try:
            subscription_id = int(callback_data.value)
        except ValueError:
            await replace_callback_message(
                callback,
                text="Не удалось определить подписку. Попробуйте ещё раз.",
                reply_markup=admin_menu_keyboard(),
            )
            return

        try:
            subscription = await business.get_user_subscription(
                user_id=int(target_user_id),
                subscription_id=subscription_id,
                refresh_remote=False,
            )
        except NotFoundError as exc:
            await replace_callback_message(
                callback,
                text=str(exc),
                reply_markup=admin_menu_keyboard(),
            )
            return

        await state.update_data(extend_subscription_id=subscription.id)
        await state.set_state(AdminIssueState.waiting_extend_months)
        await replace_callback_message(
            callback,
            text=admin_extend_months_prompt(subscription, settings.timezone),
            reply_markup=admin_extend_months_keyboard(),
        )
        return

    if callback_data.action == "extend_months":
        data = await state.get_data()
        target_user_id = data.get("extend_target_user_id")
        subscription_id = data.get("extend_subscription_id")
        if target_user_id is None or subscription_id is None:
            await replace_callback_message(
                callback,
                text="Сначала выберите пользователя и подписку для продления.",
                reply_markup=admin_menu_keyboard(),
            )
            return

        try:
            months = int(callback_data.value)
        except ValueError:
            await replace_callback_message(
                callback,
                text="Неверный срок. Попробуйте ещё раз.",
                reply_markup=admin_menu_keyboard(),
            )
            return

        days = ADMIN_MONTH_TO_DAYS.get(months)
        if days is None:
            await replace_callback_message(
                callback,
                text="Неверный срок продления. Выберите вариант из списка.",
                reply_markup=admin_menu_keyboard(),
            )
            return

        try:
            target, subscription = await business.admin_extend_subscription(
                admin_telegram_id=callback.from_user.id,
                target_user_id=int(target_user_id),
                subscription_id=int(subscription_id),
                days=days,
            )
        except (NotFoundError, RemnawaveAPIError) as exc:
            await replace_callback_message(
                callback,
                text=str(exc),
                reply_markup=admin_menu_keyboard(),
            )
            return

        await state.clear()
        months_label = _month_label(months)

        await replace_callback_message(
            callback,
            text=admin_extend_success_text(target, subscription, months_label, settings.timezone),
            reply_markup=admin_menu_keyboard(),
        )

        await callback.bot.send_message(
            chat_id=target.telegram_id,
            text=(
                f"Администратор продлил вашу подписку на <b>{months_label}</b>.\n\n"
                f"Ключ: <code>{subscription.remna_username}</code>\n\n"
                f"Действует до: <b>{subscription.expire_at.astimezone(ZoneInfo(settings.timezone)).strftime('%d.%m.%Y %H:%M')}</b>\n\n"
                f"Лимит: <b>{subscription.device_limit} устройства</b>\n\n"
            ),
            reply_markup=main_menu_keyboard(support_username=settings.support_username),
            disable_web_page_preview=True,
        )
        return

    if callback_data.action != "issue_months":
        await callback.answer()
        return

    data = await state.get_data()
    target_identifier = data.get("target_identifier")
    if not target_identifier:
        await replace_callback_message(
            callback,
            text="Сначала укажите пользователя (ID/username).",
            reply_markup=admin_menu_keyboard(),
        )
        return

    try:
        months = int(callback_data.value)
    except ValueError:
        await replace_callback_message(
            callback,
            text="Неверный срок. Попробуйте ещё раз.",
            reply_markup=admin_menu_keyboard(),
        )
        return
    days = ADMIN_MONTH_TO_DAYS.get(months)
    if days is None:
        await replace_callback_message(
            callback,
            text="Неверный срок выдачи. Выберите вариант из списка.",
            reply_markup=admin_menu_keyboard(),
        )
        return

    device_limit = data.get("device_limit")
    if device_limit is None:
        await replace_callback_message(
            callback,
            text="Сначала выберите лимит устройств.",
            reply_markup=admin_menu_keyboard(),
        )
        return

    try:
        target, subscription = await business.admin_issue_subscription(
            admin_telegram_id=callback.from_user.id,
            target_identifier=target_identifier,
            days=days,
            device_limit=int(device_limit),
        )
    except (NotFoundError, RemnawaveAPIError) as exc:
        await replace_callback_message(
            callback,
            text=str(exc),
            reply_markup=admin_menu_keyboard(),
        )
        return

    await state.clear()
    months_label = _month_label(months)

    await replace_callback_message(
        callback,
        text=admin_issue_success_text(target, subscription, settings.timezone),
        reply_markup=admin_menu_keyboard(),
    )

    await callback.bot.send_message(
        chat_id=target.telegram_id,
        text=(
            f"Администратор выдал вам подписку на <b>{months_label}</b>.\n\n"
            f"Ключ: <code>{subscription.remna_username}</code>\n\n"
            f"Действует до: <b>{subscription.expire_at.astimezone(ZoneInfo(settings.timezone)).strftime('%d.%m.%Y %H:%M')}</b>\n\n"
            f"Лимит: <b>{subscription.device_limit} устройства</b>\n\n"
        ),
        reply_markup=main_menu_keyboard(support_username=settings.support_username),
        disable_web_page_preview=True,
    )

