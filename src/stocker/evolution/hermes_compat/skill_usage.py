"""Hermes-compatible skill usage telemetry.

Upstream reference: `hermes-agent/tools/skill_usage.py`.
Local deviations: project-local `data/evolution/skills/.usage.json` path.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from stocker.evolution.paths import skills_root
from stocker.utils.helpers import atomic_json_write, json_read

STATE_ACTIVE = "active"
STATE_STALE = "stale"
STATE_ARCHIVED = "archived"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SkillUsageStore:
    """Sidecar usage store for evolution skills."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else skills_root()
        self.path = self.root / ".usage.json"

    def load(self) -> dict[str, dict[str, Any]]:
        data = json_read(self.path, default={})
        return data if isinstance(data, dict) else {}

    def save(self, data: dict[str, dict[str, Any]]) -> None:
        atomic_json_write(self.path, data)

    def get_record(self, skill_id: str) -> dict[str, Any]:
        return self.load().get(skill_id, self._default_record())

    def mark_created(self, skill_id: str, created_by: str = "reviewer") -> None:
        self._mutate(skill_id, lambda rec: rec.update({"created_by": created_by, "created_at": rec.get("created_at") or _now_iso()}))

    def bump_view(self, skill_id: str) -> None:
        self._bump(skill_id, "view")

    def bump_use(self, skill_id: str) -> None:
        self._bump(skill_id, "use")

    def bump_patch(self, skill_id: str) -> None:
        self._bump(skill_id, "patch")

    def set_pinned(self, skill_id: str, pinned: bool) -> None:
        self._mutate(skill_id, lambda rec: rec.update({"pinned": bool(pinned)}))

    def set_state(self, skill_id: str, state: str) -> None:
        def apply(rec: dict[str, Any]) -> None:
            rec["state"] = state
            if state == STATE_ARCHIVED:
                rec["archived_at"] = _now_iso()
        self._mutate(skill_id, apply)

    def report(self) -> list[dict[str, Any]]:
        data = self.load()
        rows = []
        for skill_id, rec in data.items():
            row = {"id": skill_id, **self._default_record(), **rec}
            row["last_activity_at"] = self.latest_activity_at(row)
            rows.append(row)
        return rows

    def mark_stale_by_age(self, stale_after_days: int = 30, archive_after_days: int = 90) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        stale_cutoff = now - timedelta(days=stale_after_days)
        archive_cutoff = now - timedelta(days=archive_after_days)
        counts = {"marked_stale": 0, "archived": 0, "checked": 0}
        data = self.load()
        for skill_id, rec in data.items():
            counts["checked"] += 1
            if rec.get("pinned") or rec.get("created_by") == "user":
                continue
            activity = self._parse_iso(self.latest_activity_at(rec) or rec.get("created_at")) or now
            state = rec.get("state", STATE_ACTIVE)
            if activity <= archive_cutoff and state != STATE_ARCHIVED:
                rec["state"] = STATE_ARCHIVED
                rec["archived_at"] = _now_iso()
                counts["archived"] += 1
            elif activity <= stale_cutoff and state == STATE_ACTIVE:
                rec["state"] = STATE_STALE
                counts["marked_stale"] += 1
        self.save(data)
        return counts

    def latest_activity_at(self, rec: dict[str, Any]) -> str | None:
        values = [rec.get("last_used_at"), rec.get("last_viewed_at"), rec.get("last_patched_at")]
        parsed = [(self._parse_iso(v), v) for v in values if v]
        parsed = [(dt, raw) for dt, raw in parsed if dt is not None]
        if not parsed:
            return None
        parsed.sort(key=lambda item: item[0], reverse=True)
        return str(parsed[0][1])

    def _bump(self, skill_id: str, action: str) -> None:
        count_key = f"{action}_count"
        time_key = f"last_{action}d_at" if action == "use" else f"last_{action}ed_at"
        if action == "use":
            time_key = "last_used_at"
        def apply(rec: dict[str, Any]) -> None:
            rec[count_key] = int(rec.get(count_key) or 0) + 1
            rec[time_key] = _now_iso()
        self._mutate(skill_id, apply)

    def _mutate(self, skill_id: str, fn) -> None:
        data = self.load()
        rec = {**self._default_record(), **data.get(skill_id, {})}
        fn(rec)
        data[skill_id] = rec
        self.save(data)

    @staticmethod
    def _default_record() -> dict[str, Any]:
        return {
            "use_count": 0,
            "view_count": 0,
            "patch_count": 0,
            "last_used_at": None,
            "last_viewed_at": None,
            "last_patched_at": None,
            "created_at": _now_iso(),
            "created_by": "system",
            "state": STATE_ACTIVE,
            "pinned": False,
            "archived_at": None,
        }

    @staticmethod
    def _parse_iso(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
