"""Backtest configuration loader.

Reads STOCKER_BACKTEST_* environment variables and constructs BacktestConfig.
Follows the same pattern as integrations/futu/config.py.
"""

from __future__ import annotations

import os

from stocker.backtest.models import (
    BacktestConfig,
    BacktestDataSource,
    BacktestRunMode,
    BarFrequency,
)


def load_backtest_config(
    stocker_config: dict | None = None,
    overrides: dict | None = None,
) -> BacktestConfig:
    """Build ``BacktestConfig`` from stocker config dict and/or env vars.

    Priority: overrides > stocker_config > env vars > defaults.
    """
    cfg = stocker_config or {}
    ovr = overrides or {}

    def _get(key: str, default: str = "") -> str:
        return ovr.get(key, cfg.get(key, os.getenv(f"STOCKER_BACKTEST_{key.upper()}", default)))

    symbols_raw = _get("symbols", "")
    symbols = (
        [s.strip() for s in symbols_raw.split(",") if s.strip()]
        if isinstance(symbols_raw, str)
        else symbols_raw
    )

    return BacktestConfig(
        symbols=symbols,
        start_date=_get("start_date", "2024-01-01"),
        end_date=_get("end_date", "2024-12-31"),
        initial_cash=float(_get("initial_cash", "100000")),
        commission_rate=float(_get("commission_rate", "0.001")),
        slippage_pct=float(_get("slippage_pct", "0.001")),
        data_source=BacktestDataSource(_get("data_source", "yfinance")),
        data_path=_get("data_path", ""),
        run_mode=BacktestRunMode(_get("run_mode", "rule")),
        bar_frequency=BarFrequency(_get("bar_frequency", "daily")),
        benchmark=_get("benchmark", ""),
    )
