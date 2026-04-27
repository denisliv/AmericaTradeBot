"""Tools available to the AI manager: car search, subscriptions, CRM lead."""

from __future__ import annotations

import asyncio
import csv
import logging
import random
import re
from dataclasses import dataclass
from typing import Any, Optional

import aiofiles
import aiohttp
from psycopg import AsyncConnection

from app.infrastructure.database.db import set_subscription
from app.infrastructure.services.ai_manager.cars_catalog import (
    DEFAULT_CARS_MD_PATH,
    find_catalog_price_benchmark,
    load_cars_catalog,
)
from app.infrastructure.services.ai_manager.schemas import CarCard, CollectedInfo
from app.infrastructure.services.bitrix_utils import bitrix_send_data
from app.infrastructure.services.utils import get_images
from app.lexicon.lexicon_ru import LEXICON_EN_RU

logger = logging.getLogger(__name__)

_CSV_PATH = "data/salesdata.csv"
_COPART_LOT_URL = "https://www.copart.com/lot/{lot}/"
_MILES_TO_KM = 1.60934
_LOT_NUMBER_RE = re.compile(r"\b(\d{7,10})\b")


@dataclass
class ToolResult:
    ok: bool
    message: str
    payload: dict[str, Any] | None = None


class AIManagerTools:
    """Concrete tool implementations the graph executes."""

    async def search_cars_by_ranges(
        self,
        *,
        info: CollectedInfo,
        count: int = 3,
    ) -> ToolResult:
        """Search salesdata.csv by numeric ranges and enrich results with preview images.

        Ranges are treated as inclusive. Missing bounds are considered open.
        Odometer is compared in kilometers; CSV stores it in miles.

        If the strict filter yields no rows, we progressively relax constraints
        (drop `model`, then `brand`, then `year` range) so the user still gets
        close alternatives. The names of the relaxed fields are returned in
        the payload as ``relaxed_fields`` so the responder can mention the
        widening honestly instead of pretending zero results.
        """

        if not info.search_ready():
            return ToolResult(
                ok=False,
                message=(
                    "Чтобы подобрать авто, нужен хотя бы один ориентир: "
                    "марка с моделью, или тип топлива/кузова, или диапазон года/бюджета."
                ),
            )

        try:
            async with aiofiles.open(_CSV_PATH, mode="r", encoding="utf-8") as csvfile:
                csv_lines = await csvfile.readlines()
        except FileNotFoundError:
            logger.error("salesdata.csv not found at %s", _CSV_PATH)
            return ToolResult(ok=False, message="Каталог авто временно недоступен.")

        all_rows = list(csv.DictReader(csv_lines))

        # Progressive broadening: each tier relaxes one more constraint.
        # We stop as soon as any tier has matches.
        relax_tiers: list[set[str]] = [
            set(),              # strict
            {"model"},          # drop exact model, keep brand
            {"brand", "model"}, # drop make entirely
            {"brand", "model", "year"},  # same fuel/body/budget, wider years
        ]

        filtered: list[dict] = []
        relaxed_fields: list[str] = []
        for tier in relax_tiers:
            filtered = [row for row in all_rows if _match_row(row, info, ignore=tier)]
            if filtered:
                relaxed_fields = sorted(tier)
                break

        if not filtered:
            return ToolResult(
                ok=True,
                message="Подходящих лотов сейчас нет даже при расширенных критериях.",
                payload={"cars": [], "relaxed_fields": []},
            )

        random.shuffle(filtered)
        selected = filtered[: max(count * 2, count)]

        cards = await _build_cards(selected, target=count)
        if not cards:
            return ToolResult(
                ok=True,
                message="Лоты есть, но без доступных фото. Могу показать без фото?",
                payload={"cars": [], "relaxed_fields": relaxed_fields},
            )

        return ToolResult(
            ok=True,
            message=f"Найдено вариантов: {len(cards)}.",
            payload={
                "cars": cards[:count],
                "relaxed_fields": relaxed_fields,
            },
        )

    async def add_subscription(
        self,
        conn: AsyncConnection,
        *,
        user_id: int,
        subscription_type: str,
    ) -> ToolResult:
        if subscription_type != "self_selection_requests":
            return ToolResult(ok=False, message="Неизвестный тип подписки.")

        new_count = await set_subscription(conn, user_id=user_id, table=subscription_type)
        if new_count <= 0:
            return ToolResult(ok=False, message="Не удалось включить подписку.")

        if new_count >= 6:
            return ToolResult(
                ok=False,
                message="Достигнут лимит активных подписок (6).",
                payload={"active_count": new_count},
            )

        return ToolResult(
            ok=True,
            message=f"Подписка включена. Активных подписок: {new_count}.",
            payload={"active_count": new_count},
        )

    async def lookup_lot_by_number(self, lot_query: str) -> ToolResult:
        lot_number = _extract_lot_number(lot_query)
        if not lot_number:
            return ToolResult(ok=False, message="Не вижу номер лота в сообщении.")

        try:
            async with aiofiles.open(_CSV_PATH, mode="r", encoding="utf-8") as csvfile:
                csv_lines = await csvfile.readlines()
        except FileNotFoundError:
            logger.error("salesdata.csv not found at %s", _CSV_PATH)
            return ToolResult(ok=False, message="Каталог авто временно недоступен.")

        for row in csv.DictReader(csv_lines):
            if str(row.get("Lot number") or "").strip() != lot_number:
                continue
            preview = (row.get("Image Thumbnail") or "").strip()
            if preview and not preview.startswith("http"):
                preview = f"https://{preview.lstrip('/')}"
            if not preview:
                async with aiohttp.ClientSession() as session:
                    images = await get_images(row, session, max_images=1)
                preview = images[0] if images else ""
            if not preview:
                return ToolResult(
                    ok=False,
                    message=f"Лот {lot_number} найден, но фото для карточки недоступно.",
                )
            return ToolResult(
                ok=True,
                message=f"Лот {lot_number} найден в CSV.",
                payload={"car": _make_card(row, preview), "lot": _lot_payload(row)},
            )

        return ToolResult(
            ok=False,
            message=f"Лот {lot_number} не найден в текущем salesdata.csv.",
        )

    async def estimate_landed_cost_for_lot(
        self,
        *,
        lot_query: str,
        shipping_mode: str = "container",
        brand: str | None = None,
        model: str | None = None,
        year: int | None = None,
        fuel_type: str | None = None,
    ) -> ToolResult:
        """Return a transparent rough estimate using CSV facts, cars.md and customs rules."""

        lot_number = _extract_lot_number(lot_query)
        if not lot_number and not (brand and model and year):
            return ToolResult(
                ok=False,
                message="Для примерного расчета достаточно марка/модель/год или номер лота.",
            )

        row: dict[str, Any] | None = None
        if lot_number:
            try:
                async with aiofiles.open(_CSV_PATH, mode="r", encoding="utf-8") as csvfile:
                    csv_lines = await csvfile.readlines()
            except FileNotFoundError:
                logger.error("salesdata.csv not found at %s", _CSV_PATH)
                return ToolResult(ok=False, message="Каталог авто временно недоступен.")

            for candidate in csv.DictReader(csv_lines):
                if str(candidate.get("Lot number") or "").strip() == lot_number:
                    row = candidate
                    break

            if row is None:
                return ToolResult(
                    ok=False,
                    message=f"Лот {lot_number} не найден в текущем salesdata.csv.",
                )

        lot = _lot_payload(row) if row is not None else _manual_lot_payload(
            brand=brand,
            model=model,
            year=year,
            fuel_type=fuel_type,
        )
        price_usd = lot["price_usd"]
        catalog = load_cars_catalog(DEFAULT_CARS_MD_PATH)
        benchmark = find_catalog_price_benchmark(
            catalog=catalog,
            make=lot.get("make") or brand,
            model=lot.get("model_detail") or model,
            year=lot.get("year") or year,
            fuel_type=lot.get("fuel_type") or fuel_type,
            body_style=lot.get("body_style"),
        )
        benchmark_payload = _catalog_benchmark_payload(benchmark)

        is_electric = _normalize_fuel(lot["fuel_type"] or fuel_type or "") == "electric"
        if not is_electric and benchmark and benchmark.entry.category_title == "Электромобили":
            is_electric = True
        customs_usd = 0.0 if is_electric else None
        known_subtotal_usd = (price_usd or 0.0) + (customs_usd or 0.0)
        shipping_label = "контейнер" if "container" in shipping_mode.lower() else shipping_mode
        indicative_range = None
        if benchmark:
            indicative_range = (benchmark.lo_usd, benchmark.hi_usd)
        estimate = {
            "lot_number": lot_number or None,
            "lot_price_usd": price_usd,
            "price_source": lot["price_source"],
            "fuel_type": lot["fuel_type"],
            "shipping_mode": shipping_label,
            "customs_usd": customs_usd,
            "known_subtotal_usd": known_subtotal_usd,
            "catalog_benchmark": benchmark_payload,
            "indicative_total_range_usd": indicative_range,
            "service_fee_note": "Базовый пакет услуг AmericaTrade: 700 BYN.",
            "repair_note": "Финальная стоимость зависит от ремонта и скрытых повреждений.",
        }
        customs_line = (
            "Пошлина/НДС для EV: $0"
            if is_electric
            else "Таможня для ДВС считается по возрасту, стоимости и объему двигателя."
        )
        lot_line = (
            f"{lot['price_source']}: ${price_usd:,.0f}. " if price_usd else "Расчет по марка/модель/год. "
        )
        benchmark_line = (
            f"ориентир по cars.md: ${benchmark.lo_usd:,.0f}-${benchmark.hi_usd:,.0f} "
            f"({benchmark.entry.model}, {benchmark.entry.band_label}). "
            if benchmark
            else "В cars.md нет близкого ценового ориентира; нужен ручной расчет менеджера. "
        )
        return ToolResult(
            ok=True,
            message=(
                f"Примерный расчет: {lot['year']} {lot['make']} {lot['model_detail']}. "
                f"{lot_line}{customs_line}. "
                f"{benchmark_line}"
                "В этот ориентир закладывай покупку, доставку, таможенный контур и услугу; "
                "базовый пакет услуг AmericaTrade отдельно: 700 BYN. "
                "Конечная стоимость зависит от ремонта и скрытых повреждений; это оценивает менеджер "
                "после передачи в CRM."
            ).replace(",", " "),
            payload={"lot": lot, "estimate": estimate},
        )

    async def quick_vehicle_specs(
        self,
        *,
        brand: str,
        model: str,
        year_from: int | None = None,
        year_to: int | None = None,
        limit: int = 30,
    ) -> ToolResult:
        if not brand or not model:
            return ToolResult(ok=False, message="Нужны марка и модель для проверки характеристик.")
        try:
            async with aiofiles.open(_CSV_PATH, mode="r", encoding="utf-8") as csvfile:
                csv_lines = await csvfile.readlines()
        except FileNotFoundError:
            logger.error("salesdata.csv not found at %s", _CSV_PATH)
            return ToolResult(ok=False, message="Каталог авто временно недоступен.")

        rows: list[dict[str, Any]] = []
        brand_norm = brand.strip().lower()
        model_norm = model.strip().lower()
        for row in csv.DictReader(csv_lines):
            make = (row.get("Make") or "").strip().lower()
            model_group = (row.get("Model Group") or "").strip().lower()
            model_detail = (row.get("Model Detail") or "").strip().lower()
            if make != brand_norm:
                continue
            if model_norm not in model_group and model_norm not in model_detail:
                continue
            year = _safe_int(row.get("Year"))
            if year_from is not None and (year is None or year < year_from):
                continue
            if year_to is not None and (year is None or year > year_to):
                continue
            rows.append(row)
            if len(rows) >= max(limit, 1):
                break

        if not rows:
            return ToolResult(
                ok=False,
                message=f"В CSV не нашел быстрые характеристики для {brand} {model}.",
            )

        specs = _summarize_vehicle_specs(rows)
        if specs["is_electric"]:
            customs_note = "По электромобилям в базе знаний: пошлина 0% + НДС 0% в действующие льготные периоды."
        else:
            customs_note = (
                "Для растаможки ДВС важны возраст авто и объем двигателя; точный расчет нужен по конкретному лоту."
            )
        return ToolResult(
            ok=True,
            message=customs_note,
            payload={"specs": specs},
        )

    async def create_lead(
        self,
        *,
        tg_login: str | None,
        tg_id: int,
        data: dict[str, Any],
        method: str,
    ) -> ToolResult:
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                response = await bitrix_send_data(
                    tg_login=tg_login or "",
                    tg_id=tg_id,
                    data=data,
                    method=method,
                )
                return ToolResult(
                    ok=True,
                    message="Лид отправлен в Bitrix.",
                    payload={"bitrix_response": response},
                )
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Failed to send AI manager lead to Bitrix (attempt %s/2): %s",
                    attempt + 1,
                    exc,
                )
                if attempt == 0:
                    await asyncio.sleep(0.2)
        logger.exception("Failed to send AI manager lead to Bitrix: %s", last_exc)
        return ToolResult(
            ok=False,
            message="Не удалось передать лид в CRM. Менеджер свяжется вручную.",
        )


