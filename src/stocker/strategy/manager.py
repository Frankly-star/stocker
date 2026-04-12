"""StrategyManager: singleton that owns the active StrategyConfig.

Responsibilities:
  - Load active strategy from ``data/strategies/active.json`` on first access
  - Persist changes to disk atomically
  - Support switching between built-in presets
  - Provide a module-level ``get_strategy()`` shortcut used by all consumers
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from stocker.strategy.models import StrategyConfig
from stocker.strategy.presets import PRESETS, list_preset_names
from stocker.strategy.validators import validate_strategy

logger = logging.getLogger(__name__)

_STRATEGIES_DIR = Path("data/strategies")
_ACTIVE_FILE = _STRATEGIES_DIR / "active.json"


class StrategyManager:
    """Thread-safe singleton that manages the active strategy configuration."""

    _instance: "StrategyManager | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "StrategyManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._initialized = False
                    cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._rw_lock = threading.RLock()
        self._config: StrategyConfig = StrategyConfig()  # balanced default
        self._load_from_disk()
        self._initialized = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self) -> StrategyConfig:
        """Return the active strategy config (read-only snapshot)."""
        with self._rw_lock:
            return self._config.model_copy(deep=True)

    def update(self, partial: dict[str, Any]) -> StrategyConfig:
        """Merge *partial* into the active config, validate, persist, and return new config.

        ``partial`` may contain nested dicts, e.g.
        ``{"technical": {"rsi_window": 21}, "risk": {"stop_loss_min_pct": 3.0}}``.

        Raises ``ValueError`` on validation failure.
        """
        with self._rw_lock:
            current = self._config.model_dump()
            _deep_merge(current, partial)
            new_config = StrategyConfig(**current).with_timestamp()
            # Pydantic model_validators run during construction above.
            # Additional business-rule warnings (non-fatal) are logged.
            warnings = validate_strategy(new_config)
            for w in warnings:
                logger.warning("[Strategy] %s", w)
            self._config = new_config
            self._persist()
            logger.info("[Strategy] Updated: %s", new_config.name)
            return self._config.model_copy(deep=True)

    def switch_preset(self, name: str) -> StrategyConfig:
        """Switch to a built-in preset by name.

        Raises ``KeyError`` if preset not found.
        """
        preset = PRESETS.get(name)
        if preset is None:
            raise KeyError(f"Unknown preset: {name!r}. Available: {list_preset_names()}")
        with self._rw_lock:
            self._config = preset.model_copy(deep=True).with_timestamp()
            self._persist()
            logger.info("[Strategy] Switched to preset: %s", name)
            return self._config.model_copy(deep=True)

    def reset(self) -> StrategyConfig:
        """Reset to the default balanced preset."""
        return self.switch_preset("balanced")

    def list_presets(self) -> dict[str, dict]:
        """Return all presets as serializable dicts."""
        return {
            name: cfg.model_dump(mode="json")
            for name, cfg in PRESETS.items()
        }

    def get_warnings(self) -> list[str]:
        """Return business-rule warnings for the current config."""
        with self._rw_lock:
            return validate_strategy(self._config)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self) -> None:
        """Write active config to JSON file (atomic via temp+rename)."""
        try:
            _STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)
            data = self._config.model_dump(mode="json")
            tmp = _ACTIVE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(_ACTIVE_FILE)
            logger.debug("[Strategy] Persisted to %s", _ACTIVE_FILE)
        except Exception as e:
            logger.error("[Strategy] Failed to persist: %s", e)

    def _load_from_disk(self) -> None:
        """Load active.json if it exists, otherwise use default."""
        if _ACTIVE_FILE.exists():
            try:
                raw = json.loads(_ACTIVE_FILE.read_text(encoding="utf-8"))
                self._config = StrategyConfig(**raw)
                logger.info("[Strategy] Loaded from %s (name=%s)", _ACTIVE_FILE, self._config.name)
                return
            except Exception as e:
                logger.warning("[Strategy] Failed to load %s: %s — using defaults", _ACTIVE_FILE, e)
        # First run or corrupted file — persist defaults
        self._config = StrategyConfig().with_timestamp()
        self._persist()
        logger.info("[Strategy] Initialized with defaults (balanced)")

    # ------------------------------------------------------------------
    # Testing helper
    # ------------------------------------------------------------------

    @classmethod
    def _reset_singleton(cls) -> None:
        """Reset the singleton (for testing only)."""
        with cls._lock:
            cls._instance = None


# ---------------------------------------------------------------------------
# Module-level shortcut
# ---------------------------------------------------------------------------

def get_strategy() -> StrategyConfig:
    """Convenience function — returns the current active strategy config."""
    return StrategyManager().get()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge *override* into *base* in-place."""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
