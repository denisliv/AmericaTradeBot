import asyncio
import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

_BITRIX_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=5)
_BITRIX_MAX_ATTEMPTS = 3


def _strip_non_bmp(text: str) -> str:
    """Remove characters outside the Unicode BMP (e.g. most emoji).

    Bitrix stores COMMENTS in MySQL utf8 (3-byte), which truncates the value
    at the first 4-byte character, losing everything after it.
    """
    cleaned = "".join(ch for ch in text if ord(ch) <= 0xFFFF)
    return " ".join(cleaned.split())


def _get_bitrix_base_url(webhook_url: str) -> str:
    raw_url = webhook_url.strip()
    if not raw_url:
        raise RuntimeError("BITRIX_WEBHOOK_URL is required")
    base_url = raw_url.rstrip("/")
    return f"{base_url}/crm.lead.add.json"


def _raise_for_bitrix_error(payload: Any) -> None:
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(
            f"Bitrix returned error {payload.get('error')}: "
            f"{payload.get('error_description', '')}"
        )


def _build_fields(tg_login: str, tg_id: int, data: dict, method: str) -> dict:
    telegram_value = f"@{tg_login}" if tg_login else str(tg_id)

    if method == "consultation_request":
        brand = data.get("brand", "")
        model = data.get("model", "")
        year = data.get("year", "")
        body_style = data.get("body_style", "")
        budget = data.get("budget", "")
        car_title = data.get("car_title", "")
        lot = data.get("lot", "")
        request_details = data.get("request_details", "")
        source = data.get("source", "")

        # Тип запроса: из рассылки / с выбранными критериями / просто консультация
        if source == "nurture":
            category = "По рассылке"
        elif any(
            [brand, model, year, body_style, budget, car_title, lot, request_details]
        ):
            category = "Заявка"
        else:
            category = "Консультация"

        fields = {
            "FIELDS[TITLE]": f"AmericaTradeBot | {category}",
            "FIELDS[NAME]": data.get("name", ""),
            "FIELDS[PHONE][0][VALUE]": data.get("phone", ""),
            "FIELDS[PHONE][0][VALUE_TYPE]": "Мобильный",
            "FIELDS[IM][0][VALUE]": telegram_value,
            "FIELDS[IM][0][VALUE_TYPE]": "Telegram",
        }

        parts = []
        if brand:
            parts.append(f"Марка: {brand}")
        if model:
            parts.append(f"Модель: {model}")
        if year:
            parts.append(f"Год: {year}")
        if body_style:
            parts.append(f"Тип авто: {body_style}")
        if budget:
            parts.append(f"Бюджет: {budget}")
        if car_title and lot:
            parts.append(f"Авто: {car_title}")
            parts.append(f"Лот №: {lot} | https://www.copart.com/lot/{lot}/")
        elif car_title:
            parts.append(f"Пример: {car_title}")
        if request_details:
            parts.append(f"Запрос клиента: {request_details}")
        if parts:
            fields["FIELDS[COMMENTS]"] = _strip_non_bmp(" | ".join(parts))
        return fields

    raise ValueError(f"Unsupported bitrix method: {method}")


async def bitrix_send_data(
    tg_login: str,
    tg_id: int,
    data: dict,
    method: str,
    *,
    webhook_url: str,
) -> str:
    url = _get_bitrix_base_url(webhook_url)
    fields = _build_fields(tg_login, tg_id, data, method)

    last_error: Exception | None = None
    async with aiohttp.ClientSession(timeout=_BITRIX_TIMEOUT) as session:
        for attempt in range(1, _BITRIX_MAX_ATTEMPTS + 1):
            try:
                async with session.post(url, data=fields) as resp:
                    response = await resp.text()
                    if 500 <= resp.status < 600:
                        raise aiohttp.ClientResponseError(
                            request_info=resp.request_info,
                            history=resp.history,
                            status=resp.status,
                            message=response,
                        )
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
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
                if attempt >= _BITRIX_MAX_ATTEMPTS:
                    break
                backoff = 2 ** (attempt - 1)
                logger.warning(
                    "Bitrix request retry %s/%s in %ss: %s",
                    attempt,
                    _BITRIX_MAX_ATTEMPTS,
                    backoff,
                    exc,
                )
                await asyncio.sleep(backoff)

    raise RuntimeError(f"Bitrix request failed after retries: {last_error}")
