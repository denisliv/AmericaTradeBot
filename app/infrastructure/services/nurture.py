"""Прогревочная цепочка рассылок (по диаграмме Miro).

График от регистрации пользователя (при оставленной заявке сдвигается на +3 дня):
шаг 1 - через 60 минут, далее по посту каждый день (дни 1-7) в 19:00 по таймзоне
бота; подборки дня 3 разнесены: кроссоверы в 19:00, седаны в 21:00.
Шаги 7-9 (Telegram/Instagram/TikTok) повторяются каждые 30 дней бессрочно.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.enums import ButtonStyle
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from psycopg_pool import AsyncConnectionPool

from app.bot.keyboards.keyboards_inline import create_choice_keyboard
from app.infrastructure.database.nurture import (
    get_active_nurture_rows,
    set_nurture_last_step,
)
from app.infrastructure.paths import WARM_UP_POSTS_IMG_DIR
from app.infrastructure.services.car_media import make_media_group
from app.infrastructure.services.safe_send import SendStatus, send_to_user_safely
from app.infrastructure.services.salesdata import get_random_car_with_images
from app.lexicon.lexicon_ru import (
    LEXICON_ASSISTED_GALLERY_RU,
    LEXICON_NEWSLETTER_RU,
    LEXICON_NURTURE_RU,
    LEXICON_RU,
)

logger = logging.getLogger(__name__)

# Картинки прогревочных постов; текст поста идет подписью под картинкой
WHY_AMERICATRADE_IMG = WARM_UP_POSTS_IMG_DIR / "why_americatrade.png"
TOP_MYTHS_IMG = WARM_UP_POSTS_IMG_DIR / "top_myths.png"
TOP_CARS_IMG = {
    "suv": (WARM_UP_POSTS_IMG_DIR / "top_suv.png", "кроссоверов"),
    "sedan": (WARM_UP_POSTS_IMG_DIR / "top_sedan.png", "седанов"),
}

# День отправки шага (от старта цепочки); шаг 1 - через 60 минут.
# Шаги 4 и 5 - подборки кроссоверов и седанов в один день, но в разное время
STEP_OFFSET_DAYS = {2: 1, 3: 2, 4: 3, 5: 3, 6: 4, 7: 5, 8: 6, 9: 7}
FIRST_STEP_DELAY = timedelta(minutes=60)
SEND_HOUR = 19
STEP_SEND_HOUR = {5: 21}  # седаны уходят позже кроссоверов
MONTHLY_REPEAT_DAYS = 30
_SOCIAL_STEPS = (7, 8, 9)
_LAST_BASE_STEP = 9

TELEGRAM_CHANNEL_URL = "https://t.me/americatradeby"
INSTAGRAM_URL = "https://www.instagram.com/americatrade.by"
TIKTOK_URL = "https://www.tiktok.com/@americatrade"


def resolve_step(last_step: int) -> tuple[int, int]:
    """Возвращает (следующий шаг цепочки, контентный шаг 1..9).

    После шага 9 цепочка продолжается месячными повторами шагов 7-9:
    10 = повтор шага 7, 11 = повтор шага 8, 12 = повтор шага 9, 13 = шаг 7 и т.д.
    """
    next_step = last_step + 1
    if next_step <= _LAST_BASE_STEP:
        return next_step, next_step
    return next_step, _SOCIAL_STEPS[(next_step - _LAST_BASE_STEP - 1) % 3]


def due_at(
    started_at: datetime,
    shift_days: int,
    step: int,
    tz: ZoneInfo,
) -> datetime:
    """Момент отправки шага: смещение заявки двигает весь оставшийся график."""
    base = (started_at + timedelta(days=shift_days)).astimezone(tz)
    if step == 1:
        return base + FIRST_STEP_DELAY

    if step <= _LAST_BASE_STEP:
        offset_days = STEP_OFFSET_DAYS[step]
        hour = STEP_SEND_HOUR.get(step, SEND_HOUR)
    else:
        content_step = _SOCIAL_STEPS[(step - _LAST_BASE_STEP - 1) % 3]
        cycle = (step - _LAST_BASE_STEP - 1) // 3 + 1
        offset_days = STEP_OFFSET_DAYS[content_step] + MONTHLY_REPEAT_DAYS * cycle
        hour = SEND_HOUR

    return (base + timedelta(days=offset_days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )


def _consultation_keyboard() -> InlineKeyboardMarkup:
    # Отдельный callback: лид из рассылки помечается в Bitrix источником "рассылка"
    return create_choice_keyboard(
        ("application_from_nurture", "free_consultation_button", ButtonStyle.SUCCESS),
        width=1,
    )


def _url_keyboard(text: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, url=url, style=ButtonStyle.SUCCESS)]
        ]
    )


async def _send_photo_post(
    bot: Bot,
    user_id: int,
    image: Path,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Пост с картинкой и текстом-подписью; без картинки (runtime-файл) - просто текст."""
    if image.exists():
        await bot.send_photo(
            chat_id=user_id,
            photo=FSInputFile(image),
            caption=text,
            reply_markup=reply_markup,
        )
    else:
        logger.warning("Nurture post image not found: %s", image)
        await bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup)


async def _send_text_step(bot: Bot, user_id: int, text: str) -> None:
    await bot.send_message(
        chat_id=user_id, text=text, reply_markup=_consultation_keyboard()
    )


