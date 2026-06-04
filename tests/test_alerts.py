from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_position_alert_generation_and_cooldown(tmp_path):
    from stocker.alerts.position_alerts import generate_position_alerts
    from stocker.alerts.store import AlertStore
    from stocker.broker.models import Position
    from stocker.portfolio.store import PositionStore

    position_store = PositionStore(filepath=str(tmp_path / "positions.json"), broker_type="simulated")
    position_store._positions["AAPL"] = Position(
        ticker="AAPL",
        quantity=10,
        avg_cost=100.0,
        current_price=88.0,
    )
    position_store._save()
    alert_store = AlertStore(filepath=str(tmp_path / "alerts.json"))

    def no_kline(_ticker: str):
        return None

    first = generate_position_alerts(
        position_store,
        alert_store,
        cooldown_minutes=30,
        fetch_ohlcv_func=no_kline,
    )
    second = generate_position_alerts(
        position_store,
        alert_store,
        cooldown_minutes=30,
        fetch_ohlcv_func=no_kline,
    )

    assert first["positions_checked"] == 1
    assert first["actionable_count"] == 1
    assert first["new_alerts"][0]["risk_level"] == "must_act"
    assert first["new_alerts"][0]["trigger"] == "stop_loss"
    assert second["new_alerts"] == []
    assert second["suppressed_duplicates"] == 1
    active = alert_store.list_active()
    assert len(active) == 1
    assert active[0]["suppressed_count"] == 1


def test_alert_store_mark_handled(tmp_path):
    from stocker.alerts.models import Alert, AlertRiskLevel
    from stocker.alerts.store import AlertStore

    store = AlertStore(filepath=str(tmp_path / "alerts.json"))
    alert, created = store.add_or_update(Alert(
        ticker="TSLA",
        risk_level=AlertRiskLevel.WATCH,
        trigger="near_resistance",
        suggested_action="watch_take_profit",
        dedupe_key="position:TSLA:near_resistance",
    ))

    assert created is True
    assert store.mark_handled(alert.alert_id) is True
    assert store.list_active() == []
