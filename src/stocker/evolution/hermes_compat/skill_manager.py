"""Hermes-compatible skill manager.

Upstream reference: `hermes-agent/tools/skill_manager_tool.py`.
Local deviations: no tool registry, no hard delete by default, Stocker-specific
activation policy is delegated to adapters.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from stocker.evolution.hermes_compat.skill_reader import SkillReader
from stocker.evolution.hermes_compat.skill_schema import skill_to_markdown
from stocker.evolution.hermes_compat.skill_usage import SkillUsageStore
from stocker.evolution.models import EvolutionSkill
from stocker.evolution.paths import skills_root

_ALLOWED_SUPPORT_DIRS = {"references", "templates", "scripts", "assets"}
_VALID_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_MAX_SKILL_CONTENT_CHARS = 100_000
_MAX_SUPPORT_FILE_BYTES = 1_048_576


class SkillManager:
    """Create, patch, archive, and manage Hermes-compatible skill files."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else skills_root()
        self.reader = SkillReader(self.root)
        self.usage = SkillUsageStore(self.root)

    def create(self, skill: EvolutionSkill) -> dict[str, Any]:
        err = self._validate_skill(skill)
        if err:
            return {"success": False, "error": err}
        skill_dir = self._skill_dir(skill)
        if skill_dir.exists():
            return {"success": False, "error": f"Skill already exists: {skill.id}"}
        skill_dir.mkdir(parents=True, exist_ok=True)
        for subdir in sorted(_ALLOWED_SUPPORT_DIRS):
            (skill_dir / subdir).mkdir(exist_ok=True)
        self._write_text(skill_dir / "SKILL.md", skill_to_markdown(skill))
        self.usage.mark_created(skill.id, skill.created_by)
        return {"success": True, "path": str(skill_dir / "SKILL.md"), "id": skill.id}

    def edit(self, name_or_id: str, content: str) -> dict[str, Any]:
        if len(content) > _MAX_SKILL_CONTENT_CHARS:
            return {"success": False, "error": "SKILL.md content is too large"}
        skill_file = self.reader.find_skill_file(name_or_id)
        if skill_file is None:
            return {"success": False, "error": f"Skill not found: {name_or_id}"}
        self._write_text(skill_file, content)
        self.usage.bump_patch(name_or_id)
        return {"success": True, "path": str(skill_file)}

    def patch(
        self,
        name_or_id: str,
        old_string: str,
        new_string: str,
        file_path: str | None = None,
        replace_all: bool = False,
    ) -> dict[str, Any]:
        skill_file = self.reader.find_skill_file(name_or_id)
        if skill_file is None:
            return {"success": False, "error": f"Skill not found: {name_or_id}"}
        target = self._support_path(skill_file.parent, file_path) if file_path else skill_file
        content = target.read_text(encoding="utf-8")
        if old_string not in content:
            return {"success": False, "error": "old_string not found"}
        if not replace_all and content.count(old_string) > 1:
            return {"success": False, "error": "old_string is not unique; set replace_all=true or provide more context"}
        updated = content.replace(old_string, new_string, -1 if replace_all else 1)
        self._write_text(target, updated)
        self.usage.bump_patch(self._skill_id(skill_file))
        return {"success": True, "path": str(target)}

    def write_file(self, name_or_id: str, file_path: str, file_content: str) -> dict[str, Any]:
        if len(file_content.encode("utf-8")) > _MAX_SUPPORT_FILE_BYTES:
            return {"success": False, "error": "support file is too large"}
        skill_file = self.reader.find_skill_file(name_or_id)
        if skill_file is None:
            return {"success": False, "error": f"Skill not found: {name_or_id}"}
        target = self._support_path(skill_file.parent, file_path, must_exist=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._write_text(target, file_content)
        self.usage.bump_patch(self._skill_id(skill_file))
        return {"success": True, "path": str(target)}

    def remove_file(self, name_or_id: str, file_path: str) -> dict[str, Any]:
        skill_file = self.reader.find_skill_file(name_or_id)
        if skill_file is None:
            return {"success": False, "error": f"Skill not found: {name_or_id}"}
        target = self._support_path(skill_file.parent, file_path)
        target.unlink()
        self.usage.bump_patch(self._skill_id(skill_file))
        return {"success": True, "path": str(target)}

    def archive(self, name_or_id: str) -> dict[str, Any]:
        skill_file = self.reader.find_skill_file(name_or_id)
        if skill_file is None:
            return {"success": False, "error": f"Skill not found: {name_or_id}"}
        skill = self.reader.view_skill(name_or_id).skill
        if skill and skill.pinned:
            return {"success": False, "error": f"Skill is pinned: {name_or_id}"}
        archive_root = self.root / ".archive"
        archive_root.mkdir(parents=True, exist_ok=True)
        dest = archive_root / skill_file.parent.name
        if dest.exists():
            suffix = re.sub(r"[^0-9]", "", skill_file.stat().st_mtime_ns.__str__())
            dest = archive_root / f"{skill_file.parent.name}-{suffix}"
        shutil.move(str(skill_file.parent), str(dest))
        self.usage.set_state(skill.id if skill else name_or_id, "archived")
        return {"success": True, "path": str(dest)}

    def _skill_dir(self, skill: EvolutionSkill) -> Path:
        return self.root / skill.domain / skill.team / skill.name

    def _skill_id(self, skill_file: Path) -> str:
        content = skill_file.read_text(encoding="utf-8")
        return self.reader.view_skill(skill_file.parent.name).skill.id if self.reader.view_skill(skill_file.parent.name).skill else skill_file.parent.name

    def _support_path(self, skill_dir: Path, file_path: str | None, must_exist: bool = True) -> Path:
        if not file_path:
            raise ValueError("file_path is required")
        rel = Path(file_path)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("file_path must be relative and stay inside the skill directory")
        if not rel.parts or rel.parts[0] not in _ALLOWED_SUPPORT_DIRS:
            raise ValueError(f"file_path must start with one of {sorted(_ALLOWED_SUPPORT_DIRS)}")
        target = (skill_dir / rel).resolve()
        target.relative_to(skill_dir.resolve())
        if must_exist and not target.exists():
            raise FileNotFoundError(file_path)
        return target

    def _validate_skill(self, skill: EvolutionSkill) -> str | None:
        if not _VALID_NAME_RE.match(skill.name):
            return "Invalid skill name; use lowercase letters, numbers, dots, underscores, and hyphens"
        if not skill.description.strip():
            return "description is required"
        if not skill.body.strip():
            return "body is required"
        if len(skill_to_markdown(skill)) > _MAX_SKILL_CONTENT_CHARS:
            return "SKILL.md content is too large"
        return None

    @staticmethod
    def _write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
