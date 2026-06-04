"""Deterministic weekly review report for EvolutionSkill runtime."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from stocker.evolution.adapters.patch_store import PatchStore
from stocker.evolution.adapters.trace_store import TraceStore
from stocker.evolution.hermes_compat.curator import SkillCurator
from stocker.evolution.paths import reviews_root
from stocker.utils.helpers import atomic_json_write


class WeeklyEvolutionReview:
    """Summarize skills, traces, patches, and curator signals without LLM calls."""

    def __init__(
        self,
        *,
        skills_dir: str | Path | None = None,
        traces_dir: str | Path | None = None,
        patches_dir: str | Path | None = None,
        review_dir: str | Path | None = None,
    ) -> None:
        self.curator = SkillCurator(skills_dir)
        self.traces = TraceStore(traces_dir)
        self.patches = PatchStore(patches_dir, skills_dir=skills_dir)
        self.review_dir = Path(review_dir) if review_dir is not None else reviews_root()

    def generate(self, trace_limit: int = 500, persist: bool = True) -> dict[str, Any]:
        curator_report = self.curator.report()
        traces = self.traces.list_recent(limit=trace_limit)
        patches = self.patches.list_patches(limit=200)
        usage = curator_report.get("usage", [])
        skills = curator_report.get("skills", [])

        by_node = Counter(f"{row.get('team')}/{row.get('node')}" for row in traces)
        warning_counter: Counter[str] = Counter()
        for row in traces:
            for warning in row.get("data_warnings") or []:
                warning_counter[str(warning)] += 1

        pending_patches = [p for p in patches if p.get("status") in {"draft", "validated", "approved"}]
        stale_usage = [u for u in usage if u.get("state") == "stale"]
        archived_usage = [u for u in usage if u.get("state") == "archived"]

        recommendations: list[str] = []
        if pending_patches:
            recommendations.append(f"Review {len(pending_patches)} pending evolution patch draft(s) before activating strategy changes.")
        if stale_usage:
            recommendations.append(f"Inspect {len(stale_usage)} stale skill(s); pin useful user assets or archive obsolete reviewer-created skills.")
        if warning_counter:
            most_common = warning_counter.most_common(3)
            recommendations.append("Prioritize data-quality improvements for frequent warnings: " + ", ".join(k for k, _ in most_common))
        if not traces:
            recommendations.append("No recent node traces found; run LangGraph analysis/risk flows before strategy review.")
        if not skills:
            recommendations.append("No EvolutionSkill assets found; seed baseline skills for intelligence, risk, and supervisor teams.")

        report = {
            "generated_at": datetime.now().isoformat(),
            "stats": {
                "skills": len(skills),
                "usage_records": len(usage),
                "traces": len(traces),
                "patches": len(patches),
                "pending_patches": len(pending_patches),
                "stale_skills": len(stale_usage),
                "archived_skills": len(archived_usage),
            },
            "top_nodes": by_node.most_common(10),
            "top_data_warnings": warning_counter.most_common(10),
            "pending_patches": pending_patches[:20],
            "stale_skills": stale_usage[:20],
            "recommendations": recommendations,
        }
        if persist:
            self.save(report)
        return report

    def save(self, report: dict[str, Any]) -> Path:
        self.review_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = self.review_dir / f"{stamp}-weekly-review.json"
        atomic_json_write(path, report)
        return path
