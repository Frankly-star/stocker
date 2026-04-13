"""Watchlist data models: WatchlistItem and ScanFilter."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from stocker.analysis.models import SwingSignal


class WatchlistItem(BaseModel):
    """A stock in the user's watchlist (not necessarily held)."""

    ticker: str
    name: str = ""
    market: str = ""  # HK / US / CN
    tags: list[str] = Field(default_factory=list)
    added_at: datetime = Field(default_factory=datetime.now)
    last_scanned_at: datetime | None = None
    latest_signal: SwingSignal | None = None  # typed SwingSignal (Pydantic handles dict <-> model)
    notes: str = ""


class ScanFilter(BaseModel):
    """Filter criteria for watchlist scanning.

    All fields are optional — only non-None fields are applied.
    """

    rsi_below: float | None = None  # RSI oversold threshold (e.g. 30)
    rsi_above: float | None = None  # RSI overbought threshold (e.g. 70)
    macd_cross_up: bool | None = None  # MACD histogram crossing above zero
    macd_cross_down: bool | None = None  # MACD histogram crossing below zero
    bb_position_below: float | None = None  # BB position < threshold (0-1)
    bb_position_above: float | None = None  # BB position > threshold (0-1)
    near_support: bool | None = None  # Price near support level
    near_resistance: bool | None = None  # Price near resistance level
    min_signal_strength: float = 0.0  # Minimum signal strength (0-100) to include
    market_environment: str | None = None  # range_bound / trending_up / trending_down / volatile
