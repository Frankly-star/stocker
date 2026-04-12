"""Range detection: determine if a stock is range-bound or trending.

Uses multiple signals: Bollinger Band width, ADX proxy via ATR, price channel analysis.
"""

from __future__ import annotations

import pandas as pd

from stocker.analysis.indicators import calc_bbands, calc_atr


def detect_market_environment(
    df: pd.DataFrame,
    bb_squeeze_threshold: float | None = None,
    atr_trend_threshold: float | None = None,
) -> str:
    """Determine market environment for a stock.

    Args:
        df: OHLCV DataFrame
        bb_squeeze_threshold: BB width / middle below this = squeeze (range-bound).
            If None, read from active strategy config.
        atr_trend_threshold: ATR multiplier above which = trending/volatile.
            If None, read from active strategy config.

    Returns:
        One of: "range_bound", "trending_up", "trending_down", "volatile"
    """
    # Load defaults from strategy if not provided
    if bb_squeeze_threshold is None or atr_trend_threshold is None:
        try:
            from stocker.strategy import get_strategy
            m = get_strategy().market
            bb_squeeze_threshold = bb_squeeze_threshold if bb_squeeze_threshold is not None else m.bb_squeeze_threshold
            atr_trend_threshold = atr_trend_threshold if atr_trend_threshold is not None else m.atr_trend_threshold
            min_bars = m.min_bars_required
        except Exception:
            bb_squeeze_threshold = bb_squeeze_threshold if bb_squeeze_threshold is not None else 0.04
            atr_trend_threshold = atr_trend_threshold if atr_trend_threshold is not None else 1.5
            min_bars = 50
    else:
        min_bars = 50

    close = df["Close"]
    if len(close) < min_bars:
        return "range_bound"

    bb_upper, bb_middle, bb_lower = calc_bbands(close)
    atr = calc_atr(df)

    latest = len(close) - 1
    bb_width = (bb_upper.iloc[latest] - bb_lower.iloc[latest]) / bb_middle.iloc[latest]
    atr_val = atr.iloc[latest]
    avg_atr = atr.rolling(50).mean().iloc[latest]

    # Price vs moving averages for trend direction
    sma_50 = close.rolling(50).mean().iloc[latest]
    sma_20 = close.rolling(20).mean().iloc[latest]
    current = close.iloc[latest]

    # Volatile: ATR spike
    if avg_atr > 0 and atr_val / avg_atr > atr_trend_threshold:
        return "volatile"

    # Squeeze (range-bound)
    if bb_width < bb_squeeze_threshold:
        return "range_bound"

    # Trending
    if current > sma_20 > sma_50:
        return "trending_up"
    elif current < sma_20 < sma_50:
        return "trending_down"

    return "range_bound"


def determine_zone(
    current_price: float,
    supports: list[float],
    resistances: list[float],
    threshold_pct: float | None = None,
) -> str:
    """Determine where current price is relative to support/resistance.

    Args:
        current_price: Current stock price
        supports: List of support levels (descending)
        resistances: List of resistance levels (ascending)
        threshold_pct: Percentage proximity to consider "near".
            If None, read from active strategy config.

    Returns:
        "near_support", "near_resistance", or "mid_range"
    """
    if threshold_pct is None:
        try:
            from stocker.strategy import get_strategy
            threshold_pct = get_strategy().market.zone_threshold_pct
        except Exception:
            threshold_pct = 2.0

    if supports:
        nearest_support = supports[0]
        if current_price > 0:
            dist_to_support = (current_price - nearest_support) / current_price * 100
            if dist_to_support < threshold_pct:
                return "near_support"

    if resistances:
        nearest_resistance = resistances[0]
        if current_price > 0:
            dist_to_resistance = (nearest_resistance - current_price) / current_price * 100
            if dist_to_resistance < threshold_pct:
                return "near_resistance"

    return "mid_range"


def calc_range_width(supports: list[float], resistances: list[float]) -> float:
    """Calculate the range width as a percentage.

    Uses the nearest support and resistance levels.
    """
    if not supports or not resistances:
        return 0.0
    nearest_support = supports[0]
    nearest_resistance = resistances[0]
    if nearest_support <= 0:
        return 0.0
    return (nearest_resistance - nearest_support) / nearest_support * 100
