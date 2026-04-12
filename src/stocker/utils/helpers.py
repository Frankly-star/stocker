"""Utility functions: atomic JSON I/O, date helpers, ticker validation."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Atomic JSON I/O (write to temp then rename to prevent corruption)
# ---------------------------------------------------------------------------

def atomic_json_write(filepath: str | Path, data: Any) -> None:
    """Write JSON atomically: write to temp file, then rename."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=filepath.parent, suffix=".tmp", prefix=filepath.stem
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        # Atomic rename (same filesystem)
        os.replace(tmp_path, filepath)
    except Exception:
        # Clean up temp file on error
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def json_read(filepath: str | Path, default: Any = None) -> Any:
    """Read JSON file, return default if not found or invalid."""
    filepath = Path(filepath)
    if not filepath.exists():
        return default if default is not None else {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default if default is not None else {}


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def today_str() -> str:
    """Return today's date as YYYY-MM-DD string."""
    return date.today().strftime("%Y-%m-%d")


def parse_date(date_input: str | date | datetime) -> datetime:
    """Parse various date formats to datetime."""
    if isinstance(date_input, datetime):
        return date_input
    if isinstance(date_input, date):
        return datetime.combine(date_input, datetime.min.time())
    return datetime.strptime(date_input, "%Y-%m-%d")


def is_trading_day(d: date | datetime) -> bool:
    """Check if a date is a weekday (rough trading day check)."""
    if isinstance(d, datetime):
        d = d.date()
    return d.weekday() < 5


def get_next_weekday(d: date | datetime) -> date:
    """Get the next weekday (Mon-Fri) from the given date."""
    if isinstance(d, datetime):
        d = d.date()
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


# ---------------------------------------------------------------------------
# Ticker validation
# ---------------------------------------------------------------------------

_TICKER_PATTERN = re.compile(r"^[A-Z0-9.\-]{1,10}$", re.IGNORECASE)


def validate_ticker(ticker: str) -> str:
    """Validate and normalize a ticker symbol. Raises ValueError if invalid."""
    ticker = ticker.strip().upper()
    if not _TICKER_PATTERN.match(ticker):
        raise ValueError(f"Invalid ticker symbol: {ticker!r}")
    return ticker
