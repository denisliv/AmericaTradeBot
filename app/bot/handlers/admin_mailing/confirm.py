"""Confirm / cancel mailing handler — triggers the broadcaster."""

import logging

from aiogram import F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from psycopg_pool import AsyncConnectionPool

from app.bot.handlers.admin_mailing._common import (
    mailing_payload_from_state,
    make_admin_router,
)
from app.bot.states.admin_mailing import FSMAdminMailing
from app.infrastructure.database.db import (
    admin_mailing_delete_table,
    admin_mailing_prepare_for_broadcast,
)
from app.infrastructure.services.admin_mailing_sender import AdminMailingSender

logger = logging.getLogger(__name__)

router = make_admin_router()


@router.callback_query(
    F.data.in_({"confirm_sender", "cancel_sender"}),
    StateFilter(FSMAdminMailing.confirm_send),
)
async def sender_decide(
    callback: CallbackQuery,
    state: FSMContext,
    db_pool: AsyncConnectionPool,
) -> None:
    data = await state.get_data()
    sender = AdminMailingSender(callback.bot)

    if callback.data == "confirm_sender":
        await callback.message.edit_text("Начинаю рассылку", reply_markup=None)
        try:
            try:
                payload = mailing_payload_from_state(data)
            except ValueError as exc:
                await callback.message.answer(f"Не могу начать рассылку: {exc}")
                return
            async with db_pool.connection() as conn:
                await conn.set_autocommit(True)
                await admin_mailing_prepare_for_broadcast(conn)
            count = await sender.broadcaster(
                db_pool,
                chat_id=payload["chat_id"],
                message_id=payload["message_id"],
                media_items=payload["media_items"],
                is_album=payload["is_album"],
                text_button=payload["text_button"],
                url_button=payload["url_button"],
                button_message_text=payload["button_message_text"],
            )
            await callback.message.answer(
                f"Успешно разослали рекламное сообщение [{count}] пользователям"
            )
        finally:
            try:
                async with db_pool.connection() as conn:
                    await conn.set_autocommit(True)
                    await admin_mailing_delete_table(conn)
            except Exception as e:
                logger.warning("admin_mailing_delete_table: %s", e, exc_info=True)

    elif callback.data == "cancel_sender":
        await callback.message.edit_text("Отменил рассылку", reply_markup=None)

    await state.clear()
    await callback.answer()
