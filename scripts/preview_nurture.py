"""Отправляет шаги прогревочной цепочки указанному пользователю для проверки.

Проверяет контент постов (картинки, подписи, кнопки, подборку из CSV) без
ожидания расписания. Не конфликтует с работающим ботом: скрипт не использует
polling, только отправку сообщений.

Запуск:
    uv run python scripts/preview_nurture.py <telegram_user_id>
    uv run python scripts/preview_nurture.py <telegram_user_id> --steps 1,4
    docker compose exec bot python scripts/preview_nurture.py <telegram_user_id>

Пользователь должен хотя бы раз запустить бота (/start), иначе Telegram
не позволит отправить ему сообщение.
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

from app.config import load_config  # noqa: E402
from app.infrastructure.services.nurture import send_nurture_step  # noqa: E402


def parse_steps(raw: str) -> list[int]:
    """"1-9" или "1,3,5" -> список номеров шагов."""
    if "-" in raw:
        start, end = raw.split("-", 1)
        steps = list(range(int(start), int(end) + 1))
    else:
        steps = [int(part) for part in raw.split(",")]
    for step in steps:
        if not 1 <= step <= 9:
            raise ValueError(f"Шаг {step} вне диапазона 1-9")
    return steps


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Отправить шаги прогревочной рассылки для проверки"
    )
    parser.add_argument("user_id", type=int, help="Telegram user_id получателя")
    parser.add_argument(
        "--steps",
        default="1-9",
        help='Шаги: "1-9" (по умолчанию) или перечисление "1,2,4"',
    )
    parser.add_argument(
        "--name", default="Тест", help="Имя, подставляемое в тексты постов"
    )
    args = parser.parse_args()
    steps = parse_steps(args.steps)

    config = load_config()
    bot = Bot(
        token=config.bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    failed = 0
    try:
        for step in steps:
            print(f"Шаг {step}: отправляю...", flush=True)
            try:
                await send_nurture_step(bot, args.user_id, args.name, step)
            except Exception as e:
                failed += 1
                print(f"Шаг {step}: ОШИБКА - {e}", flush=True)
            else:
                print(f"Шаг {step}: OK", flush=True)
            await asyncio.sleep(1)
    finally:
        await bot.session.close()

    if failed:
        print(f"Готово с ошибками: {failed} из {len(steps)} шагов не отправлены")
        sys.exit(1)
    print(f"Готово: отправлено {len(steps)} шагов")


if __name__ == "__main__":
    asyncio.run(main())