async def _send_top_car_post(
    bot: Bot, user_id: int, first_name: str, body_group: str
) -> None:
    """Пост-подборка одного кузова: картинка-заголовок, авто из CSV, кнопки."""
    car = await get_random_car_with_images(body_group)
    if not car:
        # Редкий случай (нет подходящих лотов с фото): пост пропускается
        logger.warning("Nurture top cars: no %s with images found", body_group)
        return

    image, category = TOP_CARS_IMG[body_group]
    await _send_photo_post(
        bot,
        user_id,
        image,
        LEXICON_ASSISTED_GALLERY_RU["top_header"](category),
    )
    media_group = await make_media_group(car, first_name, 1)
    await bot.send_media_group(chat_id=user_id, media=media_group)
    await bot.send_message(
        chat_id=user_id,
        text="👇 Нажмите кнопку, чтобы получить расчёт цены под ключ в РБ:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📋 Получить детальный расчет Авто № 1",
                        callback_data=(
                            f"Лот №: {car[0]['Lot number']}"
                            f"-{car[0]['Make']}-{car[0]['Model Detail']}"
                        ),
                        style=ButtonStyle.PRIMARY,
                    )
                ]
            ]
        ),
    )
    await asyncio.sleep(0.2)
    await bot.send_message(
        chat_id=user_id,
        text=LEXICON_NEWSLETTER_RU["car_selection_text"],
        reply_markup=_consultation_keyboard(),
    )


async def send_nurture_step(
    bot: Bot, user_id: int, first_name: str, content_step: int
) -> None:
    if content_step == 1:
        await _send_photo_post(
            bot,
            user_id,
            WHY_AMERICATRADE_IMG,
            LEXICON_RU["why_americatrade_text"],
            reply_markup=_consultation_keyboard(),
        )
    elif content_step == 2:
        await _send_photo_post(
            bot,
            user_id,
            TOP_MYTHS_IMG,
            LEXICON_NURTURE_RU["myths_text"],
            reply_markup=_consultation_keyboard(),
        )
    elif content_step == 3:
        await _send_text_step(bot, user_id, LEXICON_NURTURE_RU["client_story_text"])
    elif content_step == 4:
        await _send_top_car_post(bot, user_id, first_name, "suv")
    elif content_step == 5:
        await _send_top_car_post(bot, user_id, first_name, "sedan")
    elif content_step == 6:
        await _send_text_step(bot, user_id, LEXICON_NURTURE_RU["thinking_text"])
    elif content_step == 7:
        await bot.send_message(
            chat_id=user_id,
            text=LEXICON_NURTURE_RU["telegram_text"],
            reply_markup=_url_keyboard(
                LEXICON_NURTURE_RU["go_telegram_button"], TELEGRAM_CHANNEL_URL
            ),
        )
    elif content_step == 8:
        await bot.send_message(
            chat_id=user_id,
            text=LEXICON_NURTURE_RU["instagram_text"],
            reply_markup=_url_keyboard(
                LEXICON_NURTURE_RU["go_instagram_button"], INSTAGRAM_URL
            ),
        )
    elif content_step == 9:
        await bot.send_message(
            chat_id=user_id,
            text=LEXICON_NURTURE_RU["tiktok_text"],
            reply_markup=_url_keyboard(
                LEXICON_NURTURE_RU["go_tiktok_button"], TIKTOK_URL
            ),
        )


async def send_due_nurture_messages(
    bot: Bot,
    db_pool: AsyncConnectionPool,
    timezone_name: str,
) -> None:
    """Отправляет каждому пользователю не более одного назревшего шага за запуск."""
    tz = ZoneInfo(timezone_name)
    now = datetime.now(tz)

    async with db_pool.connection() as conn:
        # Каждое обновление last_step коммитится сразу: иначе падение прогона
        # откатило бы отметки об уже отправленных сообщениях и вызвало дубли
        await conn.set_autocommit(True)
        rows = await get_active_nurture_rows(conn)

        sent = 0
        for row in rows:
            step, content_step = resolve_step(row.last_step)
            if due_at(row.started_at, row.shift_days, step, tz) > now:
                continue

            try:
                status, detail = await send_to_user_safely(
                    partial(
                        send_nurture_step,
                        bot,
                        row.user_id,
                        row.name or "Пользователь",
                        content_step,
                    ),
                    conn=conn,
                    user_id=row.user_id,
                )
            except TelegramRetryAfter as e:
                # Флуд-контроль Telegram: прекращаем прогон, шаги останутся
                # назревшими и уйдут в следующем запуске джоба
                logger.warning(
                    "Nurture: rate limited (retry after %s s), stopping this run",
                    e.retry_after,
                )
                break

            if status is SendStatus.BLOCKED:
                continue
            if status is SendStatus.ERROR:
                # Шаг помечается обработанным, чтобы не зациклиться на битом контенте
                logger.warning(
                    "Nurture: send failed for user %d, step skipped: %s",
                    row.user_id,
                    detail,
                )

            await set_nurture_last_step(conn, user_id=row.user_id, last_step=step)
            sent += 1
            await asyncio.sleep(0.2)

    if sent:
        logger.info("Nurture: sent %d messages", sent)
