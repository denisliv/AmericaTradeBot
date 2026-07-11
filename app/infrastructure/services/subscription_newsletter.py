import asyncio
import logging
from typing import List, Tuple

from aiogram import Bot
from aiogram.enums import ButtonStyle
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from psycopg_pool import AsyncConnectionPool

from app.infrastructure.database.selections import get_user_subscriptions
from app.infrastructure.database.users import get_active_subscribers
from app.infrastructure.services.car_media import make_media_group
from app.infrastructure.services.safe_send import SendStatus, send_to_user_safely
from app.infrastructure.services.salesdata import get_data
from app.lexicon.lexicon_ru import LEXICON_BUTTONS_RU, LEXICON_NEWSLETTER_RU, LEXICON_RU

logger = logging.getLogger(__name__)


async def send_self_selection_cars(
    bot: Bot,
    subscriber,
    cars_data: List[Tuple[dict, List[str]]],
) -> int:
    """Отправляет автомобили для self selection подписки с фото и кнопками"""
    if not cars_data:
        await bot.send_message(
            chat_id=subscriber.user_id,
            text=f"{LEXICON_RU['nothing_found_text']}",
        )
        return 0

    messages_sent = 0
    any_sent = False

    # Под каждую медиагруппу — сообщение "👇 Актуальные варианты:" с одной
    # кнопкой выбора авто. Media group не поддерживает reply_markup,
    # поэтому кнопка идёт отдельным сообщением сразу под альбомом.
    for i, (car, images) in enumerate(cars_data, 1):
        try:
            if not images:
                logger.warning(f"No images for car {i}, skipping")
                continue

            media_group = await make_media_group(
                (car, images), subscriber.name or "Пользователь", i
            )

            await bot.send_media_group(chat_id=subscriber.user_id, media=media_group)
            messages_sent += 1

            await bot.send_message(
                chat_id=subscriber.user_id,
                text="👇 Нажмите кнопку, чтобы получить расчёт цены под ключ в РБ:",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=f"Авто № {i}",
                                callback_data=(
                                    f"Лот №: {car.get('Lot number', 'N/A')}"
                                    f"-{car.get('Make', 'N/A')}"
                                    f"-{car.get('Model Detail', 'N/A')}"
                                ),
                                style=ButtonStyle.PRIMARY,
                            )
                        ]
                    ]
                ),
            )
            messages_sent += 1
            any_sent = True
            await asyncio.sleep(0.5)  # пауза между автомобилями

        except (TelegramForbiddenError, TelegramRetryAfter):
            # Блокировку и flood-limit обрабатывает уровень отправки пользователю
            raise
        except Exception as e:
            logger.error(f"Error sending car {i} to user {subscriber.user_id}: {e}")
            logger.error(f"Car data: {car}")
            logger.error(f"Images: {images}")
            continue

    # Финальное CTA-сообщение с зелёной кнопкой заявки на подбор
    if any_sent:
        await bot.send_message(
            chat_id=subscriber.user_id,
            text=LEXICON_NEWSLETTER_RU["car_selection_text"],
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=LEXICON_BUTTONS_RU["application_for_selection_button"],
                            callback_data="application_for_selection_button",
                            style=ButtonStyle.SUCCESS,
                        )
                    ]
                ]
            ),
        )
        messages_sent += 1

    return messages_sent


async def get_cars_for_self_selection(
    subscription,
) -> List[Tuple[dict, List[str]]]:
    """Получает автомобили для self selection подписки"""
    user_dict = {
        "brand": subscription.brand,
        "model": subscription.model,
        "year": subscription.year,
        "odometer": subscription.odometer,
        "auction_status": subscription.auction_status,
    }

    cars_data = await get_data(user_dict, count=3)
    return cars_data


class NewsletterQueue:
    """Очередь для рассылки с поддержкой retry и rate limiting"""

    def __init__(
        self,
        max_retries: int = 3,
        batch_size: int = 30,
        delay_between_batches: float = 1.0,
    ):
        self.max_retries = max_retries
        self.batch_size = batch_size
        self.delay_between_batches = delay_between_batches
        self.queue = asyncio.Queue()
        self.retry_queue = asyncio.Queue()
        self._total_items = 0

    async def add_subscriber(self, subscriber) -> None:
        """Добавляет подписчика в очередь"""
        await self.queue.put((subscriber, 0))  # (subscriber, retry_count)
        self._total_items += 1

    async def add_retry(self, subscriber, retry_count: int) -> None:
        """Добавляет подписчика в очередь для повторной отправки"""
        if retry_count < self.max_retries:
            await self.retry_queue.put((subscriber, retry_count + 1))
            self._total_items += 1

    async def get_batch(self) -> List[Tuple]:
        """Получает батч подписчиков для отправки"""
        batch = []
        while len(batch) < self.batch_size and self._total_items > 0:
            try:
                # Сначала пытаемся получить из основной очереди
                if not self.queue.empty():
                    item = await asyncio.wait_for(self.queue.get(), timeout=0.1)
                    batch.append(item)
                    self._total_items -= 1
                # Если основная очередь пуста, берем из retry очереди
                elif not self.retry_queue.empty():
                    item = await asyncio.wait_for(self.retry_queue.get(), timeout=0.1)
                    batch.append(item)
                    self._total_items -= 1
                else:
                    break
            except asyncio.TimeoutError:
                break
        return batch

    def is_empty(self) -> bool:
        """Проверяет, пуста ли очередь"""
        return self._total_items == 0


