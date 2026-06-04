"""Patch draft store and safe application helpers for EvolutionSkill."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from stocker.evolution.adapters.approval_policy import requires_human_or_simulation_approval
from stocker.evolution.adapters.stocker_validator import validate_patch
from stocker.evolution.hermes_compat.skill_manager import SkillManager
from stocker.evolution.hermes_compat.skill_reader import SkillReader
from stocker.evolution.hermes_compat.skill_schema import skill_to_markdown
from stocker.evolution.models import SkillPatchDraft
from stocker.evolution.paths import patches_root

from stocker.utils.helpers import atomic_json_write, json_read


class PatchStore:
    """Persist, validate, approve, and apply reviewer patch drafts.

    Patch drafts are JSON files under `data/evolution/patches`. Applying a patch
    is explicit and gated by Stocker validation rules; high-risk patches must be
    approved before application.
    """

    def __init__(self, root: str | Path | None = None, skills_dir: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else patches_root()
        self.reader = SkillReader(skills_dir)
        self.manager = SkillManager(skills_dir)

    def save(self, patch: SkillPatchDraft) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{patch.patch_id}.json"
        atomic_json_write(path, patch.model_dump(mode="json"))
        return path

    def load(self, patch_id: str) -> SkillPatchDraft | None:
        path = self.root / f"{patch_id}.json"
        data = json_read(path, default=None)
        if not isinstance(data, dict):
            return None
        return SkillPatchDraft(**data)

    def list_patches(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            data = json_read(path, default=None)
            if not isinstance(data, dict):
                continue
            if status and data.get("status") != status:
                continue
            rows.append(data)
            if len(rows) >= limit:
                break
        return rows

    def validate(self, patch_id: str) -> dict[str, Any]:
        patch = self.load(patch_id)
        if patch is None:
            return {"success": False, "error": f"Patch not found: {patch_id}"}
        target_node = self._target_node(patch.target_skill_id)
        result = validate_patch(patch, target_node=target_node)
        patch.status = "validated" if result.ok else "rejected"
        patch.metadata = {**patch.metadata, "validation": result.model_dump(mode="json")}
        self.save(patch)
        return {"success": result.ok, "patch": patch.model_dump(mode="json"), "validation": result.model_dump(mode="json")}

    def approve(
        self,
        patch_id: str,
        approved_by: str = "user",
        evidence_ids: list[str] | None = None,
        evidence_note: str = "",
    ) -> dict[str, Any]:
        patch = self.load(patch_id)
        if patch is None:
            return {"success": False, "error": f"Patch not found: {patch_id}"}
        validation = validate_patch(patch, target_node=self._target_node(patch.target_skill_id))
        if not validation.ok:
            patch.status = "rejected"
            patch.metadata = {**patch.metadata, "validation": validation.model_dump(mode="json")}
            self.save(patch)
            return {"success": False, "patch": patch.model_dump(mode="json"), "validation": validation.model_dump(mode="json")}
        patch.status = "approved"
        patch.metadata = {
            **patch.metadata,
            "approved_by": approved_by,
            "approval_evidence_ids": [str(item) for item in (evidence_ids or []) if str(item).strip()],
            "approval_evidence_note": evidence_note,
            "validation": validation.model_dump(mode="json"),
        }
        self.save(patch)
        return {"success": True, "patch": patch.model_dump(mode="json"), "validation": validation.model_dump(mode="json")}


    def apply(self, patch_id: str) -> dict[str, Any]:
        patch = self.load(patch_id)
        if patch is None:
            return {"success": False, "error": f"Patch not found: {patch_id}"}
        viewed = self.reader.view_skill(patch.target_skill_id)
        if not viewed.success or viewed.skill is None:
            return {"success": False, "error": f"Target skill not found: {patch.target_skill_id}"}

        validation = validate_patch(patch, target_node=viewed.skill.node)
        if not validation.ok:
            patch.status = "rejected"
            patch.metadata = {**patch.metadata, "validation": validation.model_dump(mode="json")}
            self.save(patch)
            return {"success": False, "patch": patch.model_dump(mode="json"), "validation": validation.model_dump(mode="json")}

        requires_gate = requires_human_or_simulation_approval(skill=viewed.skill, patch=patch, node=viewed.skill.node)
        if requires_gate and patch.status != "approved":
            patch.status = "validated"
            patch.metadata = {**patch.metadata, "validation": validation.model_dump(mode="json")}
            self.save(patch)
            return {
                "success": False,
                "error": "Patch requires approval before apply",
                "patch": patch.model_dump(mode="json"),
                "validation": validation.model_dump(mode="json"),
            }
        if requires_gate and not self._has_simulation_or_backtest_evidence(patch):
            patch.metadata = {**patch.metadata, "validation": validation.model_dump(mode="json")}
            self.save(patch)
            return {
                "success": False,
                "error": "High-risk patch requires paper/backtest evidence before apply",
                "patch": patch.model_dump(mode="json"),
                "validation": validation.model_dump(mode="json"),
            }

        if patch.old_text:

            result = self.manager.patch(patch.target_skill_id, patch.old_text, patch.new_text)
        else:
            skill = viewed.skill.model_copy()
            skill.version = patch.proposed_version
            skill.body = skill.body.rstrip() + "\n" + patch.new_text.strip() + "\n"
            result = self.manager.edit(patch.target_skill_id, skill_to_markdown(skill))
        if not result.get("success"):
            return {"success": False, "error": result.get("error"), "patch": patch.model_dump(mode="json")}

        patch.status = "applied"
        patch.metadata = {**patch.metadata, "applied_path": result.get("path"), "validation": validation.model_dump(mode="json")}
        self.save(patch)
        return {"success": True, "patch": patch.model_dump(mode="json"), "result": result}

    def _target_node(self, skill_id: str) -> str | None:
        viewed = self.reader.view_skill(skill_id)
        if viewed.success and viewed.skill is not None:
            return viewed.skill.node
        return None

    @staticmethod
    def _has_simulation_or_backtest_evidence(patch: SkillPatchDraft) -> bool:
        evidence_ids = patch.metadata.get("approval_evidence_ids") or []
        if not isinstance(evidence_ids, list):
            evidence_ids = [evidence_ids]
        allowed_prefixes = ("paper:", "paper-", "sim:", "simulation:", "backtest:", "backtest-")
        return any(str(item).lower().startswith(allowed_prefixes) for item in evidence_ids)

