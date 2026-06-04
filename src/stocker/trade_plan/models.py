"""Trade plan models for PAPER-002."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class TradePlanStatus(str, Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class TradePlan(BaseModel):
    """A user-confirmed-before-execution paper trade plan."""

    plan_id: str = Field(default_factory=lambda: f"TP-{uuid4().hex[:10]}")
    source_alert_id: str = ""
    ticker: str
    action: str = "sell"  # buy / sell
    quantity: int = 0
    suggested_price: float | None = None
    reason: str = ""
    status: TradePlanStatus = TradePlanStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    confirmed_at: datetime | None = None
    executed_at: datetime | None = None
    execution_result: dict = Field(default_factory=dict)
    notes: str = ""

    def mark_executed(self, result: dict) -> None:
        self.status = TradePlanStatus.EXECUTED if result.get("status") == "filled" else TradePlanStatus.REJECTED
        self.execution_result = result
        self.confirmed_at = datetime.now()
        self.executed_at = datetime.now()

    def mark_cancelled(self) -> None:
        self.status = TradePlanStatus.CANCELLED
