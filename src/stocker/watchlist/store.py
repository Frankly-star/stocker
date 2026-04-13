"""WatchlistStore: persistent custom stock pool management.

Data isolation follows the same pattern as PositionStore:
  - ``futu``      -> ``data/futu/watchlist.json``
  - ``simulated`` -> ``data/simulated/watchlist.json``
  - ``backtest``  -> ``data/backtest/watchlist.json``
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

from stocker.utils.base_store import BaseJsonStore
from stocker.utils.store_helpers import create_store_path
from stocker.watchlist.models import WatchlistItem

logger = logging.getLogger(__name__)


def create_watchlist_store(
    broker_type: str | None = None, base_dir: str = "data"
) -> "WatchlistStore":
    """Factory: create a WatchlistStore isolated by broker_type."""
    filepath = create_store_path(broker_type, "watchlist.json", base_dir)
    return WatchlistStore(filepath=str(filepath))


class WatchlistStore(BaseJsonStore[WatchlistItem]):
    """Manages the user's watchlist with JSON persistence."""

    def __init__(self, filepath: str = "data/watchlist.json") -> None:
        super().__init__(filepath=filepath, model_class=WatchlistItem, key_field="ticker")

    # ------------------------------------------------------------------
    # Override _load to uppercase keys
    # ------------------------------------------------------------------

    def _load(self) -> None:
        from stocker.utils.helpers import json_read
        data = json_read(self._filepath, default=[])
        self._data = {}
        for item in data:
            try:
                wi = WatchlistItem(**item)
                self._data[wi.ticker.upper()] = wi
            except Exception as e:
                logger.warning("Failed to load watchlist item: %s", e)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get(self, ticker: str) -> WatchlistItem | None:
        return self._data.get(ticker.upper())

    def list_all(self) -> list[WatchlistItem]:
        return list(self._data.values())

    def add(
        self,
        ticker: str,
        name: str = "",
        market: str = "",
        tags: list[str] | None = None,
    ) -> WatchlistItem:
        """Add a stock to the watchlist (or update if exists)."""
        ticker = ticker.upper()
        existing = self._data.get(ticker)
        if existing:
            if name:
                existing.name = name
            if market:
                existing.market = market
            if tags is not None:
                existing.tags = tags
        else:
            existing = WatchlistItem(
                ticker=ticker,
                name=name,
                market=market,
                tags=tags or [],
            )
            self._data[ticker] = existing
        self._save()
        return existing

    def remove(self, ticker: str) -> bool:
        ticker = ticker.upper()
        if ticker in self._data:
            del self._data[ticker]
            self._save()
            return True
        return False

    def update_signal(self, ticker: str, signal_data: dict) -> None:
        """Update the latest signal snapshot for a watchlist item."""
        ticker = ticker.upper()
        item = self._data.get(ticker)
        if item:
            item.latest_signal = signal_data
            item.last_scanned_at = datetime.now()
            self._save()

    def import_csv(self, filepath: str) -> dict:
        """Import watchlist items from CSV. Expected columns: ticker, name, market, tags."""
        fp = Path(filepath)
        if not fp.exists():
            raise FileNotFoundError(f"CSV file not found: {filepath}")

        imported = []
        with open(fp, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = row.get("ticker", "").strip().upper()
                if not ticker:
                    continue
                name = row.get("name", "").strip()
                market = row.get("market", "").strip()
                tags_str = row.get("tags", "")
                tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
                self.add(ticker=ticker, name=name, market=market, tags=tags)
                imported.append(ticker)

        logger.info("Imported %d watchlist items from %s", len(imported), filepath)
        return {"imported": imported, "count": len(imported)}

    def get_tickers(self) -> list[str]:
        """Return list of all tickers in the watchlist."""
        return [wi.ticker for wi in self._data.values()]

    def count(self) -> int:
        return len(self._data)
