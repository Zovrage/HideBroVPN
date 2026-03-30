from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message


async def safe_delete_message(message: Message | None) -> None:
    if message is None:
        return
    try:
        await message.delete()
    except TelegramBadRequest:
        return


async def replace_callback_message(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message:
    await callback.answer()
    await safe_delete_message(callback.message)
    return await callback.bot.send_message(
        chat_id=callback.from_user.id,
        text=text,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )
