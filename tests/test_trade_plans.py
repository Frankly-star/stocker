from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _client(tmp_path, monkeypatch):
    from stocker.alerts.store import AlertStore
    from stocker.api.routes import create_router
    from stocker.broker.models import Position
    from stocker.broker.trade_store import TradeStore
    from stocker.portfolio.store import PositionStore
    from stocker.trade_plan.store import TradePlanStore

    monkeypatch.setenv("STOCKER_PAPER_INITIAL_CASH", "10000")
    position_store = PositionStore(filepath=str(tmp_path / "positions.json"), broker_type="simulated")
    position_store._positions["AAPL"] = Position(
        ticker="AAPL",
        quantity=4,
        avg_cost=100.0,
        current_price=88.0,
    )
    position_store._save()
    trade_store = TradeStore(filepath=str(tmp_path / "trades.json"))
    alert_store = AlertStore(filepath=str(tmp_path / "alerts.json"))
    trade_plan_store = TradePlanStore(filepath=str(tmp_path / "trade_plans.json"))
    app = FastAPI()
    app.include_router(
        create_router(
            position_store=position_store,
            trade_store=trade_store,
            alert_store=alert_store,
            trade_plan_store=trade_plan_store,
        ),
        prefix="/api/v1",
    )
    return TestClient(app), position_store, trade_store, alert_store, trade_plan_store


def test_create_trade_plan_from_alert(tmp_path, monkeypatch):
    client, _, _, alert_store, trade_plan_store = _client(tmp_path, monkeypatch)

    alert = client.get("/api/v1/alerts/positions").json()["new_alerts"][0]
    response = client.post("/api/v1/trade-plans/from-alert", json={"alert_id": alert["alert_id"]})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    plan = body["plan"]
    assert plan["source_alert_id"] == alert["alert_id"]
    assert plan["ticker"] == "AAPL"
    assert plan["action"] == "sell"
    assert plan["quantity"] == 4
    assert plan["status"] == "pending"
    assert trade_plan_store.get(plan["plan_id"]) is not None
    assert len(alert_store.list_active()) == 1


def test_execute_trade_plan_requires_active_mode(tmp_path, monkeypatch):
    from stocker.engine.runtime_state import set_execution_mode

    set_execution_mode("observe")
    client, _, trade_store, _, _ = _client(tmp_path, monkeypatch)
    alert = client.get("/api/v1/alerts/positions").json()["new_alerts"][0]
    plan = client.post("/api/v1/trade-plans/from-alert", json={"alert_id": alert["alert_id"]}).json()["plan"]

    response = client.post(f"/api/v1/trade-plans/{plan['plan_id']}/execute", json={"price": 88.0})

    assert response.json()["success"] is False
    assert "execution_mode" in response.json()["error"]
    assert trade_store.count() == 0


def test_execute_trade_plan_with_westock_paper(tmp_path, monkeypatch):
    from stocker.engine.runtime_state import set_execution_mode

    set_execution_mode("active")
    client, position_store, trade_store, alert_store, trade_plan_store = _client(tmp_path, monkeypatch)
    alert = client.get("/api/v1/alerts/positions").json()["new_alerts"][0]
    plan = client.post("/api/v1/trade-plans/from-alert", json={"alert_id": alert["alert_id"], "quantity": 2}).json()["plan"]

    response = client.post(f"/api/v1/trade-plans/{plan['plan_id']}/execute", json={"price": 88.0})
    set_execution_mode("observe")

    body = response.json()
    assert body["success"] is True
    assert body["result"]["broker"] == "westock-paper"
    assert trade_store.count() == 1
    assert position_store.get("AAPL").quantity == 2
    stored_plan = trade_plan_store.get(plan["plan_id"])
    assert stored_plan.status == "executed"
    assert alert_store.list_active() == []
