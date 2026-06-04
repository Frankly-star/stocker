"""Position alert generation for ALERT-001."""

from __future__ import annotations

import logging
from typing import Any, Callable

from stocker.alerts.models import Alert, AlertRiskLevel
from stocker.broker.models import Position

logger = logging.getLogger(__name__)


def generate_position_alerts(
    position_store: Any,
    alert_store: Any | None = None,
    *,
    cooldown_minutes: int = 30,
    fetch_ohlcv_func: Callable[[str], Any] | None = None,
) -> dict:
    """Generate position alerts for every current holding.

    Returns both per-position assessments and persisted active alerts.
    """
    positions = position_store.list_all() if position_store else []
    assessments: list[dict] = []
    created_alerts: list[dict] = []
    suppressed = 0

    for position in positions:
        alert = evaluate_position(position, fetch_ohlcv_func=fetch_ohlcv_func)
        assessments.append(alert.model_dump(mode="json"))
        if alert.risk_level == AlertRiskLevel.NORMAL:
            continue
        if alert_store is None:
            created_alerts.append(alert.model_dump(mode="json"))
            continue
        stored, created = alert_store.add_or_update(alert, cooldown_minutes=cooldown_minutes)
        if created:
            created_alerts.append(stored.model_dump(mode="json"))
        else:
            suppressed += 1

    active_alerts = alert_store.list_active(limit=100) if alert_store is not None else created_alerts
    return {
        "positions_checked": len(positions),
        "assessments": assessments,
        "new_alerts": created_alerts,
        "active_alerts": active_alerts,
        "suppressed_duplicates": suppressed,
        "actionable_count": sum(1 for a in assessments if a.get("risk_level") != AlertRiskLevel.NORMAL.value),
    }


def evaluate_position(
    position: Position,
    *,
    fetch_ohlcv_func: Callable[[str], Any] | None = None,
) -> Alert:
    ticker = position.ticker.upper()
    current_price = float(position.current_price or 0.0)
    signal = None

    try:
        if fetch_ohlcv_func is None:
            from stocker.utils.data_helpers import fetch_ohlcv_westock
            fetch_ohlcv_func = fetch_ohlcv_westock
        df = fetch_ohlcv_func(ticker)
        if df is not None and not df.empty:
            from stocker.analysis.swing_signals import SwingSignalEngine
            signal = SwingSignalEngine().analyze(ticker, df)
            if signal.suggested_price > 0:
                current_price = float(signal.suggested_price)
    except Exception as e:
        logger.debug("Position alert data fetch failed for %s: %s", ticker, e)

    avg_cost = float(position.avg_cost or 0.0)
    pnl_pct = ((current_price - avg_cost) / avg_cost * 100) if avg_cost > 0 and current_price > 0 else 0.0

    risk_level = AlertRiskLevel.NORMAL
    trigger = "normal"
    suggested_action = "hold"
    price_level: float | None = current_price if current_price > 0 else None
    reason = "持仓状态正常，暂无明确操作预警。"

    stop_loss_pct, take_profit_pct = _strategy_thresholds()

    supports: list[float] = []
    resistances: list[float] = []
    signal_type = ""
    signal_strength = 0.0
    if signal is not None:
        supports = [float(x) for x in signal.indicators.get("supports", []) if x]
        resistances = [float(x) for x in signal.indicators.get("resistances", []) if x]
        signal_type = getattr(signal.signal_type, "value", str(signal.signal_type))
        signal_strength = float(signal.strength or 0.0)

    nearest_support = _nearest_below(current_price, supports)
    nearest_resistance = _nearest_above(current_price, resistances)

    if current_price <= 0:
        risk_level = AlertRiskLevel.WATCH
        trigger = "price_unavailable"
        suggested_action = "check_data"
        price_level = None
        reason = "无法获取当前价格，需检查固定行情源或 ticker 格式。"
    elif avg_cost > 0 and pnl_pct <= -stop_loss_pct:
        risk_level = AlertRiskLevel.MUST_ACT
        trigger = "stop_loss"
        suggested_action = "reduce_or_stop_loss"
        price_level = current_price
        reason = f"当前亏损 {pnl_pct:.1f}% 已触及止损阈值 {stop_loss_pct:.1f}%。"
    elif signal_type == "exit_long" and signal_strength >= 60:
        risk_level = AlertRiskLevel.MUST_ACT
        trigger = "strong_exit_signal"
        suggested_action = "reduce_or_take_profit"
        price_level = current_price
        reason = f"波段退出信号强度 {signal_strength:.0f}，需要处理持仓。"
    elif nearest_support and current_price < nearest_support * 0.99:
        risk_level = AlertRiskLevel.MUST_ACT
        trigger = "support_breakdown"
        suggested_action = "reduce_or_stop_loss"
        price_level = nearest_support
        reason = f"价格 {current_price:.2f} 跌破支撑位 {nearest_support:.2f}。"
    elif avg_cost > 0 and pnl_pct >= take_profit_pct:
        risk_level = AlertRiskLevel.WATCH
        trigger = "take_profit_zone"
        suggested_action = "consider_take_profit"
        price_level = current_price
        reason = f"当前浮盈 {pnl_pct:.1f}% 已进入止盈观察区。"
    elif nearest_resistance and abs(current_price - nearest_resistance) / nearest_resistance <= 0.02:
        risk_level = AlertRiskLevel.WATCH
        trigger = "near_resistance"
        suggested_action = "watch_take_profit"
        price_level = nearest_resistance
        reason = f"价格接近压力位 {nearest_resistance:.2f}，关注减仓或止盈。"
    elif nearest_support and abs(current_price - nearest_support) / nearest_support <= 0.02:
        risk_level = AlertRiskLevel.WATCH
        trigger = "near_support"
        suggested_action = "watch_breakdown_or_rebound"
        price_level = nearest_support
        reason = f"价格接近支撑位 {nearest_support:.2f}，关注破位或反弹。"
    elif avg_cost > 0 and pnl_pct <= -max(2.0, stop_loss_pct * 0.6):
        risk_level = AlertRiskLevel.WATCH
        trigger = "loss_watch"
        suggested_action = "watch_stop_loss"
        price_level = current_price
        reason = f"当前亏损 {pnl_pct:.1f}%，接近止损区。"

    return Alert(
        ticker=ticker,
        risk_level=risk_level,
        trigger=trigger,
        suggested_action=suggested_action,
        price_level=price_level,
        current_price=current_price,
        avg_cost=avg_cost,
        pnl_pct=round(pnl_pct, 2),
        reason=reason,
        source="position",
        dedupe_key=f"position:{ticker}:{trigger}",
    )


def _strategy_thresholds() -> tuple[float, float]:
    try:
        from stocker.strategy import get_strategy
        risk = get_strategy().risk
        stop_loss_pct = float(risk.stop_loss_max_pct)
        take_profit_pct = stop_loss_pct * float(risk.take_profit_min_ratio)
        return stop_loss_pct, take_profit_pct
    except Exception:
        return 10.0, 15.0


def _nearest_below(price: float, levels: list[float]) -> float | None:
    if price <= 0:
        return None
    below = [level for level in levels if level > 0 and level <= price * 1.05]
    return max(below) if below else None


def _nearest_above(price: float, levels: list[float]) -> float | None:
    if price <= 0:
        return None
    above = [level for level in levels if level > 0 and level >= price * 0.95]
    return min(above) if above else None
