"""Create westock-paper trade plans from alerts."""

from __future__ import annotations

from stocker.alerts.models import Alert, AlertRiskLevel
from stocker.trade_plan.models import TradePlan

_SELL_ACTIONS = {
    "reduce_or_stop_loss",
    "reduce_or_take_profit",
    "consider_take_profit",
    "watch_take_profit",
    "watch_stop_loss",
}


def create_plan_from_alert(
    alert: Alert,
    *,
    position_store,
    quantity: int | None = None,
    action: str | None = None,
    price: float | None = None,
) -> TradePlan:
    """Convert an actionable alert to a pending westock-paper trade plan."""
    ticker = alert.ticker.upper()
    position = position_store.get(ticker) if position_store is not None else None
    resolved_action = action or _action_from_alert(alert)
    resolved_quantity = quantity if quantity is not None else _quantity_from_alert(alert, position, resolved_action)
    if resolved_quantity <= 0:
        raise ValueError(f"Cannot create trade plan for {ticker}: quantity must be positive")

    suggested_price = price if price and price > 0 else (alert.current_price or alert.price_level)
    return TradePlan(
        source_alert_id=alert.alert_id,
        ticker=ticker,
        action=resolved_action,
        quantity=resolved_quantity,
        suggested_price=suggested_price if suggested_price and suggested_price > 0 else None,
        reason=f"{alert.trigger}: {alert.reason}",
        notes=f"risk_level={alert.risk_level.value}; suggested_action={alert.suggested_action}",
    )


def _action_from_alert(alert: Alert) -> str:
    if alert.suggested_action in _SELL_ACTIONS:
        return "sell"
    if alert.risk_level == AlertRiskLevel.MUST_ACT:
        return "sell"
    return "sell"


def _quantity_from_alert(alert: Alert, position, action: str) -> int:
    if action == "buy":
        return 1
    if position is None:
        return 0
    if alert.risk_level == AlertRiskLevel.MUST_ACT:
        return int(position.quantity)
    return max(1, int(position.quantity // 2))
