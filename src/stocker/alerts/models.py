"""Alert data models for position and event monitoring."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class AlertRiskLevel(str, Enum):
    MUST_ACT = "must_act"
    WATCH = "watch"
    NORMAL = "normal"


class AlertStatus(str, Enum):
    ACTIVE = "active"
    HANDLED = "handled"
    SUPPRESSED = "suppressed"


class Alert(BaseModel):
    """A trading-relevant alert.

    Core fields intentionally match the user-facing requirement:
    risk_level, trigger, suggested_action, price_level, reason.
    """

    alert_id: str = Field(default_factory=lambda: f"AL-{uuid4().hex[:10]}")
    ticker: str
    risk_level: AlertRiskLevel = AlertRiskLevel.NORMAL
    trigger: str = ""
    suggested_action: str = ""
    price_level: float | None = None
    current_price: float = 0.0
    avg_cost: float = 0.0
    pnl_pct: float = 0.0
    reason: str = ""
    source: str = "position"
    dedupe_key: str = ""
    status: AlertStatus = AlertStatus.ACTIVE
    suppressed_count: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    last_seen_at: datetime = Field(default_factory=datetime.now)
    handled_at: datetime | None = None

    def touch(self) -> None:
        now = datetime.now()
        self.updated_at = now
        self.last_seen_at = now

    def mark_handled(self) -> None:
        now = datetime.now()
        self.status = AlertStatus.HANDLED
        self.handled_at = now
        self.updated_at = now
