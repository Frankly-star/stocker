"""MarketDataAgent: technical analysis with quantitative computation + LLM summary.

This agent performs deterministic calculations (indicators, S&R levels, zone detection)
and uses LLM only for formatting/summarizing the structured results.

Data source priority: westock-data (primary) → yfinance (fallback).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import tool

from stocker.analysis.indicators import compute_all_signals, find_support_resistance
from stocker.analysis.range_detector import calc_range_width, detect_market_environment, determine_zone

logger = logging.getLogger(__name__)


def _convert_to_westock_code(ticker: str) -> str:
    """Convert standard ticker format to westock-data code format.

    Examples: 0700.HK → hk00700, AAPL → usAAPL, 600519.SS → sh600519
    Also handles already-westock inputs: SZ300750 → sz300750
    """
    t = ticker.strip()
    tu = t.upper()

    # Already in westock format
    for prefix in ("SH", "SZ", "BJ", "HK", "US"):
        if tu.startswith(prefix) and len(tu) > 2:
            if prefix == "US":
                return f"us{tu[2:]}"
            return f"{prefix.lower()}{tu[2:]}"

    if tu.endswith(".HK"):
        return f"hk{tu.replace('.HK', '').zfill(5)}"
    elif tu.endswith(".SS") or tu.endswith(".SH"):
        return f"sh{tu.split('.')[0]}"
    elif tu.endswith(".SZ"):
        return f"sz{tu.split('.')[0]}"
    elif tu.endswith(".T"):
        return t
    elif tu.isalpha():
        return f"us{tu}"
    elif tu.isdigit():
        return f"sh{tu}" if tu.startswith("6") or tu.startswith("9") else f"sz{tu}"
    return t.lower()


def _fetch_westock_kline_as_df(ticker: str, count: int = 250):
    """Fetch K-line from westock-data and convert to pandas DataFrame for indicator computation.

    Returns (df, source_label) where df has Date/Open/High/Low/Close/Volume columns,
    or (empty DataFrame, "") if westock fails.
    """
    import pandas as pd

    try:
        from stocker.skills.westock_data import _run_westock
    except ImportError:
        logger.debug("westock_data module not available")
        return pd.DataFrame(), ""

    ws_code = _convert_to_westock_code(ticker)
    logger.info("Fetching kline from westock for %s (code=%s, count=%d)", ticker, ws_code, count)

    try:
        raw = _run_westock(["kline", ws_code, "day", str(count), "qfq"], timeout=30)
    except Exception as e:
        logger.warning("westock kline fetch failed for %s: %s", ticker, e)
        return pd.DataFrame(), ""

    if not raw or "error" in raw.lower()[:100] or "not found" in raw.lower()[:100]:
        logger.warning("westock kline returned no usable data for %s", ticker)
        return pd.DataFrame(), ""

    # Parse the westock kline output into a DataFrame
    # westock kline outputs tab-separated or JSON data — try JSON first, then TSV
    try:
        data = json.loads(raw)
        if isinstance(data, list) and len(data) > 0:
            df = pd.DataFrame(data)
        elif isinstance(data, dict) and "data" in data:
            df = pd.DataFrame(data["data"])
        else:
            df = pd.DataFrame()
    except (json.JSONDecodeError, ValueError):
        # Try parsing as tab/comma-separated text
        try:
            from io import StringIO
            df = pd.read_csv(StringIO(raw), sep=None, engine="python")
        except Exception:
            logger.warning("Cannot parse westock kline output for %s", ticker)
            return pd.DataFrame(), ""

    if df.empty:
        return pd.DataFrame(), ""

    # Normalize column names — westock may use Chinese or English headers
    col_map = {}
    for c in df.columns:
        cl = str(c).lower().strip()
        if cl in ("date", "日期", "time", "timestamp"):
            col_map[c] = "Date"
        elif cl in ("open", "开盘", "开盘价"):
            col_map[c] = "Open"
        elif cl in ("high", "最高", "最高价"):
            col_map[c] = "High"
        elif cl in ("low", "最低", "最低价"):
            col_map[c] = "Low"
        elif cl in ("close", "收盘", "收盘价"):
            col_map[c] = "Close"
        elif cl in ("volume", "成交量", "vol"):
            col_map[c] = "Volume"

    if col_map:
        df = df.rename(columns=col_map)

    # Ensure required columns exist
    required = {"Date", "Open", "High", "Low", "Close"}
    if not required.issubset(set(df.columns)):
        logger.warning("westock kline missing required columns for %s: have %s, need %s",
                       ticker, list(df.columns), list(required))
        return pd.DataFrame(), ""

    # Clean types
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    for col in ["Open", "High", "Low", "Close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "Volume" in df.columns:
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")
    else:
        df["Volume"] = 0
    df = df.dropna(subset=["Close"])
    df = df.sort_values("Date").reset_index(drop=True)

    logger.info("westock kline: got %d bars for %s", len(df), ticker)
    return df, "WeStock (Tencent)"


def _fetch_yfinance_ohlcv(ticker: str):
    """Fetch OHLCV from yfinance (cache → fresh download). Fallback data source.

    Returns (df, source_label) or (empty DataFrame, "").
    """
    import pandas as pd

    # Try cached data first
    try:
        from stocker.dataflows.yfinance_provider import load_ohlcv
        df = load_ohlcv(ticker.upper())
        if not df.empty and len(df) >= 50:
            logger.info("yfinance cache hit: %d bars for %s", len(df), ticker)
            return df, "yfinance (cached)"
    except Exception as e:
        logger.debug("yfinance cache load failed for %s: %s", ticker, e)

    # Force-fetch fresh
    try:
        import os
        import yfinance as yf
        from stocker.dataflows.yfinance_provider import _yf_retry, _get_cache_dir

        symbol = ticker.upper()
        today = pd.Timestamp.today()
        start = today - pd.DateOffset(years=5)
        start_str = start.strftime("%Y-%m-%d")
        end_str = today.strftime("%Y-%m-%d")

        cache_dir = _get_cache_dir()
        cache_file = os.path.join(cache_dir, f"{symbol}-{start_str}-{end_str}.csv")
        if os.path.exists(cache_file):
            os.remove(cache_file)

        data = _yf_retry(lambda: yf.download(
            symbol, start=start_str, end=end_str,
            multi_level_index=False, progress=False, auto_adjust=True,
        ))

        if data is None or data.empty:
            return pd.DataFrame(), ""

        data = data.reset_index()
        if "Date" not in data.columns:
            return pd.DataFrame(), ""

        data.to_csv(cache_file, index=False)
        data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
        data = data.dropna(subset=["Date"])
        price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
        data[price_cols] = data[price_cols].apply(pd.to_numeric, errors="coerce")
        data = data.dropna(subset=["Close"])
        data[price_cols] = data[price_cols].ffill().bfill()

        if len(data) >= 50:
            logger.info("yfinance fresh fetch: %d bars for %s", len(data), ticker)
            return data, "yfinance (fresh)"
    except Exception as e:
        logger.warning("yfinance fetch failed for %s: %s", ticker, e)

    return pd.DataFrame(), ""


def _get_quick_quote(ticker: str) -> str:
    """Get basic quote info when OHLCV is unavailable from any source."""
    # 1. Try westock-data (no rate limiting)
    try:
        from stocker.skills.westock_data import _run_westock
        ws_code = _convert_to_westock_code(ticker.upper())
        result = _run_westock(["quote", ws_code], timeout=15)
        if result and "error" not in result.lower()[:100] and "not found" not in result.lower()[:100]:
            return (
                f"## Quick Quote (WeStock): {ticker.upper()}\n\n"
                f"{result}\n\n"
                f"Note: Full technical analysis unavailable. Data sourced from Tencent WeStock API."
            )
    except Exception as e:
        logger.debug("westock quote failed for %s: %s", ticker, e)

    # 2. Fallback to yfinance .info
    try:
        import yfinance as yf
        from stocker.dataflows.yfinance_provider import _yf_retry

        obj = yf.Ticker(ticker.upper())
        info = _yf_retry(lambda: obj.info)
        if info:
            price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose", 0)
            return (
                f"## Quick Quote: {ticker.upper()}\n\n"
                f"**Price**: ${price:.2f}\n"
                f"**52W High**: ${info.get('fiftyTwoWeekHigh', 0):.2f}\n"
                f"**52W Low**: ${info.get('fiftyTwoWeekLow', 0):.2f}\n"
                f"**50D Avg**: ${info.get('fiftyDayAverage', 0):.2f}\n"
                f"**200D Avg**: ${info.get('twoHundredDayAverage', 0):.2f}\n"
                f"**Market Cap**: {info.get('marketCap', 'N/A')}\n"
                f"**PE (TTM)**: {info.get('trailingPE', 'N/A')}\n"
                f"**Beta**: {info.get('beta', 'N/A')}\n\n"
                f"Note: Full technical analysis unavailable."
            )
    except Exception:
        pass

    return f"Unable to retrieve any data for {ticker}: all data sources failed."


def create_market_data_tools() -> list:
    """Create tools for the MarketDataAgent."""

    @tool
    def analyze_technicals(ticker: str) -> str:
        """Run full technical analysis with OHLCV data, computing indicators, S&R levels, and market environment.

        Data source priority: westock-data (primary) → yfinance (fallback).
        If neither provides enough OHLCV bars, returns a quick quote instead.
        """
        try:
            df = None
            source = ""

            # PRIMARY: try westock-data kline first (no rate limit)
            df, source = _fetch_westock_kline_as_df(ticker, count=250)

            # FALLBACK: try yfinance if westock didn't produce enough data
            if df is None or df.empty or len(df) < 50:
                logger.info("westock kline insufficient for %s, trying yfinance...", ticker)
                df, source = _fetch_yfinance_ohlcv(ticker)

            # If still insufficient, return quick quote
            if df is None or df.empty or len(df) < 50:
                logger.warning("No sufficient OHLCV from any source for %s, using quick quote", ticker)
                return _get_quick_quote(ticker)

            # Compute all indicators
            signals = compute_all_signals(df)
            supports, resistances = find_support_resistance(df)
            env = detect_market_environment(df)
            zone = determine_zone(signals["current_price"], supports, resistances)
            rw = calc_range_width(supports, resistances)

            return (
                f"## Technical Analysis: {ticker.upper()}\n\n"
                f"**Data**: {len(df)} bars loaded (source: {source})\n"
                f"**Price**: ${signals['current_price']:.2f}\n"
                f"**Market Environment**: {env}\n"
                f"**Current Zone**: {zone}\n"
                f"**Range Width**: {rw:.1f}%\n\n"
                f"**Support Levels**: {[f'${s:.2f}' for s in supports]}\n"
                f"**Resistance Levels**: {[f'${r:.2f}' for r in resistances]}\n\n"
                f"**Indicators**:\n"
                f"  RSI(14): {signals['rsi']:.1f}\n"
                f"  MACD: {signals['macd_line']:.4f} / Signal: {signals['macd_signal']:.4f} / Hist: {signals['macd_histogram']:.4f}\n"
                f"  BB Position: {signals['bb_position']:.2f} (0=lower, 1=upper)\n"
                f"  ATR(14): {signals['atr']:.2f}\n"
                f"  SMA50: ${signals['sma_50']:.2f} / SMA200: ${signals['sma_200']:.2f}\n"
                f"  Trend: {signals['trend']}\n"
            )
        except Exception as e:
            logger.error("Error analyzing %s: %s", ticker, e, exc_info=True)
            return _get_quick_quote(ticker)

    return [analyze_technicals]


MARKET_DATA_SYSTEM_PROMPT = """You are a Market Data Analyst specializing in range/swing trading.

You will receive pre-fetched market data (quote, K-line, technical indicators). Your job is to ANALYZE this data — you do NOT need to call any tools.

## YOUR ANALYSIS
Based on the provided data:
1. Identify the current price, trend direction, and market environment (range-bound vs trending).
2. Compute or interpret support/resistance levels from the K-line data.
3. Interpret technical indicators (RSI, MACD, Bollinger Bands, ATR, MA) for momentum and volatility signals.
4. Determine the current zone: near support (buy zone), near resistance (sell zone), or mid-range.
5. Provide a structured summary with actionable insights for swing traders.

Focus on FACTS and NUMBERS from the data provided. Do not speculate or make up values.
Your analysis feeds into a risk assessment team that will make the final trading decision."""
