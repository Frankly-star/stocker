"""PositionStore: unified position management with dual-mode support.

Data isolation
--------------
Each ``broker_type`` gets its own data directory to prevent cross-contamination:

- ``futu``      → ``data/futu/positions.json``
- ``simulated`` → ``data/simulated/positions.json``
- ``backtest``  → ``data/backtest/positions.json``

Use :func:`create_position_store` to automatically resolve the correct path
based on the current configuration.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from stocker.broker.models import Position, PositionSource
from stocker.utils.helpers import atomic_json_write, json_read

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path resolution helpers
# ---------------------------------------------------------------------------

_VALID_BROKER_TYPES = {"futu", "simulated", "backtest"}


def _resolve_data_dir(broker_type: str, base_dir: str = "data") -> Path:
    """Return the data directory for a given broker_type.

    Layout::

        data/
        ├── futu/
        │   ├── positions.json
        │   └── trades.json
        ├── simulated/
        │   ├── positions.json
        │   └── trades.json
        └── backtest/
            ├── positions.json
            └── trades.json
    """
    bt = broker_type.lower()
    if bt not in _VALID_BROKER_TYPES:
        logger.warning("Unknown broker_type %r — defaulting to 'simulated'", bt)
        bt = "simulated"
    return Path(base_dir) / bt


def create_position_store(broker_type: str | None = None, base_dir: str = "data") -> "PositionStore":
    """Factory: create a PositionStore isolated by broker_type.

    If *broker_type* is ``None``, it is read from the current stocker config.
    """
    if broker_type is None:
        try:
            from stocker.config import load_config
            cfg = load_config()
            broker_type = cfg.get("broker_type", "simulated")
        except Exception:
            broker_type = "simulated"

    data_dir = _resolve_data_dir(broker_type, base_dir)
    filepath = data_dir / "positions.json"
    logger.debug("PositionStore → %s", filepath)
    return PositionStore(filepath=str(filepath), broker_type=broker_type)


class PositionStore:
    """Manages all positions with source tracking and persistence."""

    def __init__(self, filepath: str = "data/positions.json", broker_type: str = "") -> None:
        self._filepath = Path(filepath)
        self._filepath.parent.mkdir(parents=True, exist_ok=True)
        self._broker_type = broker_type
        self._positions: dict[str, Position] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        data = json_read(self._filepath, default=[])
        for item in data:
            try:
                pos = Position(**item)
                self._positions[pos.ticker] = pos
            except Exception as e:
                logger.warning("Failed to load position: %s", e)

    def _save(self) -> None:
        data = [p.model_dump(mode="json") for p in self._positions.values()]
        atomic_json_write(self._filepath, data)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get(self, ticker: str) -> Position | None:
        return self._positions.get(ticker.upper())

    def list_all(self) -> list[Position]:
        return list(self._positions.values())

    def add(
        self,
        ticker: str,
        quantity: int,
        avg_cost: float,
        source: PositionSource = PositionSource.MANUAL_IMPORT,
    ) -> Position:
        """Add or update a position."""
        ticker = ticker.upper()
        existing = self._positions.get(ticker)
        if existing:
            new_qty = existing.quantity + quantity
            existing.avg_cost = (
                (existing.avg_cost * existing.quantity + avg_cost * quantity) / new_qty
                if new_qty > 0 else 0
            )
            existing.quantity = new_qty
            existing.source = source
        else:
            existing = Position(
                ticker=ticker, quantity=quantity, avg_cost=avg_cost, source=source,
            )
            self._positions[ticker] = existing
        self._save()
        return existing

    def remove(self, ticker: str) -> bool:
        ticker = ticker.upper()
        if ticker in self._positions:
            del self._positions[ticker]
            self._save()
            return True
        return False

    # ------------------------------------------------------------------
    # Broker sync (diff merge)
    # ------------------------------------------------------------------

    def sync_from_broker(self, broker_positions: list[Position]) -> dict:
        """Merge broker positions with local store.

        - New positions from broker are added
        - Updated quantities are synced
        - manual_import positions are NOT deleted by sync
        - broker_synced positions not in broker list are removed

        Returns summary of changes.
        """
        changes = {"added": [], "updated": [], "removed": []}
        broker_tickers = {p.ticker.upper() for p in broker_positions}

        # Add/update from broker
        for bp in broker_positions:
            t = bp.ticker.upper()
            bp.source = PositionSource.BROKER_SYNCED
            bp.last_synced_at = datetime.now()

            existing = self._positions.get(t)
            if not existing:
                self._positions[t] = bp
                changes["added"].append(t)
            elif existing.source == PositionSource.BROKER_SYNCED:
                existing.quantity = bp.quantity
                existing.avg_cost = bp.avg_cost
                existing.current_price = bp.current_price
                existing.last_synced_at = datetime.now()
                changes["updated"].append(t)

        # Remove broker_synced positions no longer in broker
        to_remove = [
            t for t, p in self._positions.items()
            if p.source == PositionSource.BROKER_SYNCED and t not in broker_tickers
        ]
        for t in to_remove:
            del self._positions[t]
            changes["removed"].append(t)

        self._save()
        return changes

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_summary(self) -> dict:
        positions = self.list_all()
        total_value = sum(p.current_price * p.quantity for p in positions)
        total_pnl = sum(p.unrealized_pnl for p in positions)
        return {
            "count": len(positions),
            "total_value": total_value,
            "total_unrealized_pnl": total_pnl,
            "tickers": [p.ticker for p in positions],
        }
