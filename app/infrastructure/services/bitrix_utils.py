import asyncio
import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

_BITRIX_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=5)
_BITRIX_MAX_ATTEMPTS = 3


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
