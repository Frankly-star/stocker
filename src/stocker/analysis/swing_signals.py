"""SwingSignalEngine: multi-factor swing trading signal generator.

Combines RSI, MACD, Bollinger Bands, ATR, and support/resistance levels
to produce composite entry/exit signals with strength scores (0-100).
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from stocker.analysis.indicators import (
    calc_atr,
    calc_bbands,
    calc_macd,
    calc_rsi,
    compute_all_signals,
    find_support_resistance,
)
from stocker.analysis.models import SwingSignal, SwingSignalType
from stocker.analysis.range_detector import detect_market_environment, determine_zone

logger = logging.getLogger(__name__)


class SwingSignalEngine:
    """Generate swing trading signals from OHLCV data."""

    def __init__(self) -> None:
        # Load thresholds from strategy config
        try:
            from stocker.strategy import get_strategy
            cfg = get_strategy()
            self._rsi_oversold = cfg.risk.swing_rsi_oversold
            self._rsi_overbought = cfg.risk.swing_rsi_overbought
            self._bb_low = cfg.risk.swing_bb_low
            self._bb_high = cfg.risk.swing_bb_high
        except Exception:
            self._rsi_oversold = 30.0
            self._rsi_overbought = 70.0
            self._bb_low = 0.2
            self._bb_high = 0.8

    def analyze(self, ticker: str, df: pd.DataFrame) -> SwingSignal:
        """Analyze OHLCV data and produce a swing signal.

        Args:
            ticker: Stock ticker symbol.
            df: OHLCV DataFrame with at least 50 rows.

        Returns:
            SwingSignal with signal_type, strength, and supporting details.
        """
        if df is None or len(df) < 30:
            return SwingSignal(
                ticker=ticker,
                signal_type=SwingSignalType.NEUTRAL,
                strength=0,
                reasons=["Insufficient data (< 30 bars)"],
            )

        try:
            signals = compute_all_signals(df)
            supports, resistances = find_support_resistance(df)
            env = detect_market_environment(df)
            current_price = signals.get("current_price", 0.0)
            zone = determine_zone(current_price, supports, resistances)
        except Exception as e:
            logger.warning("Signal computation failed for %s: %s", ticker, e)
            return SwingSignal(
                ticker=ticker,
                signal_type=SwingSignalType.NEUTRAL,
                strength=0,
                reasons=[f"Computation error: {e}"],
            )

        rsi = signals.get("rsi", 50.0)
        macd_hist = signals.get("macd_histogram", 0.0)
        macd_hist_prev = self._prev_macd_hist(df)
        bb_pos = signals.get("bb_position", 0.5)
        atr = signals.get("atr", 0.0)

        # --- Score entry signals (bullish) ---
        entry_score = 0.0
        entry_reasons: list[str] = []

        # RSI oversold recovery
        if rsi < self._rsi_oversold:
            entry_score += 25
            entry_reasons.append(f"RSI 超卖 ({rsi:.1f})")
        elif rsi < 40:
            entry_score += 10
            entry_reasons.append(f"RSI 偏低 ({rsi:.1f})")

        # MACD histogram turning positive
        if macd_hist > 0 and macd_hist_prev <= 0:
            entry_score += 25
            entry_reasons.append("MACD 柱状图由负转正（金叉信号）")
        elif macd_hist > macd_hist_prev and macd_hist_prev < 0:
            entry_score += 10
            entry_reasons.append("MACD 柱状图收窄回升")

        # BB position near lower band
        if bb_pos < self._bb_low:
            entry_score += 20
            entry_reasons.append(f"价格接近布林带下轨 (BB位置={bb_pos:.2f})")
        elif bb_pos < 0.35:
            entry_score += 8
            entry_reasons.append(f"价格偏低于布林带中轨 (BB位置={bb_pos:.2f})")

        # Near support
        if zone == "near_support":
            entry_score += 20
            entry_reasons.append("价格接近支撑位")

        # Range-bound environment bonus (swing friendly)
        if env == "range_bound":
            entry_score += 10
            entry_reasons.append("市场处于区间震荡（有利于波段操作）")

        # --- Score exit signals (bearish / take profit) ---
        exit_score = 0.0
        exit_reasons: list[str] = []

        if rsi > self._rsi_overbought:
            exit_score += 25
            exit_reasons.append(f"RSI 超买 ({rsi:.1f})")
        elif rsi > 60:
            exit_score += 8
            exit_reasons.append(f"RSI 偏高 ({rsi:.1f})")

        if macd_hist < 0 and macd_hist_prev >= 0:
            exit_score += 25
            exit_reasons.append("MACD 柱状图由正转负（死叉信号）")
        elif macd_hist < macd_hist_prev and macd_hist_prev > 0:
            exit_score += 10
            exit_reasons.append("MACD 柱状图缩量回落")

        if bb_pos > self._bb_high:
            exit_score += 20
            exit_reasons.append(f"价格接近布林带上轨 (BB位置={bb_pos:.2f})")

        if zone == "near_resistance":
            exit_score += 20
            exit_reasons.append("价格接近阻力位")

        if env == "range_bound":
            exit_score += 10
            exit_reasons.append("区间震荡环境（阻力位附近宜止盈）")

        # --- Determine dominant signal ---
        entry_score = min(entry_score, 100)
        exit_score = min(exit_score, 100)

        if entry_score >= exit_score and entry_score >= 30:
            signal_type = SwingSignalType.ENTRY_LONG
            strength = entry_score
            reasons = entry_reasons
        elif exit_score > entry_score and exit_score >= 30:
            signal_type = SwingSignalType.EXIT_LONG
            strength = exit_score
            reasons = exit_reasons
        else:
            signal_type = SwingSignalType.NEUTRAL
            strength = max(entry_score, exit_score)
            reasons = ["无明确波段信号"]
            if entry_reasons:
                reasons.extend([f"(弱多) {r}" for r in entry_reasons])
            if exit_reasons:
                reasons.extend([f"(弱空) {r}" for r in exit_reasons])

        # Calculate stop-loss and take-profit based on ATR
        sl = None
        tp = None
        if signal_type == SwingSignalType.ENTRY_LONG and current_price > 0 and atr > 0:
            sl = round(current_price - 2 * atr, 2)
            tp = round(current_price + 3 * atr, 2)

        return SwingSignal(
            ticker=ticker,
            signal_type=signal_type,
            strength=round(strength, 1),
            suggested_price=round(current_price, 2),
            stop_loss=sl,
            take_profit=tp,
            reasons=reasons,
            indicators={
                "rsi": round(rsi, 2),
                "macd_histogram": round(macd_hist, 4),
                "bb_position": round(bb_pos, 3),
                "atr": round(atr, 2),
                "current_price": round(current_price, 2),
                "supports": [round(s, 2) for s in supports[:3]],
                "resistances": [round(r, 2) for r in resistances[:3]],
            },
            market_environment=env,
        )

    def _prev_macd_hist(self, df: pd.DataFrame) -> float:
        """Get the previous bar's MACD histogram value."""
        try:
            close = df["Close"]
            if len(close) < 27:
                return 0.0
            _, _, hist = calc_macd(close)
            if len(hist) >= 2:
                val = hist.iloc[-2]
                return float(val) if not pd.isna(val) else 0.0
        except Exception:
            pass
        return 0.0
