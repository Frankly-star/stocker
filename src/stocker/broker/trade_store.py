"""TradeStore: persistent trade history (replaces in-memory _trade_history).

Data isolation:
  - ``data/{broker_type}/trades.json``
"""

from __future__ import annotations

import logging

from stocker.broker.models import TradeRecord
from stocker.utils.base_store import BaseJsonStore
from stocker.utils.store_helpers import create_store_path

logger = logging.getLogger(__name__)


def create_trade_store(
    broker_type: str | None = None, base_dir: str = "data"
) -> "TradeStore":
    """Factory: create a TradeStore isolated by broker_type."""
    filepath = create_store_path(broker_type, "trades.json", base_dir)
    return TradeStore(filepath=str(filepath))


class TradeStore(BaseJsonStore[TradeRecord]):
    """Persistent trade history with JSON storage."""

    MAX_RECORDS = 1000  # keep last N records

    def __init__(self, filepath: str = "data/trades.json") -> None:
        super().__init__(filepath=filepath, model_class=TradeRecord, key_field=None)

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def add(self, record: dict | TradeRecord) -> None:
        """Add a trade record (accepts dict for backward compatibility)."""
        if isinstance(record, dict):
            record = TradeRecord(**record)
        self._append(record)
        self._truncate(self.MAX_RECORDS)
        self._save()

    def list_recent(self, limit: int = 100) -> list[dict]:
        """Return recent trades as dicts (most recent first)."""
        items = self._list_data[-limit:]
        return [r.model_dump(mode="json") for r in reversed(items)]

    def list_all(self) -> list[TradeRecord]:
        return list(self._list_data)

    def count(self) -> int:
        return len(self._list_data)

    def clear(self) -> None:
        self._list_data = []
        self._save()
