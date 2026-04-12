"""Backtest data models: configuration, metrics, trades, and reports.

All models follow the project's Pydantic v2 conventions (see broker/models.py, strategy/models.py).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class BarFrequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"


class BacktestRunMode(str, Enum):
    RULE = "rule"      # Pure rule-based signals, no LLM calls — fast
    FULL = "full"      # Full LangGraph subgraph pipeline — slow but realistic


class BacktestDataSource(str, Enum):
    YFINANCE = "yfinance"
    CSV = "csv"
    PARQUET = "parquet"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class BacktestConfig(BaseModel):
    """Backtest run configuration."""

    symbols: list[str] = Field(default_factory=list, description="回测标的列表")
    start_date: str = Field(..., description="开始日期 yyyy-mm-dd")
    end_date: str = Field(..., description="结束日期 yyyy-mm-dd")
    initial_cash: float = Field(100_000.0, ge=0, description="初始资金")
    commission_rate: float = Field(0.001, ge=0, le=0.1, description="手续费率 (0.1%)")
    slippage_pct: float = Field(0.001, ge=0, le=0.05, description="滑点百分比 (0.1%)")
    data_source: BacktestDataSource = Field(
        BacktestDataSource.YFINANCE, description="数据源"
    )
    data_path: str = Field("", description="本地数据路径 (csv/parquet 时使用)")
    run_mode: BacktestRunMode = Field(
        BacktestRunMode.RULE, description="运行模式: rule(纯规则) / full(LangGraph子图)"
    )
    bar_frequency: BarFrequency = Field(
        BarFrequency.DAILY, description="K线频率: daily / weekly"
    )
    benchmark: str = Field("", description="基准标的 (e.g. SPY, 空则不比较)")


# ---------------------------------------------------------------------------
# Trade record
# ---------------------------------------------------------------------------

class BacktestTrade(BaseModel):
    """A single trade executed during backtest."""

    trade_id: str = ""
    bar_index: int = 0
    timestamp: datetime = Field(default_factory=datetime.now)
    ticker: str = ""
    side: str = ""          # "buy" / "sell"
    quantity: int = 0
    price: float = 0.0      # execution price (after slippage)
    slippage: float = 0.0   # actual slippage amount per share
    commission: float = 0.0  # commission paid for this trade
    pnl: float | None = None  # realized P&L (for sell trades)
    notes: str = ""


# ---------------------------------------------------------------------------
# Daily snapshot
# ---------------------------------------------------------------------------

class DailySnapshot(BaseModel):
    """End-of-bar portfolio snapshot."""

    dt: datetime
    bar_index: int = 0
    cash: float = 0.0
    positions_value: float = 0.0
    nav: float = 0.0              # net asset value = cash + positions_value
    drawdown_pct: float = 0.0     # drawdown from peak NAV


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

class BacktestMetrics(BaseModel):
    """Backtest performance metrics."""

    total_return_pct: float = 0.0
    annualized_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    max_consecutive_losses: int = 0
    avg_trade_return_pct: float = 0.0
    avg_holding_days: float = 0.0
    total_commission: float = 0.0
    total_slippage: float = 0.0

    # Benchmark comparison (populated if benchmark is set)
    benchmark_return_pct: float | None = None
    alpha: float | None = None
    beta: float | None = None


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

class BacktestReport(BaseModel):
    """Complete backtest result."""

    config: BacktestConfig
    metrics: BacktestMetrics = Field(default_factory=BacktestMetrics)
    trades: list[BacktestTrade] = Field(default_factory=list)
    equity_curve: list[DailySnapshot] = Field(default_factory=list)
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: datetime = Field(default_factory=datetime.now)
    duration_seconds: float = 0.0
    status: str = "completed"  # "completed" / "failed" / "cancelled"
    error: str | None = None
