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
    admin_issue_days_keyboard,
    admin_issue_prompt_keyboard,
    admin_menu_keyboard,
    main_menu_keyboard,
)
from app.bot.states import AdminIssueState
from app.bot.texts import (
    admin_broadcast_invalid_text,
    admin_broadcast_prompt,
    admin_broadcast_result_text,
    admin_issue_days_prompt,
    admin_issue_success_text,
    admin_issue_target_prompt,
    admin_stats_text,
    admin_text,
    main_menu_text,
)
from app.bot.ui import replace_callback_message
from app.core.config import Settings
from app.services.business import BusinessService
from app.services.errors import NotFoundError, RemnawaveAPIError

router = Router(name="admin")


def _is_admin(settings: Settings, telegram_id: int) -> bool:
    return telegram_id in settings.admin_ids


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
        await state.set_state(AdminIssueState.waiting_target)
        await replace_callback_message(
            callback,
            text=admin_issue_target_prompt(),
            reply_markup=admin_issue_prompt_keyboard(),
        )
        return

    if callback_data.action == "broadcast":
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
    await message.answer(
        admin_issue_days_prompt(identifier),
        reply_markup=admin_issue_days_keyboard(),
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
async def admin_issue_days_callback(
    callback: CallbackQuery,
    callback_data: AdminIssueCb,
    state: FSMContext,
    business: BusinessService,
    settings: Settings,
) -> None:
    if not _is_admin(settings, callback.from_user.id):
        await callback.answer()
        return

    if callback_data.action != "days":
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
        days = int(callback_data.value)
    except ValueError:
        await replace_callback_message(
            callback,
            text="Неверный срок. Попробуйте ещё раз.",
            reply_markup=admin_menu_keyboard(),
        )
        return

    try:
        target, subscription = await business.admin_issue_subscription(
            admin_telegram_id=callback.from_user.id,
            target_identifier=target_identifier,
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

    await replace_callback_message(
        callback,
        text=admin_issue_success_text(target, subscription, settings.timezone),
        reply_markup=admin_menu_keyboard(),
    )

    await callback.bot.send_message(
        chat_id=target.telegram_id,
        text=(
            "Администратор выдал вам бесплатный ключ.\n"
            f"Ключ: <code>{subscription.remna_username}</code>\n"
            f"Действует до: <b>{subscription.expire_at.astimezone(ZoneInfo(settings.timezone)).strftime('%d.%m.%Y %H:%M')}</b>\n"
            f"Ссылка: <a href=\"{subscription.subscription_url}\">Подключиться</a>"
        ),
        reply_markup=main_menu_keyboard(support_username=settings.support_username),
        disable_web_page_preview=True,
    )