def _match_row(
    row: dict, info: CollectedInfo, *, ignore: set[str] | None = None
) -> bool:
    """Pure-python row filter honoring open ranges and case-insensitive string match.

    Pass ``ignore`` with one or more of {"brand", "model", "year"} to relax
    the corresponding constraints while keeping everything else. Used by the
    progressive broadening search so we can surface near-miss alternatives
    instead of an empty list.
    """
    skip = ignore or set()
    try:
        make = (row.get("Make") or "").strip()
        model_group = (row.get("Model Group") or "").strip()
        year_str = row.get("Year") or ""
        sale_date = row.get("Sale Date M/D/CY") or "0"

        if not make or not model_group or not year_str:
            return False
        if sale_date == "0":
            return False

        if "brand" not in skip and info.brand and make.lower() != info.brand.lower():
            return False
        if "model" not in skip and info.model and info.model.lower() not in model_group.lower():
            return False

        year = int(year_str)
        if "year" not in skip:
            if info.year_from is not None and year < info.year_from:
                return False
            if info.year_to is not None and year > info.year_to:
                return False

        if info.odometer_from_km is not None or info.odometer_to_km is not None:
            try:
                miles = float(row.get("Odometer") or 0)
            except ValueError:
                return False
            km = miles * _MILES_TO_KM
            if info.odometer_from_km is not None and km < info.odometer_from_km:
                return False
            if info.odometer_to_km is not None and km > info.odometer_to_km:
                return False

        if info.buy_now_only:
            try:
                buy_now = float(row.get("Buy-It-Now Price") or 0)
            except ValueError:
                buy_now = 0.0
            if buy_now <= 0:
                return False

        if info.body_style:
            body = (row.get("Body Style") or "").lower()
            if info.body_style.lower() not in body:
                return False

        if info.fuel_type:
            fuel = (row.get("Fuel Type") or "").strip().lower()
            if _normalize_fuel(info.fuel_type) != fuel:
                return False

        if info.budget_from_usd is not None or info.budget_to_usd is not None:
            price = _row_price(row)
            if price is None:
                return False
            if info.budget_from_usd is not None and price < info.budget_from_usd:
                return False
            if info.budget_to_usd is not None and price > info.budget_to_usd:
                return False

        return True
    except (ValueError, KeyError):
        return False


