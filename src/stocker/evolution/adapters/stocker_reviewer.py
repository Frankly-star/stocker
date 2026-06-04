"""Reviewer adapter that turns Stocker reflections/traces into patch drafts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from stocker.evolution.hermes_compat.skill_reader import SkillReader
from stocker.evolution.models import SkillPatchDraft
from stocker.evolution.paths import patches_root
from stocker.utils.helpers import atomic_json_write


class StockerEvolutionReviewer:
    """Create patch drafts from review evidence. It never applies patches."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.reader = SkillReader(root)
        if root is None:
            self.patch_root = patches_root()
        else:
            root_path = Path(root)
            self.patch_root = root_path.parent / "patches"


    def propose_patch_from_reflection(
        self,
        *,
        target_skill_id: str,
        reflection: str,
        reason: str,
        evidence_trace_ids: list[str] | None = None,
        risk_level: str = "medium",
    ) -> SkillPatchDraft | None:
        skill_file = self.reader.find_skill_file(target_skill_id)
        if skill_file is None:
            return None
        skill = self.reader.view_skill(target_skill_id).skill
        if skill is None:
            return None
        addition = (
            "\n\n## Learned Improvement Draft\n"
            f"Reason: {reason}\n\n"
            f"Reflection:\n{reflection.strip()}\n"
        )
        patch = SkillPatchDraft(
            target_skill_id=skill.id,
            target_version=skill.version,
            proposed_version=skill.version + 1,
            old_text=None,
            new_text=addition,
            reason=reason,
            evidence_trace_ids=evidence_trace_ids or [],
            risk_level=risk_level,  # type: ignore[arg-type]
        )
        self.save_patch(patch)
        return patch

    def save_patch(self, patch: SkillPatchDraft) -> Path:
        self.patch_root.mkdir(parents=True, exist_ok=True)
        path = self.patch_root / f"{patch.patch_id}.json"
        atomic_json_write(path, patch.model_dump(mode="json"))
        return path
