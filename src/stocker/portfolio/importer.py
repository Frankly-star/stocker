"""PositionImporter: CSV import and diff merge logic."""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from stocker.broker.models import PositionSource
from stocker.portfolio.store import PositionStore

logger = logging.getLogger(__name__)


class PositionImporter:
    """Import positions from CSV files or manual input."""

    def __init__(self, store: PositionStore) -> None:
        self._store = store

    def import_csv(self, filepath: str) -> dict:
        """Import positions from a CSV file.

        Expected columns: ticker, quantity, avg_cost
        Optional columns: market_type

        Returns summary of imported positions.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"CSV file not found: {filepath}")

        imported = []
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = row.get("ticker", "").strip().upper()
                if not ticker:
                    continue
                try:
                    quantity = int(row.get("quantity", 0))
                    avg_cost = float(row.get("avg_cost", 0))
                except (ValueError, TypeError):
                    logger.warning("Invalid data for %s, skipping", ticker)
                    continue

                self._store.add(
                    ticker=ticker,
                    quantity=quantity,
                    avg_cost=avg_cost,
                    source=PositionSource.CSV_IMPORT,
                )
                imported.append(ticker)

        logger.info("Imported %d positions from %s", len(imported), filepath)
        return {"imported": imported, "count": len(imported)}

    def add_manual(self, ticker: str, quantity: int, avg_cost: float) -> dict:
        """Add a position manually."""
        pos = self._store.add(
            ticker=ticker, quantity=quantity, avg_cost=avg_cost,
            source=PositionSource.MANUAL_IMPORT,
        )
        return {"ticker": pos.ticker, "quantity": pos.quantity, "avg_cost": pos.avg_cost}
