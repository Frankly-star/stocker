"""BacktestResultCollector: accumulates trade data and computes performance metrics.

Called by BacktestRuntime at the end of each bar and after the full run
to produce the final BacktestReport.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime

import numpy as np
import pandas as pd

from stocker.backtest.models import (
    BacktestConfig,
    BacktestMetrics,
    BacktestReport,
    BacktestTrade,
    DailySnapshot,
)

logger = logging.getLogger(__name__)

# Annual trading days for annualization
TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE = 0.02  # 2% annual risk-free rate


class BacktestResultCollector:
    """Collects backtest data and computes final performance metrics."""

    def __init__(self, config: BacktestConfig) -> None:
        self._config = config
        self._trades: list[BacktestTrade] = []
        self._snapshots: list[DailySnapshot] = []
        self._start_time = datetime.now()

    # ------------------------------------------------------------------
    # Data collection (called during backtest loop)
    # ------------------------------------------------------------------

    def add_snapshot(self, snapshot: DailySnapshot) -> None:
        self._snapshots.append(snapshot)

    def add_trade(self, trade: BacktestTrade) -> None:
        self._trades.append(trade)

    def add_trades(self, trades: list[BacktestTrade]) -> None:
        self._trades.extend(trades)

    # ------------------------------------------------------------------
    # Finalization
    # ------------------------------------------------------------------

    def finalize(self) -> BacktestReport:
        """Compute all metrics and produce the final BacktestReport."""
        end_time = datetime.now()
        duration = (end_time - self._start_time).total_seconds()

        metrics = self._compute_metrics()

        return BacktestReport(
            config=self._config,
            metrics=metrics,
            trades=list(self._trades),
            equity_curve=list(self._snapshots),
            start_time=self._start_time,
            end_time=end_time,
            duration_seconds=duration,
            status="completed",
        )

    # ------------------------------------------------------------------
    # Metrics computation
    # ------------------------------------------------------------------

    def _compute_metrics(self) -> BacktestMetrics:
        metrics = BacktestMetrics()

        if not self._snapshots:
            return metrics

        navs = [s.nav for s in self._snapshots]
        initial_nav = self._config.initial_cash

        # Total return
        final_nav = navs[-1]
        metrics.total_return_pct = (final_nav - initial_nav) / initial_nav * 100

        # Annualized return
        n_days = len(navs)
        if n_days > 1 and final_nav > 0 and initial_nav > 0:
            years = n_days / TRADING_DAYS_PER_YEAR
            if years > 0:
                metrics.annualized_return_pct = (
                    (final_nav / initial_nav) ** (1 / years) - 1
                ) * 100

        # Max drawdown
        peak = initial_nav
        max_dd = 0.0
        for nav in navs:
            peak = max(peak, nav)
            dd = (peak - nav) / peak * 100 if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        metrics.max_drawdown_pct = max_dd

        # Daily returns for Sharpe / Sortino
        daily_returns = self._compute_daily_returns(navs)

        if len(daily_returns) > 1:
            metrics.sharpe_ratio = self._sharpe(daily_returns)
            metrics.sortino_ratio = self._sortino(daily_returns)
            if max_dd > 0:
                metrics.calmar_ratio = metrics.annualized_return_pct / max_dd

        # Trade-level metrics
        self._compute_trade_metrics(metrics)

        # Costs
        metrics.total_commission = sum(t.commission for t in self._trades)
        metrics.total_slippage = sum(abs(t.slippage) * t.quantity for t in self._trades)

        return metrics

    def _compute_daily_returns(self, navs: list[float]) -> list[float]:
        if len(navs) < 2:
            return []
        returns = []
        for i in range(1, len(navs)):
            if navs[i - 1] > 0:
                returns.append((navs[i] - navs[i - 1]) / navs[i - 1])
            else:
                returns.append(0.0)
        return returns

    @staticmethod
    def _sharpe(daily_returns: list[float]) -> float:
        """Annualized Sharpe ratio."""
        if not daily_returns:
            return 0.0
        arr = np.array(daily_returns)
        mean_ret = np.mean(arr)
        std_ret = np.std(arr, ddof=1)
        if std_ret == 0:
            return 0.0
        daily_rf = RISK_FREE_RATE / TRADING_DAYS_PER_YEAR
        sharpe = (mean_ret - daily_rf) / std_ret * math.sqrt(TRADING_DAYS_PER_YEAR)
        return round(sharpe, 4)

    @staticmethod
    def _sortino(daily_returns: list[float]) -> float:
        """Annualized Sortino ratio (only downside deviation)."""
        if not daily_returns:
            return 0.0
        arr = np.array(daily_returns)
        mean_ret = np.mean(arr)
        daily_rf = RISK_FREE_RATE / TRADING_DAYS_PER_YEAR
        downside = arr[arr < daily_rf]
        if len(downside) == 0:
            return 0.0
        down_std = np.std(downside, ddof=1)
        if down_std == 0:
            return 0.0
        sortino = (mean_ret - daily_rf) / down_std * math.sqrt(TRADING_DAYS_PER_YEAR)
        return round(sortino, 4)

    def _compute_trade_metrics(self, metrics: BacktestMetrics) -> None:
        """Compute win rate, profit/loss ratio, consecutive losses, etc."""
        sell_trades = [t for t in self._trades if t.side == "sell" and t.pnl is not None]
        metrics.total_trades = len(self._trades)

        if not sell_trades:
            return

        wins = [t for t in sell_trades if t.pnl is not None and t.pnl > 0]
        losses = [t for t in sell_trades if t.pnl is not None and t.pnl <= 0]

        metrics.winning_trades = len(wins)
        metrics.losing_trades = len(losses)
        metrics.win_rate = len(wins) / len(sell_trades) * 100 if sell_trades else 0.0

        avg_win = np.mean([t.pnl for t in wins]) if wins else 0.0
        avg_loss = abs(np.mean([t.pnl for t in losses])) if losses else 0.0
        metrics.profit_loss_ratio = round(avg_win / avg_loss, 4) if avg_loss > 0 else 0.0

        # Average trade return %
        returns = []
        for t in sell_trades:
            if t.pnl is not None and t.price > 0:
                returns.append(t.pnl / (t.price * t.quantity) * 100)
        metrics.avg_trade_return_pct = round(np.mean(returns), 4) if returns else 0.0

        # Max consecutive losses
        max_consec = 0
        current_consec = 0
        for t in sell_trades:
            if t.pnl is not None and t.pnl <= 0:
                current_consec += 1
                max_consec = max(max_consec, current_consec)
            else:
                current_consec = 0
        metrics.max_consecutive_losses = max_consec
