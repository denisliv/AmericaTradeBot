"""Отправляет еженедельные посты указанному пользователю для проверки.

Проверяет контент постов (картинка + текст-подпись) без ожидания воскресенья.
Не конфликтует с работающим ботом: скрипт не использует polling.

Запуск:
    uv run python scripts/preview_weekly_posts.py <telegram_user_id>
    uv run python scripts/preview_weekly_posts.py <telegram_user_id> --posts 3,5
    uv run python scripts/preview_weekly_posts.py <telegram_user_id> --current
    docker compose exec bot python scripts/preview_weekly_posts.py <telegram_user_id>

Пользователь должен хотя бы раз запустить бота (/start).
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Запуск файлом из корня проекта: добавляем корень в sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram import Bot  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.types import FSInputFile  # noqa: E402

from app.config import load_config  # noqa: E402
from app.infrastructure.services.daily_posts_broadcast import (  # noqa: E402
    list_post_files,
    pick_post_for_current_week,
    weekly_post_image,
)


def select_posts(raw: str, files: list[Path]) -> list[Path]:
    """"1-12" или "1,3,5" -> файлы постов по порядковым номерам (с 1)."""
    if "-" in raw:
        start, end = raw.split("-", 1)
        numbers = list(range(int(start), int(end) + 1))
    else:
        numbers = [int(part) for part in raw.split(",")]
    for number in numbers:
        if not 1 <= number <= len(files):
            raise ValueError(f"Пост {number} вне диапазона 1-{len(files)}")
    return [files[number - 1] for number in numbers]


async def send_post(bot: Bot, user_id: int, path: Path) -> None:
    text = path.read_text(encoding="utf-8").strip()
    image = weekly_post_image(path)
    if image:
        await bot.send_photo(
            chat_id=user_id,
            photo=FSInputFile(image),
            caption=text,
            parse_mode=None,
        )
    else:
        await bot.send_message(chat_id=user_id, text=text, parse_mode=None)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Отправить еженедельные посты для проверки"
    )
    parser.add_argument("user_id", type=int, help="Telegram user_id получателя")
    parser.add_argument(
        "--posts",
        default=None,
        help='Номера постов: "3,5" или "1-12" (по умолчанию - все)',
    )
    parser.add_argument(
        "--current",
        action="store_true",
        help="Отправить только пост текущей календарной недели",
    )
    args = parser.parse_args()

    files = list_post_files()
    if not files:
        print("В data/posts нет файлов post_*.txt")
        sys.exit(1)

    if args.current:
        picked = pick_post_for_current_week()
        if not picked:
            print("Пост текущей недели не найден")
            sys.exit(1)
        selected = [picked[0]]
        print(f"Пост текущей недели: {picked[0].name}")
    elif args.posts:
        selected = select_posts(args.posts, files)
    else:
        selected = files

    config = load_config()
    bot = Bot(
        token=config.bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    failed = 0
    try:
        for path in selected:
            print(f"{path.name}: отправляю...", flush=True)
            try:
                await send_post(bot, args.user_id, path)
            except Exception as e:
                failed += 1
                print(f"{path.name}: ОШИБКА - {e}", flush=True)
            else:
                print(f"{path.name}: OK", flush=True)
            await asyncio.sleep(1)
    finally:
        await bot.session.close()

    if failed:
        print(f"Готово с ошибками: {failed} из {len(selected)} постов не отправлены")
        sys.exit(1)
    print(f"Готово: отправлено {len(selected)} постов")


if __name__ == "__main__":
    asyncio.run(main())