def _normalize_fuel(value: str) -> str:
    """Map common Russian/English fuel aliases to the CSV vocabulary."""
    v = value.strip().lower()
    aliases = {
        "электро": "electric",
        "электрический": "electric",
        "электромобиль": "electric",
        "ev": "electric",
        "electric": "electric",
        "гибрид": "hybrid",
        "hybrid": "hybrid",
        "бензин": "gasoline",
        "бензиновый": "gasoline",
        "gasoline": "gasoline",
        "petrol": "gasoline",
        "gas": "gasoline",
        "дизель": "diesel",
        "дизельный": "diesel",
        "diesel": "diesel",
    }
    return aliases.get(v, v)


def _row_price(row: dict) -> float | None:
    """Pick the most meaningful price signal available for a row."""
    for key in ("Buy-It-Now Price", "High Bid =non-vix,Sealed=Vix", "Est. Retail Value"):
        try:
            value = float(row.get(key) or 0)
            if value > 0:
                return value
        except (TypeError, ValueError):
            continue
    return None


def _lot_payload(row: dict[str, Any]) -> dict[str, Any]:
    price_source: str | None = None
    price_usd: float | None = None
    for key, label in (
        ("Buy-It-Now Price", "Buy Now"),
        ("High Bid =non-vix,Sealed=Vix", "текущая ставка"),
        ("Est. Retail Value", "оценочная розничная стоимость"),
    ):
        value = _safe_float(row.get(key))
        if value and value > 0:
            price_source = label
            price_usd = value
            break

    return {
        "lot_number": str(row.get("Lot number") or row.get("Id") or "").strip(),
        "year": _safe_int(row.get("Year")),
        "make": (row.get("Make") or "").strip(),
        "model_detail": (row.get("Model Detail") or "").strip(),
        "model_group": (row.get("Model Group") or "").strip(),
        "fuel_type": (row.get("Fuel Type") or "").strip(),
        "engine": (row.get("Engine") or "").strip(),
        "drive": (row.get("Drive") or "").strip(),
        "transmission": (row.get("Transmission") or "").strip(),
        "body_style": (row.get("Body Style") or "").strip(),
        "price_source": price_source,
        "price_usd": price_usd,
    }


