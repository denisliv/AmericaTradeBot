"""In-memory cache for salesdata.csv, invalidated by file mtime.

Чтение и парсинг CSV выполняются в отдельном потоке, чтобы не блокировать
event loop. Конкурентные обращения сериализуются через asyncio.Lock, поэтому
тяжёлый парсинг происходит только однократно после обновления файла.
"""

from __future__ import annotations

import asyncio
import csv
import logging
from pathlib import Path
from typing import Any

from app.infrastructure.paths import SALESDATA_CSV

logger = logging.getLogger(__name__)


class SalesDataCache:
    def __init__(self, path: Path = SALESDATA_CSV) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._rows: list[dict[str, Any]] | None = None
        self._mtime: float | None = None

    async def get_rows(self) -> list[dict[str, Any]]:
        """Return cached CSV rows, reloading from disk on mtime change."""
        try:
            current_mtime = self._path.stat().st_mtime
        except FileNotFoundError:
            logger.warning("Salesdata CSV not found at %s", self._path)
            return []

        if self._rows is not None and self._mtime == current_mtime:
            return self._rows

        async with self._lock:
            try:
                current_mtime = self._path.stat().st_mtime
            except FileNotFoundError:
                return []
            if self._rows is not None and self._mtime == current_mtime:
                return self._rows
            rows = await asyncio.to_thread(self._read_rows, self._path)
            self._rows = rows
            self._mtime = current_mtime
            logger.info("Salesdata CSV reloaded: %d rows", len(rows))
            return rows

    def invalidate(self) -> None:
        self._rows = None
        self._mtime = None

    @staticmethod
    def _read_rows(path: Path) -> list[dict[str, Any]]:
        with path.open("r", encoding="utf-8", newline="") as csvfile:
            return list(csv.DictReader(csvfile))


sales_data_cache = SalesDataCache()
