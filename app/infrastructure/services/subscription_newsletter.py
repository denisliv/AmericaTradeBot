import asyncio
import logging
from typing import List, Tuple

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from psycopg_pool import AsyncConnectionPool

from app.infrastructure.database.db import (
    get_active_subscribers,
    get_user_subscriptions,
)
from app.infrastructure.services.utils import (
    get_assisted_data,
    get_data,
    make_media_group,
)
from app.lexicon.lexicon_ru import LEXICON_NEWSLETTER_RU, LEXICON_RU

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
    successful_cars = []

    # Отправляем все media_group для автомобилей
    for i, (car, images) in enumerate(cars_data, 1):
        try:
            # Проверяем, что у автомобиля есть изображения
            if not images:
                logger.warning(f"No images for car {i}, skipping")
                continue

            # Создаем media group с фото
            media_group = await make_media_group(
                (car, images), subscriber.name or "Пользователь", i
            )

            # Отправляем фото
            await bot.send_media_group(chat_id=subscriber.user_id, media=media_group)
            successful_cars.append((i, car))
            messages_sent += 1
            await asyncio.sleep(0.5)  # пауза между автомобилями

        except Exception as e:
            logger.error(f"Error sending car {i} to user {subscriber.user_id}: {e}")
            logger.error(f"Car data: {car}")
            logger.error(f"Images: {images}")
            continue

    # Отправляем одно сообщение с кнопками для всех успешно отправленных автомобилей
    if successful_cars:
        # Создаем кнопки для всех автомобилей
        keyboard_buttons = []
        for i, car in successful_cars:
            keyboard_buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"Авто № {i}",
                        callback_data=f"Лот №: {car.get('Lot number', 'N/A')}-{car.get('Make', 'N/A')}-{car.get('Model Detail', 'N/A')}",
                    )
                ]
            )

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        # Отправляем сообщение с кнопками
        await bot.send_message(
            chat_id=subscriber.user_id,
            text=LEXICON_NEWSLETTER_RU["car_selection_text"],
            reply_markup=keyboard,
        )
        messages_sent += 1

    return messages_sent


async def send_assisted_selection_cars(
    bot: Bot,
    subscriber,
    cars_data: List[Tuple[dict, List[str]]],
) -> int:
    """Отправляет автомобили для assisted selection подписки с фото и кнопками"""
    if not cars_data:
        await bot.send_message(
            chat_id=subscriber.user_id,
            text=f"{LEXICON_RU['nothing_found_text']}",
        )
        return 0

    messages_sent = 0
    successful_cars = []

    # Отправляем все media_group для автомобилей
    for i, (car, images) in enumerate(cars_data, 1):
        try:
            # Проверяем, что у автомобиля есть изображения
            if not images:
                logger.warning(f"No images for car {i}, skipping")
                continue

            # Создаем media group с фото
            media_group = await make_media_group(
                (car, images), subscriber.name or "Пользователь", i
            )

            # Отправляем фото
            await bot.send_media_group(chat_id=subscriber.user_id, media=media_group)
            successful_cars.append((i, car))
            messages_sent += 1
            await asyncio.sleep(0.5)  # пауза между автомобилями

        except Exception as e:
            logger.error(f"Error sending car {i} to user {subscriber.user_id}: {e}")
            logger.error(f"Car data: {car}")
            logger.error(f"Images: {images}")
            continue

    # Отправляем одно сообщение с кнопками для всех успешно отправленных автомобилей
    if successful_cars:
        # Создаем кнопки для всех автомобилей
        keyboard_buttons = []
        for i, car in successful_cars:
            keyboard_buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"Авто № {i}",
                        callback_data=f"Лот №: {car.get('Lot number', 'N/A')}-{car.get('Make', 'N/A')}-{car.get('Model Detail', 'N/A')}",
                    )
                ]
            )

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        # Отправляем сообщение с кнопками
        await bot.send_message(
            chat_id=subscriber.user_id,
            text=LEXICON_NEWSLETTER_RU["car_selection_text"],
            reply_markup=keyboard,
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


async def get_cars_for_assisted_selection(
    subscription,
) -> List[Tuple[dict, List[str]]]:
    """Получает автомобили для assisted selection подписки"""
    user_dict = {
        "body_style": subscription.body_style,
        "budget": subscription.budget,
    }

    cars_data = await get_assisted_data(user_dict, count=3)
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


async def send_newsletter_to_user(bot: Bot, subscriber, conn) -> tuple[bool, str]:
    """
    Отправляет рассылку пользователю с данными об автомобилях

    Returns:
        tuple: (success: bool, error_message: str)
    """
    try:
        # Получаем подписки пользователя
        self_selection_subs, assisted_selection_subs = await get_user_subscriptions(
            conn, user_id=subscriber.user_id
        )

        messages_sent = 0

        # Обрабатываем self selection подписки
        for subscription in self_selection_subs:
            cars_data = await get_cars_for_self_selection(subscription)
            messages_sent += await send_self_selection_cars(bot, subscriber, cars_data)

        # Обрабатываем assisted selection подписки
        for subscription in assisted_selection_subs:
            cars_data = await get_cars_for_assisted_selection(subscription)
            messages_sent += await send_assisted_selection_cars(
                bot, subscriber, cars_data
            )

        logger.debug(f"Sent {messages_sent} messages to user {subscriber.user_id}")
        return True, ""

    except TelegramRetryAfter as e:
        # Telegram просит подождать
        wait_time = e.retry_after
        logger.warning(
            f"Rate limited for user {subscriber.user_id}, waiting {wait_time}s"
        )
        await asyncio.sleep(wait_time)
        return False, f"Rate limited, retry after {wait_time}s"

    except TelegramBadRequest as e:
        error_msg = str(e)
        if "chat not found" in error_msg or "bot was blocked" in error_msg:
            return False, "User blocked bot"
        elif "user is deactivated" in error_msg:
            return False, "User deactivated"
        else:
            return False, f"Bad request: {error_msg}"

    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


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

            # Создаем очередь и добавляем подписчиков
            queue = NewsletterQueue(
                max_retries=3,
                batch_size=30,  # Отправляем по 30 сообщений за раз
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

                # Отправляем сообщения в батче параллельно
                tasks = []
                for subscriber, retry_count in batch:
                    task = send_newsletter_to_user(bot, subscriber, conn)
                    tasks.append((task, subscriber, retry_count))

                # Ждем завершения всех задач в батче
                for task, subscriber, retry_count in tasks:
                    success, error_msg = await task

                    if success:
                        logger.debug(f"Newsletter sent to user {subscriber.user_id}")
                    else:
                        if "blocked" in error_msg or "deactivated" in error_msg:
                            logger.warning(
                                f"User {subscriber.user_id} blocked bot or deactivated"
                            )
                        else:
                            # Добавляем в очередь для повторной отправки
                            await queue.add_retry(subscriber, retry_count)
                            logger.warning(
                                f"Failed to send newsletter to user {subscriber.user_id}: {error_msg}"
                            )

                # Пауза между батчами для соблюдения rate limits
                if not queue.is_empty():
                    await asyncio.sleep(queue.delay_between_batches)

            logger.info("Newsletter completed")

    except Exception as e:
        logger.error(f"Error in daily newsletter task: {e}")
        raise