def _manual_lot_payload(
    *,
    brand: str | None,
    model: str | None,
    year: int | None,
    fuel_type: str | None,
) -> dict[str, Any]:
    return {
        "lot_number": "",
        "year": year,
        "make": (brand or "").strip(),
        "model_detail": (model or "").strip(),
        "model_group": (model or "").strip(),
        "fuel_type": (fuel_type or "").strip(),
        "engine": "",
        "drive": "",
        "transmission": "",
        "body_style": "",
        "price_source": None,
        "price_usd": None,
    }


def _catalog_benchmark_payload(benchmark: Any | None) -> dict[str, Any] | None:
    if benchmark is None:
        return None
    return {
        "model": benchmark.entry.model,
        "category": benchmark.entry.category_title,
        "band_label": benchmark.entry.band_label,
        "lo_usd": benchmark.lo_usd,
        "hi_usd": benchmark.hi_usd,
        "match_type": benchmark.match_type,
    }


def _summarize_vehicle_specs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def unique(column: str, max_items: int = 6) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for row in rows:
            value = str(row.get(column) or "").strip()
            if not value or value in seen:
                continue
            out.append(value)
            seen.add(value)
            if len(out) >= max_items:
                break
        return out

    years = sorted(
        {
            year
            for row in rows
            if (year := _safe_int(row.get("Year"))) is not None
        }
    )
    fuel_types = unique("Fuel Type")
    engines = unique("Engine")
    body_styles = unique("Body Style")
    is_electric = any(_normalize_fuel(value) == "electric" for value in fuel_types)
    return {
        "sample_size": len(rows),
        "years": years,
        "fuel_types": fuel_types,
        "engines": engines,
        "body_styles": body_styles,
        "drives": unique("Drive"),
        "transmissions": unique("Transmission"),
        "is_electric": is_electric,
    }


