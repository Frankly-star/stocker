"""Persistent trade plan store."""

from __future__ import annotations

from stocker.trade_plan.models import TradePlan, TradePlanStatus
from stocker.utils.base_store import BaseJsonStore
from stocker.utils.store_helpers import create_store_path


def create_trade_plan_store(broker_type: str | None = None, base_dir: str = "data") -> "TradePlanStore":
    filepath = create_store_path(broker_type, "trade_plans.json", base_dir)
    return TradePlanStore(filepath=str(filepath))


class TradePlanStore(BaseJsonStore[TradePlan]):
    def __init__(self, filepath: str = "data/trade_plans.json") -> None:
        super().__init__(filepath=filepath, model_class=TradePlan, key_field="plan_id")

    def add(self, plan: TradePlan | dict) -> TradePlan:
        if isinstance(plan, dict):
            plan = TradePlan(**plan)
        self._put(plan.plan_id, plan)
        self._save()
        return plan

    def get(self, plan_id: str) -> TradePlan | None:
        return self._data.get(plan_id)

    def list_by_status(self, status: str | None = None) -> list[dict]:
        plans = list(self._data.values())
        if status:
            plans = [p for p in plans if p.status == TradePlanStatus(status)]
        plans.sort(key=lambda p: p.created_at, reverse=True)
        return [p.model_dump(mode="json") for p in plans]

    def update(self, plan: TradePlan) -> None:
        self._put(plan.plan_id, plan)
        self._save()
