"""yfinance data provider. Extracted from TradingAgents y_finance.py.

Changes: removed tradingagents imports, standalone cache dir config, simplified.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Annotated

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate-limit retry (extracted from stockstats_utils.py)
# ---------------------------------------------------------------------------

def _yf_retry(func, max_retries: int = 3, base_delay: float = 2.0):
    """Execute a yfinance call with exponential backoff on rate limits."""
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning("yfinance rate limited, retry in %.0fs (attempt %d)", delay, attempt + 1)
                    time.sleep(delay)
                else:
                    raise
            else:
                raise


def _get_cache_dir() -> str:
    """Get the data cache directory."""
    cache_dir = os.environ.get("STOCKER_DATA_DIR", "data")
    cache_path = os.path.join(cache_dir, "ohlcv_cache")
    os.makedirs(cache_path, exist_ok=True)
    return cache_path


# ---------------------------------------------------------------------------
# OHLCV data
# ---------------------------------------------------------------------------

def load_ohlcv(symbol: str, end_date: str | None = None) -> pd.DataFrame:
    """Fetch OHLCV data with CSV caching.

    Downloads up to 5 years of daily data and caches per symbol.
    If end_date is provided, filters out rows after that date (anti look-ahead).
    """
    cache_dir = _get_cache_dir()
    today = pd.Timestamp.today()
    start = today - pd.DateOffset(years=5)
    start_str = start.strftime("%Y-%m-%d")
    end_str = today.strftime("%Y-%m-%d")

    cache_file = os.path.join(cache_dir, f"{symbol}-{start_str}-{end_str}.csv")

    if os.path.exists(cache_file):
        data = pd.read_csv(cache_file, on_bad_lines="skip")
    else:
        data = _yf_retry(lambda: yf.download(
            symbol, start=start_str, end=end_str,
            multi_level_index=False, progress=False, auto_adjust=True,
        ))
        data = data.reset_index()
        data.to_csv(cache_file, index=False)

    # Clean
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date"])
    price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
    data[price_cols] = data[price_cols].apply(pd.to_numeric, errors="coerce")
    data = data.dropna(subset=["Close"])
    data[price_cols] = data[price_cols].ffill().bfill()

    if end_date:
        data = data[data["Date"] <= pd.to_datetime(end_date)]

    return data


def get_stock_data(
    symbol: Annotated[str, "ticker symbol"],
    start_date: Annotated[str, "Start date yyyy-mm-dd"],
    end_date: Annotated[str, "End date yyyy-mm-dd"],
) -> str:
    """Get OHLCV data as CSV string."""
    ticker = yf.Ticker(symbol.upper())
    data = _yf_retry(lambda: ticker.history(start=start_date, end=end_date))

    if data.empty:
        return f"No data found for '{symbol}' between {start_date} and {end_date}"

    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)

    for col in ["Open", "High", "Low", "Close"]:
        if col in data.columns:
            data[col] = data[col].round(2)

    header = f"# {symbol.upper()} from {start_date} to {end_date} ({len(data)} records)\n\n"
    return header + data.to_csv()


# ---------------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------------

def get_fundamentals(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: str | None = None,
) -> str:
    """Get company fundamentals overview from yfinance."""
    try:
        obj = yf.Ticker(ticker.upper())
        info = _yf_retry(lambda: obj.info)
        if not info:
            return f"No fundamentals for '{ticker}'"

        fields = [
            ("Name", "longName"), ("Sector", "sector"), ("Industry", "industry"),
            ("Market Cap", "marketCap"), ("PE (TTM)", "trailingPE"),
            ("Forward PE", "forwardPE"), ("PEG", "pegRatio"),
            ("P/B", "priceToBook"), ("EPS (TTM)", "trailingEps"),
            ("Forward EPS", "forwardEps"), ("Div Yield", "dividendYield"),
            ("Beta", "beta"), ("52W High", "fiftyTwoWeekHigh"),
            ("52W Low", "fiftyTwoWeekLow"), ("50D Avg", "fiftyDayAverage"),
            ("200D Avg", "twoHundredDayAverage"), ("Revenue", "totalRevenue"),
            ("EBITDA", "ebitda"), ("Net Income", "netIncomeToCommon"),
            ("Profit Margin", "profitMargins"), ("ROE", "returnOnEquity"),
            ("D/E", "debtToEquity"), ("FCF", "freeCashflow"),
        ]
        lines = [f"{label}: {info[key]}" for label, key in fields if info.get(key) is not None]
        return f"# Fundamentals: {ticker.upper()}\n\n" + "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def _filter_financials(data: pd.DataFrame, curr_date: str | None) -> pd.DataFrame:
    if not curr_date or data.empty:
        return data
    cutoff = pd.Timestamp(curr_date)
    mask = pd.to_datetime(data.columns, errors="coerce") <= cutoff
    return data.loc[:, mask]


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    obj = yf.Ticker(ticker.upper())
    data = _yf_retry(lambda: obj.quarterly_balance_sheet if freq == "quarterly" else obj.balance_sheet)
    data = _filter_financials(data, curr_date)
    if data.empty:
        return f"No balance sheet for '{ticker}'"
    return f"# Balance Sheet: {ticker.upper()} ({freq})\n\n" + data.to_csv()


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    obj = yf.Ticker(ticker.upper())
    data = _yf_retry(lambda: obj.quarterly_cashflow if freq == "quarterly" else obj.cashflow)
    data = _filter_financials(data, curr_date)
    if data.empty:
        return f"No cash flow for '{ticker}'"
    return f"# Cash Flow: {ticker.upper()} ({freq})\n\n" + data.to_csv()


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    obj = yf.Ticker(ticker.upper())
    data = _yf_retry(lambda: obj.quarterly_income_stmt if freq == "quarterly" else obj.income_stmt)
    data = _filter_financials(data, curr_date)
    if data.empty:
        return f"No income statement for '{ticker}'"
    return f"# Income Statement: {ticker.upper()} ({freq})\n\n" + data.to_csv()


def get_insider_transactions(ticker: str) -> str:
    obj = yf.Ticker(ticker.upper())
    data = _yf_retry(lambda: obj.insider_transactions)
    if data is None or data.empty:
        return f"No insider transactions for '{ticker}'"
    return f"# Insider Transactions: {ticker.upper()}\n\n" + data.to_csv()
