"""Backtest engine: historical data replay and strategy validation.

Usage::

    from stocker.backtest import BacktestRuntime, BacktestConfig

    config = BacktestConfig(
        symbols=["AAPL", "MSFT"],
        start_date="2024-01-01",
        end_date="2024-12-31",
    )
    runtime = BacktestRuntime(config)
    report = runtime.run()
    print(f"Return: {report.metrics.total_return_pct:.2f}%")
"""

from stocker.backtest.config import load_backtest_config  # noqa: F401
from stocker.backtest.models import (  # noqa: F401
    BacktestConfig,
    BacktestMetrics,
    BacktestReport,
)
from stocker.backtest.runtime import BacktestRuntime  # noqa: F401

__all__ = [
    "BacktestConfig",
    "BacktestMetrics",
    "BacktestReport",
    "BacktestRuntime",
    "load_backtest_config",
]
