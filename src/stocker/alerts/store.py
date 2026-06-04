"""Persistent alert store with dedupe and cooldown."""

from __future__ import annotations

from datetime import datetime, timedelta

from stocker.alerts.models import Alert, AlertStatus
from stocker.utils.base_store import BaseJsonStore
from stocker.utils.store_helpers import create_store_path


def create_alert_store(broker_type: str | None = None, base_dir: str = "data") -> "AlertStore":
    filepath = create_store_path(broker_type, "alerts.json", base_dir)
    return AlertStore(filepath=str(filepath))


class AlertStore(BaseJsonStore[Alert]):
    """Append-only alert store with active-alert helpers."""

    MAX_RECORDS = 2000

    def __init__(self, filepath: str = "data/alerts.json") -> None:
        super().__init__(filepath=filepath, model_class=Alert, key_field=None)

    def add_or_update(self, alert: Alert, cooldown_minutes: int = 30) -> tuple[Alert, bool]:
        """Add alert, or update an active duplicate within cooldown.

        Returns (alert, created_new).
        """
        now = datetime.now()
        cooldown_start = now - timedelta(minutes=max(1, cooldown_minutes))
        for existing in reversed(self._list_data):
            if existing.status != AlertStatus.ACTIVE:
                continue
            if existing.dedupe_key != alert.dedupe_key:
                continue
            if existing.last_seen_at >= cooldown_start:
                existing.current_price = alert.current_price
                existing.price_level = alert.price_level
                existing.reason = alert.reason
                existing.pnl_pct = alert.pnl_pct
                existing.suppressed_count += 1
                existing.touch()
                self._save()
                return existing, False
            break

        self._append(alert)
        self._truncate(self.MAX_RECORDS)
        self._save()
        return alert, True

    def list_active(self, limit: int = 100) -> list[dict]:
        alerts = [a for a in self._list_data if a.status == AlertStatus.ACTIVE]
        alerts.sort(key=lambda a: _risk_sort_key(a), reverse=True)
        return [a.model_dump(mode="json") for a in alerts[:limit]]

    def list_recent(self, limit: int = 100) -> list[dict]:
        return [a.model_dump(mode="json") for a in reversed(self._list_data[-limit:])]

    def get_by_id(self, alert_id: str) -> Alert | None:
        for alert in self._list_data:
            if alert.alert_id == alert_id:
                return alert
        return None

    def mark_handled(self, alert_id: str) -> bool:
        for alert in self._list_data:
            if alert.alert_id == alert_id:
                alert.mark_handled()
                self._save()
                return True
        return False


def _risk_sort_key(alert: Alert) -> tuple[int, datetime]:
    rank = {"must_act": 3, "watch": 2, "normal": 1}.get(str(alert.risk_level), 0)
    return rank, alert.updated_at