def _extract_lot_number(value: str) -> str | None:
    match = _LOT_NUMBER_RE.search(value or "")
    return match.group(1) if match else None


async def _build_cards(rows: list[dict], *, target: int) -> list[CarCard]:
    """Fetch a single preview image per row and build CarCard list.

    Uses 'Image Thumbnail' when present to avoid extra API calls. Falls back to
    one HD image from the Copart lotImages API if the thumbnail is missing.
    """
    cards: list[CarCard] = []
    rows_needing_hd: list[tuple[int, dict]] = []

    for idx, row in enumerate(rows):
        thumb = (row.get("Image Thumbnail") or "").strip()
        if thumb:
            preview = thumb if thumb.startswith("http") else f"https://{thumb.lstrip('/')}"
            cards.append(_make_card(row, preview))
        else:
            cards.append(None)  # type: ignore[arg-type]
            rows_needing_hd.append((idx, row))

    if rows_needing_hd and len(cards) - sum(c is None for c in cards) < target:
        async with aiohttp.ClientSession() as session:
            results = await asyncio.gather(
                *(get_images(row, session, max_images=1) for _, row in rows_needing_hd),
                return_exceptions=True,
            )
        for (idx, row), imgs in zip(rows_needing_hd, results):
            preview = None
            if isinstance(imgs, list) and imgs:
                preview = imgs[0]
            if preview:
                cards[idx] = _make_card(row, preview)

    return [c for c in cards if c is not None]


