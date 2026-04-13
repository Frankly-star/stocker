"""SwingTradeStore: persistent swing trade lifecycle management.

Data isolation:
  - ``data/{broker_type}/swing_trades.json``
"""

from __future__ import annotations

import logging
from datetime import datetime

from stocker.swing.models import SwingTrade, SwingTradeStats, SwingTradeStatus
from stocker.utils.base_store import BaseJsonStore
from stocker.utils.store_helpers import create_store_path

logger = logging.getLogger(__name__)


def create_swing_store(
    broker_type: str | None = None, base_dir: str = "data"
) -> "SwingTradeStore":
    """Factory: create a SwingTradeStore isolated by broker_type."""
    filepath = create_store_path(broker_type, "swing_trades.json", base_dir)
    return SwingTradeStore(filepath=str(filepath))


class SwingTradeStore(BaseJsonStore[SwingTrade]):
    """Manages swing trade records with JSON persistence."""

    def __init__(self, filepath: str = "data/swing_trades.json") -> None:
        super().__init__(filepath=filepath, model_class=SwingTrade, key_field="trade_id")

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def open_trade(
        self,
        ticker: str,
        entry_price: float,
        quantity: int = 0,
        signal_source: str = "",
        stop_loss: float | None = None,
        take_profit: float | None = None,
        notes: str = "",
    ) -> SwingTrade:
        """Open a new swing trade."""
        trade = SwingTrade(
            ticker=ticker.upper(),
            entry_price=entry_price,
            quantity=quantity,
            signal_source=signal_source,
            stop_loss=stop_loss,
            take_profit=take_profit,
            notes=notes,
        )
        self._data[trade.trade_id] = trade
        self._save()
        logger.info("Opened swing trade %s: %s @ %.2f x%d",
                     trade.trade_id, ticker, entry_price, quantity)
        return trade

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        exit_time: datetime | None = None,
        notes: str = "",
    ) -> SwingTrade | None:
        """Close an existing swing trade and calculate P&L."""
        trade = self._data.get(trade_id)
        if not trade:
            logger.warning("Swing trade %s not found", trade_id)
            return None
        if trade.status == SwingTradeStatus.CLOSED:
            logger.warning("Swing trade %s is already closed", trade_id)
            return trade

        trade.close(exit_price, exit_time)
        if notes:
            trade.notes = (trade.notes + " | " + notes) if trade.notes else notes
        self._save()
        logger.info("Closed swing trade %s: %s exit @ %.2f, P&L=%.2f (%.2f%%)",
                     trade.trade_id, trade.ticker, exit_price, trade.pnl, trade.pnl_pct)
        return trade

    def get(self, trade_id: str) -> SwingTrade | None:
        return self._data.get(trade_id)

    def list_all(self, status: str | None = None, ticker: str | None = None) -> list[SwingTrade]:
        """List swing trades with optional filters."""
        trades = list(self._data.values())
        if status:
            trades = [t for t in trades if t.status.value == status]
        if ticker:
            trades = [t for t in trades if t.ticker == ticker.upper()]
        return sorted(trades, key=lambda t: t.entry_time, reverse=True)

    def list_open(self) -> list[SwingTrade]:
        return self.list_all(status="open")

    def list_closed(self) -> list[SwingTrade]:
        return self.list_all(status="closed")

    def get_stats(self, ticker: str | None = None) -> SwingTradeStats:
        """Calculate aggregated statistics for swing trade review."""
        closed = self.list_all(status="closed", ticker=ticker)
        all_trades = self.list_all(ticker=ticker)

        stats = SwingTradeStats(
            total_trades=len(all_trades),
            open_trades=sum(1 for t in all_trades if t.status == SwingTradeStatus.OPEN),
            closed_trades=len(closed),
        )

        if not closed:
            return stats

        wins = [t for t in closed if t.pnl > 0]
        losses = [t for t in closed if t.pnl <= 0]

        stats.winning_trades = len(wins)
        stats.losing_trades = len(losses)
        stats.win_rate = (len(wins) / len(closed) * 100) if closed else 0

        stats.total_pnl = sum(t.pnl for t in closed)
        stats.avg_pnl = stats.total_pnl / len(closed)
        stats.avg_pnl_pct = sum(t.pnl_pct for t in closed) / len(closed)
        stats.avg_hold_days = sum(t.hold_days for t in closed) / len(closed)

        if closed:
            stats.best_trade_pnl = max(t.pnl for t in closed)
            stats.worst_trade_pnl = min(t.pnl for t in closed)

        stats.avg_win = (sum(t.pnl for t in wins) / len(wins)) if wins else 0
        stats.avg_loss = (sum(t.pnl for t in losses) / len(losses)) if losses else 0

        total_wins = sum(t.pnl for t in wins) if wins else 0
        total_losses = abs(sum(t.pnl for t in losses)) if losses else 0
        stats.profit_factor = (total_wins / total_losses) if total_losses > 0 else float("inf") if total_wins > 0 else 0

        return stats
