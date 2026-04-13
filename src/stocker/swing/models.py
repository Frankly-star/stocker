"""Swing trade data models: SwingTrade and SwingTradeStats."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class SwingTradeStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class SwingTrade(BaseModel):
    """A complete swing trade cycle: entry -> hold -> exit."""

    trade_id: str = Field(default_factory=lambda: f"SW-{uuid4().hex[:8]}")
    ticker: str
    status: SwingTradeStatus = SwingTradeStatus.OPEN

    # Entry
    entry_time: datetime = Field(default_factory=datetime.now)
    entry_price: float = 0.0
    quantity: int = 0

    # Exit (populated when closed)
    exit_time: datetime | None = None
    exit_price: float | None = None

    # P&L (auto-calculated on close)
    pnl: float = 0.0  # absolute profit/loss
    pnl_pct: float = 0.0  # percentage
    hold_days: int = 0

    # Metadata
    signal_source: str = ""  # description of the triggering signal
    stop_loss: float | None = None
    take_profit: float | None = None
    notes: str = ""

    def close(self, exit_price: float, exit_time: datetime | None = None) -> None:
        """Close this swing trade and calculate P&L."""
        self.status = SwingTradeStatus.CLOSED
        self.exit_price = exit_price
        self.exit_time = exit_time or datetime.now()
        if self.entry_price > 0 and self.quantity > 0:
            self.pnl = (exit_price - self.entry_price) * self.quantity
            self.pnl_pct = (exit_price - self.entry_price) / self.entry_price * 100
        self.hold_days = (self.exit_time - self.entry_time).days


class SwingTradeStats(BaseModel):
    """Aggregated statistics for swing trade review."""

    total_trades: int = 0
    open_trades: int = 0
    closed_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0  # percentage
    total_pnl: float = 0.0
    avg_pnl: float = 0.0
    avg_pnl_pct: float = 0.0
    avg_hold_days: float = 0.0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0  # total_wins / total_losses
