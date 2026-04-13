"""BaseJsonStore: generic JSON-persisted store base class.

Provides the shared persistence skeleton used by PositionStore,
WatchlistStore, SwingTradeStore, and TradeStore.

Two storage modes are supported:

- **keyed** (default): items are stored in a ``dict[str, T]`` keyed by
  a field extracted via ``key_field``.  Suitable for positions, watchlist
  items, and swing trades where each record has a unique identifier.

- **list** (``key_field=None``): items are stored in a plain ``list[T]``.
  Suitable for append-only stores like trade history.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel

from stocker.utils.helpers import atomic_json_write, json_read

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class BaseJsonStore(Generic[T]):
    """JSON-persisted store with generic model support.

    Parameters
    ----------
    filepath:
        Path to the JSON file.
    model_class:
        The Pydantic model class for items.
    key_field:
        Name of the model field used as dict key.
        Set to ``None`` for list-mode (append-only) storage.
    """

    def __init__(
        self,
        filepath: str,
        model_class: type[T],
        key_field: str | None = None,
    ) -> None:
        self._filepath = Path(filepath)
        self._filepath.parent.mkdir(parents=True, exist_ok=True)
        self._model_class = model_class
        self._key_field = key_field

        # Internal storage — either dict or list depending on mode
        if key_field is not None:
            self._data: dict[str, T] = {}
        else:
            self._list_data: list[T] = []

        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        raw = json_read(self._filepath, default=[])

        if self._key_field is not None:
            # Keyed dict mode
            self._data = {}
            for item in raw:
                try:
                    obj = self._model_class(**item)
                    key = str(getattr(obj, self._key_field))
                    self._data[key] = obj
                except Exception as e:
                    logger.warning("Failed to load %s item: %s", self._model_class.__name__, e)
        else:
            # List mode
            if not isinstance(raw, list):
                raw = []
            self._list_data = []
            for item in raw:
                try:
                    self._list_data.append(self._model_class(**item))
                except Exception as e:
                    logger.warning("Failed to load %s item: %s", self._model_class.__name__, e)

    def _save(self) -> None:
        if self._key_field is not None:
            data = [obj.model_dump(mode="json") for obj in self._data.values()]
        else:
            data = [obj.model_dump(mode="json") for obj in self._list_data]
        atomic_json_write(self._filepath, data)

    # ------------------------------------------------------------------
    # Keyed-mode helpers
    # ------------------------------------------------------------------

    def get(self, key: str) -> T | None:
        """Get an item by key (keyed mode only)."""
        if self._key_field is None:
            raise TypeError("get() is not supported in list mode")
        return self._data.get(key)

    def list_all(self) -> list[T]:
        """Return all items."""
        if self._key_field is not None:
            return list(self._data.values())
        return list(self._list_data)

    def _put(self, key: str, item: T) -> None:
        """Insert or replace an item by key (keyed mode only)."""
        if self._key_field is None:
            raise TypeError("_put() is not supported in list mode")
        self._data[key] = item

    def _remove(self, key: str) -> bool:
        """Remove an item by key (keyed mode only). Returns True if found."""
        if self._key_field is None:
            raise TypeError("_remove() is not supported in list mode")
        if key in self._data:
            del self._data[key]
            return True
        return False

    def count(self) -> int:
        if self._key_field is not None:
            return len(self._data)
        return len(self._list_data)

    # ------------------------------------------------------------------
    # List-mode helpers
    # ------------------------------------------------------------------

    def _append(self, item: T) -> None:
        """Append an item (list mode only)."""
        if self._key_field is not None:
            raise TypeError("_append() is not supported in keyed mode")
        self._list_data.append(item)

    def _truncate(self, max_items: int) -> None:
        """Keep only the last *max_items* items (list mode only)."""
        if self._key_field is not None:
            raise TypeError("_truncate() is not supported in keyed mode")
        if len(self._list_data) > max_items:
            self._list_data = self._list_data[-max_items:]
