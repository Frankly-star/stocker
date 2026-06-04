"""Path helpers for the Stocker evolution runtime."""

from __future__ import annotations

import os
from pathlib import Path


def data_root(base_dir: str | Path | None = None) -> Path:
    """Return the root directory used by evolution stores."""
    if base_dir is not None:
        return Path(base_dir) / "evolution"
    try:
        from stocker.config import load_config

        cfg = load_config()
        root = cfg.get("data_dir", "data")
    except Exception:
        root = os.getenv("STOCKER_DATA_DIR", "data")
    return Path(root) / "evolution"


def skills_root(base_dir: str | Path | None = None) -> Path:
    return data_root(base_dir) / "skills"


def traces_root(base_dir: str | Path | None = None) -> Path:
    return data_root(base_dir) / "traces"


def reviews_root(base_dir: str | Path | None = None) -> Path:
    return data_root(base_dir) / "reviews"


def patches_root(base_dir: str | Path | None = None) -> Path:
    return data_root(base_dir) / "patches"
