from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _client_with_simulated_broker(tmp_path, monkeypatch=None):
    from stocker.api.routes import create_router
    from stocker.broker.simulated import SimulatedBroker
    from stocker.alerts.store import AlertStore
    from stocker.broker.trade_store import TradeStore
    from stocker.portfolio.store import PositionStore
    from stocker.trade_plan.store import TradePlanStore

    if monkeypatch is not None:
        monkeypatch.setenv("STOCKER_PAPER_INITIAL_CASH", "10000")

    app = FastAPI()
    broker = SimulatedBroker(initial_cash=10_000)
    position_store = PositionStore(
        filepath=str(tmp_path / "positions.json"),
        broker_type="simulated",
    )
    trade_store = TradeStore(filepath=str(tmp_path / "trades.json"))
    alert_store = AlertStore(filepath=str(tmp_path / "alerts.json"))
    trade_plan_store = TradePlanStore(filepath=str(tmp_path / "trade_plans.json"))
    app.include_router(
        create_router(
            broker=broker,
            position_store=position_store,
            trade_store=trade_store,
            alert_store=alert_store,
            trade_plan_store=trade_plan_store,
        ),
        prefix="/api/v1",
    )
    return TestClient(app), trade_store, position_store, alert_store, trade_plan_store




def test_monitoring_routes_update_runtime_state(tmp_path, monkeypatch):
    from stocker.engine.runtime_state import set_monitoring_enabled, set_monitoring_interval_seconds

    set_monitoring_enabled(False)
    set_monitoring_interval_seconds(300)
    client, _, _, _, _ = _client_with_simulated_broker(tmp_path, monkeypatch)

    response = client.post("/api/v1/monitoring", json={"enabled": True, "interval_seconds": 15})

    assert response.status_code == 200
    monitoring = response.json()["monitoring"]
    assert monitoring["enabled"] is True
    assert monitoring["interval_seconds"] == 15

    status = client.get("/api/v1/status").json()
    assert status["monitoring"]["enabled"] is True
    assert status["monitoring"]["interval_seconds"] == 15


def test_position_alert_route_generates_and_dedupes(tmp_path, monkeypatch):
    from stocker.broker.models import Position

    client, _, position_store, alert_store, _ = _client_with_simulated_broker(tmp_path, monkeypatch)
    position_store._positions["AAPL"] = Position(
        ticker="AAPL",
        quantity=1,
        avg_cost=100.0,
        current_price=88.0,
    )
    position_store._save()

    first = client.get("/api/v1/alerts/positions").json()
    second = client.get("/api/v1/alerts/positions").json()

    assert first["actionable_count"] == 1
    assert first["new_alerts"][0]["trigger"] == "stop_loss"
    assert second["new_alerts"] == []
    assert second["suppressed_duplicates"] == 1
    assert len(alert_store.list_active()) == 1


def test_paper_validate_reads_account_without_order(tmp_path, monkeypatch):
    from stocker.engine.runtime_state import set_execution_mode

    set_execution_mode("observe")
    client, trade_store, _, _, _ = _client_with_simulated_broker(tmp_path, monkeypatch)

    response = client.post("/api/v1/paper/validate", json={"execute": False})

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["executed"] is False
    assert body["broker"] == "westock-paper"
    assert body["account_before"]["cash"] == 10_000
    assert trade_store.count() == 0


def test_paper_validate_executes_controlled_simulated_order(tmp_path, monkeypatch):
    from stocker.engine.runtime_state import set_execution_mode

    set_execution_mode("active")
    client, trade_store, position_store, _, _ = _client_with_simulated_broker(tmp_path, monkeypatch)

    response = client.post(
        "/api/v1/paper/validate",
        json={"execute": True, "ticker": "AAPL", "action": "buy", "quantity": 2, "price": 10.0},
    )
    set_execution_mode("observe")

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["executed"] is True
    assert body["order"]["status"] == "filled"
    assert body["account_after"]["cash"] == 9_980
    assert trade_store.count() == 1
    pos = position_store.get("AAPL")
    assert pos is not None
    assert pos.quantity == 2
    assert pos.avg_cost == 10.0
