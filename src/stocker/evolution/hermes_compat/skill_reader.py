"""Hermes-compatible skill reader.

Upstream reference: `hermes-agent/tools/skills_tool.py`.
Local deviations: project-local skill root, no CLI/tool registry coupling.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stocker.evolution.hermes_compat.skill_schema import markdown_to_skill, parse_frontmatter
from stocker.evolution.models import EvolutionSkill
from stocker.evolution.paths import skills_root

_ALLOWED_SUPPORT_DIRS = {"references", "templates", "scripts", "assets"}
_EXCLUDED_DIRS = {".archive", ".hub", ".git", "node_modules"}
_INJECTION_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous",
    "you are now",
    "disregard your",
    "forget your instructions",
    "new instructions:",
    "system prompt:",
    "<system>",
    "]]>",
)


@dataclass(frozen=True)
class SkillContent:
    success: bool
    name: str = ""
    skill: EvolutionSkill | None = None
    content: str = ""
    path: str = ""
    skill_dir: str = ""
    linked_files: dict[str, list[str]] | None = None
    warnings: list[str] | None = None
    error: str = ""


class SkillReader:
    """Read/list EvolutionSkill files with Hermes-style progressive disclosure."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else skills_root()

    def iter_skill_files(self) -> list[Path]:
        if not self.root.exists():
            return []
        files: list[Path] = []
        for path in self.root.rglob("SKILL.md"):
            rel_parts = path.relative_to(self.root).parts
            if any(part in _EXCLUDED_DIRS or part.startswith(".") for part in rel_parts[:-1]):
                continue
            files.append(path)
        return sorted(files)

    def list_skills(
        self,
        domain: str | None = None,
        team: str | None = None,
        node: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for skill_file in self.iter_skill_files():
            try:
                content = skill_file.read_text(encoding="utf-8")
                frontmatter, _body = parse_frontmatter(content)
                skill = markdown_to_skill(content, fallback_name=skill_file.parent.name)
            except Exception:
                continue
            if domain and skill.domain != domain:
                continue
            if team and skill.team != team:
                continue
            if node and skill.node != node:
                continue
            if status and skill.status != status:
                continue
            result.append({
                "id": skill.id,
                "name": skill.name,
                "description": skill.description,
                "domain": skill.domain,
                "team": skill.team,
                "node": skill.node,
                "skill_type": skill.skill_type,
                "version": skill.version,
                "status": skill.status,
                "risk_level": skill.risk_level,
                "path": str(skill_file),
                "category": self._category_for(skill_file),
                "metadata": frontmatter.get("metadata") if isinstance(frontmatter.get("metadata"), dict) else {},
            })
        return result

    def find_skill_file(
        self,
        name_or_id: str,
        domain: str | None = None,
        team: str | None = None,
        node: str | None = None,
        status: str | None = None,
    ) -> Path | None:
        target = name_or_id.strip()
        for row in self.list_skills(domain=domain, team=team, node=node, status=status):
            if row["id"] == target or row["name"] == target:
                return Path(row["path"])
        candidate = self.root / target / "SKILL.md"
        if candidate.exists():
            return candidate
        return None

    def get_active_skill(
        self,
        domain: str,
        team: str,
        node: str,
        skill_type: str = "prompt_strategy",
    ) -> tuple[EvolutionSkill, Path] | None:
        matches = []
        for row in self.list_skills(domain=domain, team=team, node=node, status="active"):
            if row.get("skill_type") == skill_type:
                matches.append(row)
        if not matches:
            return None
        matches.sort(key=lambda item: int(item.get("version") or 0), reverse=True)
        path = Path(matches[0]["path"])
        skill = markdown_to_skill(path.read_text(encoding="utf-8"), fallback_name=path.parent.name)
        return skill, path

    def view_skill(self, name_or_id: str, file_path: str | None = None) -> SkillContent:
        skill_file = self.find_skill_file(name_or_id)
        if skill_file is None:
            return SkillContent(success=False, error=f"Skill '{name_or_id}' not found")
        skill_dir = skill_file.parent
        try:
            if file_path:
                target = self._resolve_support_file(skill_dir, file_path)
                content = target.read_text(encoding="utf-8")
                skill = markdown_to_skill(skill_file.read_text(encoding="utf-8"), fallback_name=skill_dir.name)
                return SkillContent(
                    success=True,
                    name=skill.name,
                    skill=skill,
                    content=content,
                    path=str(target),
                    skill_dir=str(skill_dir),
                    warnings=self._warnings_for(content),
                )
            content = skill_file.read_text(encoding="utf-8")
            skill = markdown_to_skill(content, fallback_name=skill_dir.name)
            return SkillContent(
                success=True,
                name=skill.name,
                skill=skill,
                content=skill.body,
                path=str(skill_file),
                skill_dir=str(skill_dir),
                linked_files=self._linked_files(skill_dir),
                warnings=self._warnings_for(content),
            )
        except Exception as exc:
            return SkillContent(success=False, error=str(exc))

    def _resolve_support_file(self, skill_dir: Path, file_path: str) -> Path:
        rel = Path(file_path)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("file_path must be relative and stay inside the skill directory")
        if rel.parts and rel.parts[0] not in _ALLOWED_SUPPORT_DIRS:
            raise ValueError(f"file_path must start with one of {sorted(_ALLOWED_SUPPORT_DIRS)}")
        target = (skill_dir / rel).resolve()
        root = skill_dir.resolve()
        target.relative_to(root)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(str(rel))
        return target

    def _linked_files(self, skill_dir: Path) -> dict[str, list[str]] | None:
        linked: dict[str, list[str]] = {}
        for dirname in sorted(_ALLOWED_SUPPORT_DIRS):
            directory = skill_dir / dirname
            if not directory.exists():
                continue
            files = [str(path.relative_to(skill_dir)) for path in sorted(directory.rglob("*")) if path.is_file()]
            if files:
                linked[dirname] = files
        return linked or None

    def _warnings_for(self, content: str) -> list[str]:
        lower = content.lower()
        warnings: list[str] = []
        if any(pattern in lower for pattern in _INJECTION_PATTERNS):
            warnings.append("skill content contains patterns that may indicate prompt injection")
        return warnings

    def _category_for(self, skill_file: Path) -> str | None:
        try:
            rel = skill_file.relative_to(self.root)
        except ValueError:
            return None
        parts = rel.parts
        return parts[0] if len(parts) >= 3 else None
