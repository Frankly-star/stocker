"""Technical indicator calculations and support/resistance identification.

Extracted from skills/stock-market-pro calc_xxx functions + new range trading algorithms.
All functions are pure computation (no LLM, no API calls).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Core indicators (extracted from stock-market-pro yf.py)
# ---------------------------------------------------------------------------

def calc_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def calc_macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD line, signal line, histogram."""
    ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd - sig
    return macd, sig, hist


def calc_bbands(
    close: pd.Series, window: int = 20, n_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands: upper, middle, lower."""
    ma = close.rolling(window=window, min_periods=window).mean()
    std = close.rolling(window=window, min_periods=window).std(ddof=0)
    upper = ma + n_std * std
    lower = ma - n_std * std
    return upper, ma, lower


def calc_vwap(df: pd.DataFrame) -> pd.Series:
    """Volume Weighted Average Price (cumulative)."""
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    vol = df["Volume"].fillna(0)
    tpv = (typical_price * vol).cumsum()
    return tpv / vol.cumsum().replace(0, pd.NA)


def calc_atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Average True Range."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def calc_sma(close: pd.Series, window: int) -> pd.Series:
    """Simple Moving Average."""
    return close.rolling(window=window, min_periods=window).mean()


def calc_ema(close: pd.Series, span: int) -> pd.Series:
    """Exponential Moving Average."""
    return close.ewm(span=span, adjust=False, min_periods=span).mean()


# ---------------------------------------------------------------------------
# New: Support & Resistance identification (range trading specific)
# ---------------------------------------------------------------------------

def calc_pivot_points(high: float, low: float, close: float) -> dict[str, float]:
    """Classic Pivot Points from previous period H/L/C.

    Returns dict with keys: pp, r1, r2, r3, s1, s2, s3.
    """
    pp = (high + low + close) / 3
    r1 = 2 * pp - low
    s1 = 2 * pp - high
    r2 = pp + (high - low)
    s2 = pp - (high - low)
    r3 = high + 2 * (pp - low)
    s3 = low - 2 * (high - pp)
    return {"pp": pp, "r1": r1, "r2": r2, "r3": r3, "s1": s1, "s2": s2, "s3": s3}


def calc_fibonacci_levels(high: float, low: float) -> dict[str, float]:
    """Fibonacci retracement levels between a swing high and swing low.

    Returns dict with keys: 0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0.
    """
    diff = high - low
    return {
        "0.0": high,
        "0.236": high - 0.236 * diff,
        "0.382": high - 0.382 * diff,
        "0.5": high - 0.5 * diff,
        "0.618": high - 0.618 * diff,
        "0.786": high - 0.786 * diff,
        "1.0": low,
    }


def find_support_resistance(
    df: pd.DataFrame,
    window: int | None = None,
    num_levels: int | None = None,
    tolerance_pct: float | None = None,
) -> tuple[list[float], list[float]]:
    """Identify support and resistance levels by clustering local extrema.

    Algorithm:
    1. Find local minima/maxima using rolling window
    2. Cluster nearby levels (within tolerance_pct) by averaging
    3. Return top-N strongest (most-touched) levels

    Args:
        df: OHLCV DataFrame with 'High', 'Low', 'Close' columns
        window: Rolling window for local extrema detection
        num_levels: Number of support/resistance levels to return
        tolerance_pct: Percentage threshold for clustering nearby levels

    Returns:
        (support_levels, resistance_levels) — sorted lists of price levels
    """
    # Fill defaults from strategy config if not explicitly provided
    if window is None or num_levels is None or tolerance_pct is None:
        try:
            from stocker.strategy import get_strategy
            t = get_strategy().technical
            window = window if window is not None else t.sr_window
            num_levels = num_levels if num_levels is not None else t.sr_num_levels
            tolerance_pct = tolerance_pct if tolerance_pct is not None else t.sr_tolerance_pct
        except Exception:
            window = window if window is not None else 20
            num_levels = num_levels if num_levels is not None else 3
            tolerance_pct = tolerance_pct if tolerance_pct is not None else 1.5

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    current_price = close.iloc[-1]

    # Find local minima and maxima
    local_min = low[
        (low.shift(1) > low) & (low.shift(-1) > low)
    ].dropna()
    local_max = high[
        (high.shift(1) < high) & (high.shift(-1) < high)
    ].dropna()

    # Also add rolling min/max
    rolling_min = low.rolling(window=window).min().dropna()
    rolling_max = high.rolling(window=window).max().dropna()

    # Combine all candidate levels
    all_support_candidates = pd.concat([local_min, rolling_min]).unique()
    all_resistance_candidates = pd.concat([local_max, rolling_max]).unique()

    def _cluster_levels(levels: np.ndarray, tol_pct: float) -> list[tuple[float, int]]:
        """Cluster nearby price levels, return (avg_price, touch_count) pairs."""
        if len(levels) == 0:
            return []
        sorted_levels = np.sort(levels)
        clusters: list[list[float]] = [[sorted_levels[0]]]
        for lvl in sorted_levels[1:]:
            if abs(lvl - np.mean(clusters[-1])) / np.mean(clusters[-1]) * 100 < tol_pct:
                clusters[-1].append(lvl)
            else:
                clusters.append([lvl])
        return [(np.mean(c), len(c)) for c in clusters]

    support_clusters = _cluster_levels(
        all_support_candidates[all_support_candidates < current_price], tolerance_pct
    )
    resistance_clusters = _cluster_levels(
        all_resistance_candidates[all_resistance_candidates > current_price], tolerance_pct
    )

    # Sort by touch count (strength), take top N
    support_clusters.sort(key=lambda x: x[1], reverse=True)
    resistance_clusters.sort(key=lambda x: x[1], reverse=True)

    supports = sorted([c[0] for c in support_clusters[:num_levels]], reverse=True)
    resistances = sorted([c[0] for c in resistance_clusters[:num_levels]])

    return supports, resistances


def compute_all_signals(df: pd.DataFrame) -> dict:
    """Compute all technical indicators for the latest bar.

    Args:
        df: OHLCV DataFrame (must have Open/High/Low/Close/Volume columns)

    Returns:
        dict with all indicator values for the most recent row
    """
    # Load indicator parameters from strategy config
    try:
        from stocker.strategy import get_strategy
        t = get_strategy().technical
    except Exception:
        from types import SimpleNamespace
        t = SimpleNamespace(
            rsi_window=14, macd_fast=12, macd_slow=26, macd_signal=9,
            bb_window=20, bb_std=2.0, atr_window=14, sma_short=50, sma_long=200,
        )

    close = df["Close"]

    rsi = calc_rsi(close, window=t.rsi_window)
    macd_line, macd_signal, macd_hist = calc_macd(close, fast=t.macd_fast, slow=t.macd_slow, signal=t.macd_signal)
    bb_upper, bb_middle, bb_lower = calc_bbands(close, window=t.bb_window, n_std=t.bb_std)
    atr = calc_atr(df, window=t.atr_window)
    vwap = calc_vwap(df)
    sma_short = calc_sma(close, t.sma_short)
    sma_long = calc_sma(close, t.sma_long)

    latest = len(close) - 1
    current_price = close.iloc[latest]

    # Bollinger Band position: 0 = at lower, 1 = at upper
    bb_range = bb_upper.iloc[latest] - bb_lower.iloc[latest]
    bb_pos = (
        (current_price - bb_lower.iloc[latest]) / bb_range
        if bb_range > 0
        else 0.5
    )

    # Trend determination
    sma_short_val = sma_short.iloc[latest] if not pd.isna(sma_short.iloc[latest]) else current_price
    sma_long_val = sma_long.iloc[latest] if not pd.isna(sma_long.iloc[latest]) else current_price
    if current_price > sma_short_val > sma_long_val:
        trend = "uptrend"
    elif current_price < sma_short_val < sma_long_val:
        trend = "downtrend"
    else:
        trend = "sideways"

    return {
        "rsi": _safe_float(rsi.iloc[latest]),
        "macd_line": _safe_float(macd_line.iloc[latest]),
        "macd_signal": _safe_float(macd_signal.iloc[latest]),
        "macd_histogram": _safe_float(macd_hist.iloc[latest]),
        "bb_upper": _safe_float(bb_upper.iloc[latest]),
        "bb_middle": _safe_float(bb_middle.iloc[latest]),
        "bb_lower": _safe_float(bb_lower.iloc[latest]),
        "bb_position": _safe_float(bb_pos),
        "atr": _safe_float(atr.iloc[latest]),
        "vwap": _safe_float(vwap.iloc[latest]),
        "sma_50": _safe_float(sma_short_val),
        "sma_200": _safe_float(sma_long_val),
        "trend": trend,
        "current_price": _safe_float(current_price),
    }


def _safe_float(val) -> float:
    """Convert to float, handle NaN/None."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return 0.0
    return float(val)