async def process_newsletter_batch(
    bot: Bot,
    conn,
    queue: NewsletterQueue,
    batch: List[Tuple],
) -> None:
    """Параллельно обрабатывает батч подписчиков и планирует retry."""
    results = await asyncio.gather(
        *(send_newsletter_to_user(bot, subscriber, conn) for subscriber, _ in batch),
        return_exceptions=True,
    )
    for (subscriber, retry_count), result in zip(batch, results, strict=True):
        if isinstance(result, Exception):
            await queue.add_retry(subscriber, retry_count)
            logger.warning(
                "Unexpected exception for user %s: %s",
                subscriber.user_id,
                result,
            )
            continue
        status, error_msg = result
        if status is SendStatus.OK:
            logger.debug("Newsletter sent to user %s", subscriber.user_id)
            continue
        if status is SendStatus.BLOCKED:
            logger.warning("User %s blocked bot or deactivated", subscriber.user_id)
            continue
        await queue.add_retry(subscriber, retry_count)
        logger.warning(
            "Failed to send newsletter to user %s: %s",
            subscriber.user_id,
            error_msg,
        )


async def send_newsletter_to_user(bot: Bot, subscriber, conn) -> tuple[SendStatus, str]:
    """Sends subscription cars to one user.

    Returns:
        tuple: (SendStatus, error_message)
    """

    async def _send() -> None:
        self_selection_subs = await get_user_subscriptions(
            conn, user_id=subscriber.user_id
        )
        for subscription in self_selection_subs:
            cars_data = await get_cars_for_self_selection(subscription)
            await send_self_selection_cars(bot, subscriber, cars_data)

    try:
        return await send_to_user_safely(
            _send, conn=conn, user_id=subscriber.user_id
        )
    except TelegramRetryAfter as e:
        logger.warning(
            f"Rate limited for user {subscriber.user_id}, waiting {e.retry_after}s"
        )
        await asyncio.sleep(e.retry_after)
        return SendStatus.ERROR, f"Rate limited, retry after {e.retry_after}s"


async def send_daily_newsletter(bot: Bot, db_pool: AsyncConnectionPool) -> None:
    """
    Функция для ежедневной рассылки сообщений подписчикам с использованием очереди

    Args:
        bot: Экземпляр бота для отправки сообщений
        db_pool: Пул соединений с базой данных
    """
    logger.info("Starting daily newsletter task")

    try:
        # Получаем соединение с базой данных
        async with db_pool.connection() as conn:
            # Получаем всех активных подписчиков
            subscribers = await get_active_subscribers(conn)

            if not subscribers:
                logger.info("No active subscribers found")
                return

            logger.info(f"Found {len(subscribers)} active subscribers")

            # Обновления is_alive при блокировках должны фиксироваться сразу
            await conn.set_autocommit(True)

            # Создаем очередь и добавляем подписчиков
            queue = NewsletterQueue(
                max_retries=3,
                batch_size=20,  # Ниже лимита Telegram (~30/сек) с запасом
                delay_between_batches=1.0,  # Пауза 1 секунда между батчами
            )

            # Добавляем подписчиков в очередь асинхронно
            for subscriber in subscribers:
                await queue.add_subscriber(subscriber)

            # Обрабатываем очередь батчами
            while not queue.is_empty():
                batch = await queue.get_batch()
                if not batch:
                    break

                logger.info(f"Processing batch of {len(batch)} subscribers")

                await process_newsletter_batch(bot, conn, queue, batch)

                # Пауза между батчами для соблюдения rate limits
                if not queue.is_empty():
                    await asyncio.sleep(queue.delay_between_batches)

            logger.info("Newsletter completed")

    except Exception as e:
        logger.error(f"Error in daily newsletter task: {e}")
        raise
