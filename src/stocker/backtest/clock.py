"""BacktestClock: virtual clock engine for backtesting.

The single source of truth for "current time" during a backtest run.
All modules (data_store, broker, runtime) use clock.now() to prevent
look-ahead bias — no future data can be accessed.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)


class BacktestClock:
    """Virtual clock that advances along a pre-built timeline of trading bars."""

    def __init__(
        self,
        start: str,
        end: str,
        freq: str = "daily",
    ) -> None:
        """
        Args:
            start: Start date ``yyyy-mm-dd``.
            end: End date ``yyyy-mm-dd``.
            freq: Bar frequency — ``"daily"`` or ``"weekly"``.
        """
        self._start = pd.Timestamp(start)
        self._end = pd.Timestamp(end)
        self._freq = freq
        self._timeline: list[pd.Timestamp] = self._build_timeline()
        self._index: int = -1  # before first bar

    # ------------------------------------------------------------------
    # Timeline construction
    # ------------------------------------------------------------------

    def _build_timeline(self) -> list[pd.Timestamp]:
        """Generate trading-day timeline between start and end."""
        freq_map = {"daily": "B", "weekly": "W-FRI"}  # B = business days
        pd_freq = freq_map.get(self._freq, "B")
        timeline = pd.date_range(start=self._start, end=self._end, freq=pd_freq)
        ts_list = list(timeline)
        logger.info(
            "BacktestClock: %d bars from %s to %s (freq=%s)",
            len(ts_list),
            self._start.date(),
            self._end.date(),
            self._freq,
        )
        return ts_list

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def advance(self) -> datetime | None:
        """Advance to the next bar. Returns the new current time, or None if finished."""
        self._index += 1
        if self._index >= len(self._timeline):
            return None
        return self._timeline[self._index].to_pydatetime()

    def now(self) -> datetime:
        """Current virtual time. Raises if clock has not been advanced yet."""
        if self._index < 0:
            return self._start.to_pydatetime()
        if self._index >= len(self._timeline):
            return self._end.to_pydatetime()
        return self._timeline[self._index].to_pydatetime()

    def now_str(self) -> str:
        """Current time as ``yyyy-mm-dd`` string."""
        return self.now().strftime("%Y-%m-%d")

    def is_finished(self) -> bool:
        """Whether the clock has advanced past the last bar."""
        return self._index >= len(self._timeline)

    def reset(self) -> None:
        """Reset clock to before the first bar."""
        self._index = -1

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def bar_index(self) -> int:
        """Current bar index (0-based). -1 if not started."""
        return self._index

    @property
    def total_bars(self) -> int:
        return len(self._timeline)

    @property
    def progress_pct(self) -> float:
        if not self._timeline:
            return 100.0
        return min(100.0, max(0.0, (self._index + 1) / len(self._timeline) * 100))

    @property
    def timeline(self) -> list[pd.Timestamp]:
        """Full timeline (read-only)."""
        return list(self._timeline)