def _make_card(row: dict, preview_image_url: str) -> CarCard:
    lot_number = str(row.get("Lot number") or row.get("Id") or "").strip()
    year = _safe_int(row.get("Year"))
    make = (row.get("Make") or "").strip() or None
    model_detail = (row.get("Model Detail") or "").strip() or None
    body_style = (row.get("Body Style") or "").strip() or None
    color_raw = (row.get("Color") or "").strip()
    color = LEXICON_EN_RU["Color"].get(color_raw, color_raw.title()) if color_raw else None
    engine = (row.get("Engine") or "").strip() or None
    drive_raw = (row.get("Drive") or "").strip()
    drive = LEXICON_EN_RU["Drive"].get(drive_raw, drive_raw.title()) if drive_raw else None
    trans_raw = (row.get("Transmission") or "").strip()
    transmission = LEXICON_EN_RU["Transmission"].get(trans_raw, trans_raw.title()) if trans_raw else None

    odo_miles = _safe_float(row.get("Odometer"))
    odometer = None
    if odo_miles is not None:
        odometer = f"{int(odo_miles * _MILES_TO_KM):,} км".replace(",", " ")

    sale_date_raw = (row.get("Sale Date M/D/CY") or "0").strip()
    sale_date = None
    if sale_date_raw and sale_date_raw != "0" and len(sale_date_raw) == 8:
        sale_date = f"{sale_date_raw[0:4]}-{sale_date_raw[4:6]}-{sale_date_raw[6:8]}"

    buy_now = _safe_float(row.get("Buy-It-Now Price"))
    buy_now = buy_now if buy_now and buy_now > 0 else None

    lot_url = _COPART_LOT_URL.format(lot=lot_number) if lot_number else "https://www.copart.com"

    caption_lines: list[str] = []
    title_parts = [str(year) if year else "", make or "", model_detail or ""]
    title = " ".join(part for part in title_parts if part).strip()
    if title:
        caption_lines.append(title)
    details: list[str] = []
    if odometer:
        details.append(f"пробег {odometer}")
    if engine:
        details.append(f"двигатель {engine[:10]}")
    if transmission:
        details.append(transmission)
    if drive:
        details.append(drive)
    if color:
        details.append(color.lower())
    if details:
        caption_lines.append(", ".join(details))
    if buy_now:
        caption_lines.append(f"Buy Now: ${int(buy_now):,}".replace(",", " "))
    if sale_date:
        caption_lines.append(f"Аукцион: {sale_date}")
    caption_lines.append(f"Лот №{lot_number}")
    caption = "\n".join(caption_lines)

    return CarCard(
        lot_number=lot_number,
        year=year,
        make=make,
        model=model_detail,
        body_style=body_style,
        color=color,
        odometer=odometer,
        engine=engine,
        drive=drive,
        transmission=transmission,
        sale_date=sale_date,
        buy_now_price=buy_now,
        preview_image_url=preview_image_url,
        lot_url=lot_url,
        caption=caption,
    )


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (ValueError, TypeError):
        return None
