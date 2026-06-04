"""Hermes-compatible curator for evolution skills.

Upstream reference: `hermes-agent/agent/curator.py`.
Local deviations: deterministic lifecycle pass only; LLM consolidation belongs to
Stocker reviewer/adapter and can be added later.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from stocker.evolution.hermes_compat.skill_manager import SkillManager
from stocker.evolution.hermes_compat.skill_reader import SkillReader
from stocker.evolution.hermes_compat.skill_usage import SkillUsageStore
from stocker.evolution.paths import skills_root


class SkillCurator:
    """Lifecycle curator: stale/archive without deleting user assets."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else skills_root()
        self.usage = SkillUsageStore(self.root)
        self.reader = SkillReader(self.root)
        self.manager = SkillManager(self.root)

    def apply_lifecycle(self, stale_after_days: int = 30, archive_after_days: int = 90) -> dict[str, int]:
        """Mark old skills stale/archived; archive moves can be reviewed separately."""
        return self.usage.mark_stale_by_age(stale_after_days, archive_after_days)

    def archive_stale(self) -> dict[str, Any]:
        """Archive non-pinned stale skills by moving directories to .archive."""
        archived: list[str] = []
        errors: dict[str, str] = {}
        records = {row["id"]: row for row in self.usage.report()}
        for row in self.reader.list_skills(status="active") + self.reader.list_skills(status="draft"):
            rec = records.get(row["id"], {})
            if rec.get("state") != "stale" or rec.get("pinned") or rec.get("created_by") == "user":
                continue
            result = self.manager.archive(row["id"])
            if result.get("success"):
                archived.append(row["id"])
            else:
                errors[row["id"]] = str(result.get("error"))
        return {"archived": archived, "errors": errors}

    def report(self) -> dict[str, Any]:
        return {
            "skills": self.reader.list_skills(),
            "usage": self.usage.report(),
        }
