"""HistoricalDataStore: load, cache, and serve historical market data for backtesting.

Supports yfinance batch download, local CSV/Parquet loading, and registers
itself as a ``DataRouter`` provider to feed data into the Intelligence subgraph
without any modifications to existing code.

Anti look-ahead: all data access is gated by the BacktestClock's current time.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

from stocker.backtest.clock import BacktestClock
from stocker.backtest.models import BacktestDataSource

logger = logging.getLogger(__name__)

_CACHE_DIR = Path("data/backtest/cache")


class HistoricalDataStore:
    """In-memory historical data store with lazy loading and disk cache."""

    def __init__(self, clock: BacktestClock) -> None:
        self._clock = clock
        # symbol -> DataFrame (columns: Date, Open, High, Low, Close, Volume)
        self._data: dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load(
        self,
        symbols: list[str],
        start: str,
        end: str,
        source: BacktestDataSource = BacktestDataSource.YFINANCE,
        data_path: str = "",
    ) -> None:
        """Batch-load historical data for all *symbols*.

        Tries disk cache first, then falls back to the specified source.
        """
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)

        for symbol in symbols:
            sym = symbol.upper().strip()
            cache_file = _CACHE_DIR / f"{sym}_{start}_{end}.csv"

            if cache_file.exists():
                df = pd.read_csv(cache_file, parse_dates=["Date"])
                logger.info("[DataStore] Loaded %s from cache (%d rows)", sym, len(df))
            elif source == BacktestDataSource.YFINANCE:
                df = self._download_yfinance(sym, start, end)
                if df is not None and not df.empty:
                    df.to_csv(cache_file, index=False)
            elif source == BacktestDataSource.CSV:
                df = self._load_csv(sym, data_path)
            elif source == BacktestDataSource.PARQUET:
                df = self._load_parquet(sym, data_path)
            else:
                df = None

            if df is not None and not df.empty:
                df = self._normalize(df, start, end)
                self._data[sym] = df
                logger.info("[DataStore] %s: %d bars loaded", sym, len(df))
            else:
                logger.warning("[DataStore] No data for %s", sym)

    # ------------------------------------------------------------------
    # Data access (gated by clock)
    # ------------------------------------------------------------------

    def get_bar(self, symbol: str, dt: pd.Timestamp | None = None) -> dict | None:
        """Get the OHLCV bar for *symbol* at the clock's current time (or *dt*).

        Returns dict with keys: Date, Open, High, Low, Close, Volume, or None.
        """
        sym = symbol.upper()
        df = self._data.get(sym)
        if df is None or df.empty:
            return None

        target = pd.Timestamp(dt) if dt is not None else pd.Timestamp(self._clock.now())

        # Find exact match or last available bar <= target
        mask = df["Date"] <= target
        if not mask.any():
            return None
        row = df.loc[mask].iloc[-1]
        return row.to_dict()

    def get_slice(
        self, symbol: str, start: str | None = None, end: str | None = None
    ) -> pd.DataFrame:
        """Get OHLCV data slice. *end* defaults to clock.now() for anti-lookahead."""
        sym = symbol.upper()
        df = self._data.get(sym)
        if df is None or df.empty:
            return pd.DataFrame()

        as_of = pd.Timestamp(end) if end else pd.Timestamp(self._clock.now())
        filtered = df[df["Date"] <= as_of]
        if start:
            filtered = filtered[filtered["Date"] >= pd.Timestamp(start)]
        return filtered.copy()

    def get_current_prices(self) -> dict[str, float]:
        """Get close prices for all symbols at the current clock time."""
        prices = {}
        for sym in self._data:
            bar = self.get_bar(sym)
            if bar and bar.get("Close"):
                prices[sym] = float(bar["Close"])
        return prices

    def has_symbol(self, symbol: str) -> bool:
        return symbol.upper() in self._data

    @property
    def symbols(self) -> list[str]:
        return list(self._data.keys())

    # ------------------------------------------------------------------
    # Legacy DataRouter integration
    # ------------------------------------------------------------------

    def register_as_provider(self, router) -> None:
        """Register historical data methods on a legacy ``DataRouter``.

        The main Intelligence graph no longer reads through DataRouter; this is
        retained for older backtest/full-mode experiments only.
        """
        store = self

        def _get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
            df = store.get_slice(symbol, start_date, end_date)
            if df.empty:
                return f"No historical data for '{symbol}' between {start_date} and {end_date}"
            header = f"# {symbol.upper()} from {start_date} to {end_date} ({len(df)} records)\n\n"
            return header + df.to_csv(index=False)

        def _get_fundamentals(ticker: str, curr_date: str | None = None) -> str:
            return f"[Backtest mode] Fundamentals not available for {ticker} in historical replay."

        def _get_news(ticker: str, start_date: str, end_date: str) -> str:
            return f"[Backtest mode] News not available for {ticker} in historical replay."

        def _get_global_news(curr_date: str) -> str:
            return f"[Backtest mode] Global news not available in historical replay."

        router.register_provider_batch(
            "historical",
            {
                "get_stock_data": _get_stock_data,
                "get_fundamentals": _get_fundamentals,
                "get_news": _get_news,
                "get_global_news": _get_global_news,
            },
            category="backtest",
        )
        # Set historical as default provider so it's tried first
        router.default_provider = "historical"
        logger.info("[DataStore] Registered as 'historical' provider on DataRouter")

    # ------------------------------------------------------------------
    # Source-specific loaders
    # ------------------------------------------------------------------

    @staticmethod
    def _download_yfinance(symbol: str, start: str, end: str) -> pd.DataFrame | None:
        try:
            import yfinance as yf

            logger.info("[DataStore] Downloading %s from yfinance (%s to %s)", symbol, start, end)
            df = yf.download(
                symbol,
                start=start,
                end=end,
                multi_level_index=False,
                progress=False,
                auto_adjust=True,
            )
            if df is None or df.empty:
                return None
            df = df.reset_index()
            return df
        except Exception as e:
            logger.warning("[DataStore] yfinance download failed for %s: %s", symbol, e)
            return None

    @staticmethod
    def _load_csv(symbol: str, data_path: str) -> pd.DataFrame | None:
        """Load from a CSV file. Expects file named ``{SYMBOL}.csv`` in *data_path*."""
        fpath = Path(data_path) / f"{symbol.upper()}.csv"
        if not fpath.exists():
            logger.warning("[DataStore] CSV not found: %s", fpath)
            return None
        try:
            return pd.read_csv(fpath, parse_dates=["Date"])
        except Exception as e:
            logger.warning("[DataStore] CSV load failed for %s: %s", fpath, e)
            return None

    @staticmethod
    def _load_parquet(symbol: str, data_path: str) -> pd.DataFrame | None:
        fpath = Path(data_path) / f"{symbol.upper()}.parquet"
        if not fpath.exists():
            logger.warning("[DataStore] Parquet not found: %s", fpath)
            return None
        try:
            return pd.read_parquet(fpath)
        except Exception as e:
            logger.warning("[DataStore] Parquet load failed for %s: %s", fpath, e)
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
        """Normalize column names and filter date range."""
        # Ensure Date column
        if "Date" not in df.columns and df.index.name == "Date":
            df = df.reset_index()
        if "Date" not in df.columns:
            # Try common alternatives
            for col in ("date", "Datetime", "datetime", "timestamp"):
                if col in df.columns:
                    df = df.rename(columns={col: "Date"})
                    break

        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"])

        # Standardize OHLCV columns
        col_map = {
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["Close"])
        df = df.sort_values("Date").reset_index(drop=True)

        # Filter to requested range
        df = df[(df["Date"] >= pd.Timestamp(start)) & (df["Date"] <= pd.Timestamp(end))]
        return df.reset_index(drop=True)
