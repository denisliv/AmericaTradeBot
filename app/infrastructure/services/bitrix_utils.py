import logging
import os
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


def _get_bitrix_base_url() -> str:
    raw_url = os.getenv("BITRIX_WEBHOOK_URL", "").strip()
    if not raw_url:
        raise RuntimeError("BITRIX_WEBHOOK_URL is required")
    base_url = raw_url.rstrip("/")
    return f"{base_url}/crm.lead.add.json"


def _ai_manager_comments(data: dict[str, Any]) -> str:
    parts = [
        f"Источник: {data.get('source', 'AI Manager')}",
        f"Стадия: {data.get('stage', 'interested')}",
        f"Интент: {data.get('intent', '')}",
    ]
    optional_fields = (
        ("Саммари для менеджера", "dialog_summary"),
        ("Марка", "brand"),
        ("Модель", "model"),
        ("Год", "year"),
        ("Бюджет", "budget"),
        ("Выбранный лот", "selected_lot"),
        ("Уверенность", "confidence"),
    )
    for label, key in optional_fields:
        value = data.get(key)
        if value not in (None, ""):
            parts.append(f"{label}: {value}")
    return " | ".join(parts)


def _raise_for_bitrix_error(payload: Any) -> None:
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(
            f"Bitrix returned error {payload.get('error')}: "
            f"{payload.get('error_description', '')}"
        )


def _build_fields(tg_login: str, tg_id: int, data: dict, method: str) -> dict:
    telegram_value = f"@{tg_login}" if tg_login else str(tg_id)

    if method == "consultation_request":
        return {
            "FIELDS[TITLE]": "Консультация (TgBot)",
            "FIELDS[NAME]": data.get("name", ""),
            "FIELDS[PHONE][0][VALUE]": data.get("phone", ""),
            "FIELDS[PHONE][0][VALUE_TYPE]": "Мобильный",
            "FIELDS[IM][0][VALUE]": telegram_value,
            "FIELDS[IM][0][VALUE_TYPE]": "Telegram",
        }

    if method == "self_selection":
        lot_description = data.get("lot").split("-")
        lot_number = lot_description[0][7:]
        brand = lot_description[1]
        model = lot_description[2]
        return {
            "FIELDS[TITLE]": f"{brand} {model} (TgBot)",
            "FIELDS[NAME]": data.get("name", ""),
            "FIELDS[PHONE][0][VALUE]": data.get("phone", ""),
            "FIELDS[PHONE][0][VALUE_TYPE]": "Мобильный",
            "FIELDS[IM][0][VALUE]": telegram_value,
            "FIELDS[IM][0][VALUE_TYPE]": "Telegram",
            "FIELDS[COMMENTS]": (
                f"Лот №: {lot_number} | https://www.copart.com/lot/{lot_number}/"
            ),
        }

    if method == "assisted_gallery":
        car_title = data.get("car_title", "")
        body_style = data.get("body_style", "")
        budget = data.get("budget", "")
        return {
            "FIELDS[TITLE]": f"Пример из галереи: {car_title} (TgBot)",
            "FIELDS[NAME]": data.get("name", ""),
            "FIELDS[PHONE][0][VALUE]": data.get("phone", ""),
            "FIELDS[PHONE][0][VALUE_TYPE]": "Мобильный",
            "FIELDS[IM][0][VALUE]": telegram_value,
            "FIELDS[IM][0][VALUE_TYPE]": "Telegram",
            "FIELDS[COMMENTS]": (
                f"Assisted selection (галерея): {car_title} | "
                f"Кузов: {body_style} | Бюджет: {budget}"
            ),
        }

    if method == "ai_manager_chat":
        return {
            "FIELDS[TITLE]": "AIManager AmericaTrade(TgBot)",
            "FIELDS[NAME]": data.get("name", ""),
            "FIELDS[PHONE][0][VALUE]": data.get("phone", ""),
            "FIELDS[PHONE][0][VALUE_TYPE]": "Мобильный",
            "FIELDS[IM][0][VALUE]": telegram_value,
            "FIELDS[IM][0][VALUE_TYPE]": "Telegram",
            "FIELDS[COMMENTS]": _ai_manager_comments(data),
        }

    raise ValueError(f"Unsupported bitrix method: {method}")


async def bitrix_send_data(tg_login: str, tg_id: int, data: dict, method: str) -> str:
    url = _get_bitrix_base_url()
    fields = _build_fields(tg_login, tg_id, data, method)
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=fields) as resp:
            response = await resp.text()
            if resp.status >= 400:
                logger.error(
                    "Bitrix lead request failed: status=%s method=%s body=%s",
                    resp.status,
                    method,
                    response,
                )
                raise RuntimeError(
                    f"Bitrix request failed with status {resp.status}: {response}"
                )
            try:
                payload = await resp.json(content_type=None)
            except Exception:
                payload = None
            _raise_for_bitrix_error(payload)
            return response
