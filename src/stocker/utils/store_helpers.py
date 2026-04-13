"""Store helpers: shared path resolution and broker_type utilities.

Centralizes the data-directory layout logic that was previously duplicated
across PositionStore, WatchlistStore, SwingTradeStore, and TradeStore.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

VALID_BROKER_TYPES: set[str] = {"futu", "simulated", "backtest"}


def resolve_data_dir(broker_type: str, base_dir: str = "data") -> Path:
    """Return the data directory for a given broker_type.

    Layout::

        data/
        ├── futu/
        │   ├── positions.json
        │   ├── watchlist.json
        │   └── ...
        ├── simulated/
        └── backtest/
    """
    bt = broker_type.lower()
    if bt not in VALID_BROKER_TYPES:
        logger.warning("Unknown broker_type %r — defaulting to 'simulated'", bt)
        bt = "simulated"
    return Path(base_dir) / bt


def resolve_broker_type(fallback: str = "simulated") -> str:
    """Read broker_type from stocker config, falling back to *fallback*."""
    try:
        from stocker.config import load_config
        cfg = load_config()
        return cfg.get("broker_type", fallback)
    except Exception:
        return fallback


def create_store_path(
    broker_type: str | None,
    filename: str,
    base_dir: str = "data",
) -> Path:
    """Resolve the full JSON file path for a store.

    If *broker_type* is ``None``, it is auto-detected from configuration.
    """
    if broker_type is None:
        broker_type = resolve_broker_type()
    data_dir = resolve_data_dir(broker_type, base_dir)
    return data_dir / filename
