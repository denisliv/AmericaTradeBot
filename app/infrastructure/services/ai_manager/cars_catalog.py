"""Parse data/ai_manager/cars.md and query by budget band and body / EV category.

Structure: `##` category → `###` price band → bullet lines
`- **Model** — годы: ...`
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

DEFAULT_CARS_MD_PATH = Path("data/ai_manager/cars.md")

_CATEGORIES_ALIASES: dict[str, str] = {
    "электро": "Электромобили",
    "электромобиль": "Электромобили",
    "электромобили": "Электромобили",
    "электрический": "Электромобили",
    "ev": "Электромобили",
    "седан": "Седан",
    "седаны": "Седан",
    "кроссовер": "Кроссовер",
    "сув": "Кроссовер",
    "suv": "Кроссовер",
}


@dataclass
class CarMdEntry:
    """One bullet line in cars.md."""

    model: str
    years_text: str
    category_title: str
    band_label: str
    lo_usd: float
    hi_usd: float
    band_kind: str  # "up_to" | "range" | "above"


@dataclass
class CatalogPriceBenchmark:
    """Best matching cars.md price band for a requested vehicle."""

    entry: CarMdEntry
    lo_usd: int
    hi_usd: int
    match_type: str  # "model" | "category"


@dataclass
class CarsMdCatalog:
    path: Path
    # category -> ordered list of band blocks: (band_h3 label, list of entries)
    categories: dict[str, list[tuple[str, list[CarMdEntry]]]] = field(
        default_factory=dict
    )


_ITEM_LINE_RE = re.compile(
    r"^[-*]\s*\*\*(.+?)\*\*\s*[—:–-]\s*(.+?)\s*$", re.UNICODE
)


def _parse_money_token(s: str) -> int:
    digits = re.sub(r"[^\d]", "", s, flags=re.UNICODE)
    if not digits:
        return 0
    return int(digits)


def _parse_band_h3(
    t: str,
) -> tuple[str, float, float, str] | None:
    """Return (label, lo, hi, band_kind) for matching prices."""
    t0 = t.strip()
    t_lower = t0.lower().replace("\u00a0", " ")

    m_up = re.match(r"^до\s*([\d\s']+)\s*usd$", t_lower)
    if m_up:
        hi = _parse_money_token(m_up.group(1))
        if hi > 0:
            return (t0, 0.0, float(hi), "up_to")

    m_range = re.match(
        r"^([\d\s']+)\s*[–-]\s*([\d\s']+)\s*usd$", t_lower
    )
    if m_range:
        a = _parse_money_token(m_range.group(1))
        b = _parse_money_token(m_range.group(2))
        lo, hi = (min(a, b), max(a, b))
        if lo > 0 and hi > 0:
            return (t0, float(lo), float(hi), "range")

    m_above = re.match(r"^([\d\s']+)\s*usd\s*и\s*выше$", t_lower)
    if m_above:
        lo = _parse_money_token(m_above.group(1))
        if lo > 0:
            return (t0, float(lo), float("inf"), "above")
    return None


def _price_in_band(price: float, lo: float, hi: float, kind: str) -> bool:
    if kind == "up_to":
        return 0 < price <= hi
    if kind == "range":
        return lo < price <= hi
    if kind == "above":
        return price >= lo
    return False


def parse_cars_markdown_text(raw: str, *, path: Path | None = None) -> CarsMdCatalog:
    path = path or DEFAULT_CARS_MD_PATH
    current_category: str | None = None
    current_band: tuple[str, float, float, str, str] | None = None
    categories: dict[str, list[tuple[str, list[CarMdEntry]]]] = {}

    for raw_line in raw.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        m_cat = re.match(r"^##\s+(.+)$", line)
        if m_cat:
            current_category = m_cat.group(1).strip()
            if current_category not in categories:
                categories[current_category] = []
            current_band = None
            continue
        m_band = re.match(r"^###\s+(.+)$", line)
        if m_band and current_category:
            parsed = _parse_band_h3(m_band.group(1).strip())
            current_band = parsed
            if not parsed:
                continue
            if current_category not in categories:
                categories[current_category] = []
            band_label = parsed[0]
            if not categories[current_category] or (
                categories[current_category][-1][0] != band_label
            ):
                categories[current_category].append((band_label, []))
            continue
        if line.strip().startswith("Каталог:"):
            continue
        m_item = _ITEM_LINE_RE.match(line)
        if m_item and current_category and current_band is not None:
            band_label, lo, hi, bkind = current_band
            model = m_item.group(1).strip()
            years = m_item.group(2).strip()
            entry = CarMdEntry(
                model=model,
                years_text=years,
                category_title=current_category,
                band_label=band_label,
                lo_usd=lo,
                hi_usd=hi,
                band_kind=bkind,
            )
            blocks = categories[current_category]
            if not blocks or blocks[-1][0] != band_label:
                blocks.append((band_label, []))
            blocks[-1][1].append(entry)

    return CarsMdCatalog(path=path, categories=categories)


@lru_cache(maxsize=2)
def _load_catalog_cached(path_str: str) -> CarsMdCatalog:
    p = Path(path_str)
    raw = p.read_text(encoding="utf-8")
    return parse_cars_markdown_text(raw, path=p)


def load_cars_catalog(path: Path | None = None) -> CarsMdCatalog:
    p = (path or DEFAULT_CARS_MD_PATH).resolve()
    return _load_catalog_cached(str(p))


def resolve_category_name(hint: str | None) -> str | None:
    if not hint or not (t := hint.strip()):
        return None
    t_lower = t.lower()
    for k, v in _CATEGORIES_ALIASES.items():
        if k in t_lower:
            return v
    for title in ("Электромобили", "Седан", "Кроссовер"):
        if title.lower() in t_lower:
            return title
    if any(x in t_lower for x in ("электро", "tesla", "ниссан leaf")) and "седан" not in t_lower:
        return "Электромобили"
    return None


QueryMode = Literal["full_section", "one_per_price_band", "all_in_category"]


def search_catalog_examples(
    *,
    catalog: CarsMdCatalog,
    body_or_category: str | None = None,
    budget_usd: int | None = None,
    mode: QueryMode = "full_section",
) -> tuple[str, list[CarMdEntry]]:
    """Return (human text, list of entries) for the agent tool output."""
    resolution = resolve_category_name(body_or_category) if body_or_category else None

    if mode == "all_in_category" and resolution:
        lines: list[str] = []
        all_e: list[CarMdEntry] = []
        for band_label, items in catalog.categories.get(resolution, []):
            if not items:
                continue
            lines.append(f"— {band_label} —")
            for e in items:
                lines.append(f"  • {e.model} — {e.years_text}")
            all_e.extend(items)
        if not all_e:
            return (
                f"В каталоге нет примеров для раздела «{resolution}».",
                [],
            )
        return (
            f"Полный перечень примеров из «{resolution}» (по бюджетным группам):\n"
            + "\n".join(lines),
            all_e,
        )

    if budget_usd is not None:
        cat_keys: list[str]
        if resolution:
            cat_keys = [resolution] if resolution in catalog.categories else []
        else:
            cat_keys = list(catalog.categories.keys())
        if not cat_keys:
            return ("Неизвестный тип кузова для поиска по каталогу.", [])

        collected: list[CarMdEntry] = []
        text_blocks: list[str] = []
        for cat in cat_keys:
            if cat not in catalog.categories:
                continue
            for band_label, items in catalog.categories[cat]:
                if not items:
                    continue
                e0 = items[0]
                if not _price_in_band(
                    float(budget_usd), e0.lo_usd, e0.hi_usd, e0.band_kind
                ):
                    continue
                if mode == "one_per_price_band":
                    e_pick = items[0]
                    collected.append(e_pick)
                    text_blocks.append(
                        f"«{cat}», {band_label}: {e_pick.model} — {e_pick.years_text}"
                    )
                else:
                    text_blocks.append(f"«{cat}», {band_label}:")
                    for e in items:
                        collected.append(e)
                        text_blocks.append(f"  • {e.model} — {e.years_text}")
        if not collected:
            return (
                f"В каталожных диапазонах не найдена группа, куда при бюджете "
                f"{budget_usd} USD попадает запрос. Уточните кузов или бюджет.",
                [],
            )
        head = f"Каталожные примеры: бюджет ~{budget_usd} USD (интервалы из файла):\n"
        return (head + "\n".join(text_blocks), collected)

    if resolution:
        lines = []
        all_e: list[CarMdEntry] = []
        for band_label, items in catalog.categories.get(resolution, []):
            if not items:
                continue
            if mode == "one_per_price_band":
                e = items[0]
                all_e.append(e)
                lines.append(
                    f"{band_label}: {e.model} — {e.years_text}"
                )
            else:
                lines.append(f"— {band_label} —")
                for e in items[:20]:
                    all_e.append(e)
                    lines.append(f"  • {e.model} — {e.years_text}")
        if not all_e:
            return (f"Раздел «{resolution}» пуст в каталоге.", [])
        return (
            f"Примеры из каталога «{resolution}» (ориентиры, не аукционные лоты):\n"
            + "\n".join(lines),
            all_e,
        )

    return (
        "Укажите тип (седан, кроссовер, электромобиль) и/или бюджет в USD, "
        "чтобы я нашёл примеры в нашем справочнике `cars.md`.",
        [],
    )


def recommend_catalog_examples_by_budget(
    *,
    catalog: CarsMdCatalog,
    budget_usd: int,
    limit: int = 4,
) -> tuple[str, list[CarMdEntry]]:
    """Return 3-4 diverse reference examples for a budget-only user request."""
    picked: list[CarMdEntry] = []
    seen_models: set[str] = set()
    for category, bands in catalog.categories.items():
        for _band_label, items in bands:
            if not items:
                continue
            first = items[0]
            if not _price_in_band(
                float(budget_usd), first.lo_usd, first.hi_usd, first.band_kind
            ):
                continue
            for item in items:
                key = item.model.lower()
                if key in seen_models:
                    continue
                picked.append(item)
                seen_models.add(key)
                break
            break
        if len(picked) >= limit:
            break

    if len(picked) < 3:
        for _category, bands in catalog.categories.items():
            for _band_label, items in bands:
                for item in items:
                    key = item.model.lower()
                    if key in seen_models:
                        continue
                    if _price_in_band(
                        float(budget_usd), item.lo_usd, item.hi_usd, item.band_kind
                    ):
                        picked.append(item)
                        seen_models.add(key)
                    if len(picked) >= min(limit, 4):
                        break
                if len(picked) >= min(limit, 4):
                    break
            if len(picked) >= min(limit, 4):
                break

    picked = picked[: max(3, min(limit, 4))]
    if not picked:
        return (
            f"В справочных примерах cars.md нет вариантов около {budget_usd} USD. "
            "Можно уточнить тип кузова или поискать реальные варианты на аукционе.",
            [],
        )

    lines = [
        f"- {entry.category_title}: {entry.model} — {entry.years_text} ({entry.band_label})"
        for entry in picked
    ]
    text = (
        f"Справочные примеры из cars.md под бюджет около {budget_usd} USD:\n"
        + "\n".join(lines)
        + "\nЭто ориентиры по типам авто, не реальные лоты. Могу поискать реальные варианты на аукционе по CSV."
    )
    return text, picked


def find_catalog_price_benchmark(
    *,
    catalog: CarsMdCatalog,
    make: str | None,
    model: str | None,
    year: int | None,
    fuel_type: str | None = None,
    body_style: str | None = None,
) -> CatalogPriceBenchmark | None:
    """Find a rough price benchmark in cars.md by model first, then category/year."""

    make_norm = _norm_words(make)
    model_norm = _norm_words(model)
    fuel_norm = (fuel_type or "").strip().lower()
    body_norm = (body_style or "").strip().lower()

    model_candidates: list[tuple[int, CarMdEntry]] = []
    category_candidates: list[tuple[int, CarMdEntry]] = []

    preferred_category = None
    if "electric" in fuel_norm or "электро" in fuel_norm:
        preferred_category = "Электромобили"
    elif "utility" in body_norm or "suv" in body_norm:
        preferred_category = "Кроссовер"

    for category, bands in catalog.categories.items():
        for _band_label, entries in bands:
            for entry in entries:
                entry_norm = _norm_words(entry.model)
                year_score = 20 if _entry_mentions_year(entry, year) else 0
                category_score = 10 if category == preferred_category else 0
                if (
                    model_norm
                    and model_norm in entry_norm
                    and (not make_norm or make_norm in entry_norm)
                ):
                    model_candidates.append((100 + year_score + category_score, entry))
                    continue
                if category == preferred_category and (year is None or _entry_mentions_year(entry, year)):
                    category_candidates.append((50 + year_score, entry))

    if model_candidates:
        _score, entry = max(model_candidates, key=lambda item: item[0])
        return _benchmark_from_entry(entry, match_type="model")
    if category_candidates:
        _score, entry = max(category_candidates, key=lambda item: item[0])
        return _benchmark_from_entry(entry, match_type="category")
    return None


def _benchmark_from_entry(entry: CarMdEntry, *, match_type: str) -> CatalogPriceBenchmark:
    lo = int(entry.lo_usd)
    if entry.hi_usd == float("inf"):
        hi = int(entry.lo_usd * 1.25)
    else:
        hi = int(entry.hi_usd)
    return CatalogPriceBenchmark(entry=entry, lo_usd=lo, hi_usd=hi, match_type=match_type)


def _norm_words(value: str | None) -> str:
    return re.sub(r"[^a-zа-я0-9]+", "", (value or "").lower(), flags=re.UNICODE)


def _entry_mentions_year(entry: CarMdEntry, year: int | None) -> bool:
    if year is None:
        return False
    years = {int(x) for x in re.findall(r"\b(20\d{2})\b", entry.years_text)}
    return year in years
