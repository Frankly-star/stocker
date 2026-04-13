"""Data helpers: shared data-fetching utilities.

Centralizes OHLCV data acquisition that was previously duplicated across
supervisor.py (_fetch_ohlcv_for_scan) and watchlist/scanner.py (_fetch_yfinance).
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def fetch_ohlcv_yfinance(
    ticker: str,
    period: str = "6mo",
    min_bars: int = 30,
) -> pd.DataFrame | None:
    """Fetch OHLCV data via yfinance.

    Parameters
    ----------
    ticker:
        Stock ticker symbol (e.g. ``"AAPL"``, ``"0700.HK"``).
    period:
        yfinance period string (default ``"6mo"``).
    min_bars:
        Minimum number of rows required.  Returns ``None`` if the
        DataFrame has fewer rows.

    Returns
    -------
    pd.DataFrame or None
        OHLCV DataFrame, or ``None`` if fetch fails or data is insufficient.
    """
    try:
        import yfinance as yf

        obj = yf.Ticker(ticker.upper())
        df = obj.history(period=period)
        if df is not None and not df.empty and len(df) >= min_bars:
            return df
    except Exception as e:
        logger.debug("yfinance fetch for %s failed: %s", ticker, e)
    return None
