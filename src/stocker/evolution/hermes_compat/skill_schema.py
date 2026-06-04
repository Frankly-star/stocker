"""Hermes-compatible SKILL.md parsing and rendering.

Upstream reference: `hermes-agent/tools/skills_tool.py` and
`hermes-agent/tools/skill_manager_tool.py` frontmatter handling.
Local deviations: minimal YAML parser fallback; Stocker-specific EvolutionSkill
fields are accepted but not required for generic Hermes compatibility.
"""

from __future__ import annotations

import re
from typing import Any

from stocker.evolution.models import EvolutionSkill

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "none"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [part.strip().strip('"\'') for part in inner.split(",")]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value.strip('"\'')


def _fallback_parse_yaml(raw: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_key: str | None = None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  ") and current_key:
            child = line.strip()
            if ":" in child:
                key, value = child.split(":", 1)
                parent = data.setdefault(current_key, {})
                if isinstance(parent, dict):
                    parent[key.strip()] = _parse_scalar(value)
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        current_key = key
        data[key] = _parse_scalar(value) if value.strip() else {}
    return data


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter, body) from a SKILL.md string."""
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content.strip()
    raw, body = match.group(1), match.group(2).strip()
    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(raw) or {}
        if isinstance(parsed, dict):
            return parsed, body
    except Exception:
        pass
    return _fallback_parse_yaml(raw), body


def render_frontmatter(data: dict[str, Any]) -> str:
    """Render a simple YAML frontmatter block without requiring PyYAML."""
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif value is None:
            rendered = "null"
        elif isinstance(value, (list, tuple)):
            rendered = "[" + ", ".join(str(v) for v in value) + "]"
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            for child_key, child_value in value.items():
                lines.append(f"  {child_key}: {child_value}")
            continue
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}")
    lines.append("---")
    return "\n".join(lines)


def skill_to_markdown(skill: EvolutionSkill) -> str:
    frontmatter = {
        "name": skill.name,
        "description": skill.description,
        "id": skill.id,
        "domain": skill.domain,
        "team": skill.team,
        "node": skill.node,
        "skill_type": skill.skill_type,
        "version": skill.version,
        "status": skill.status,
        "risk_level": skill.risk_level,
        "created_by": skill.created_by,
        "requires_approval": skill.requires_approval,
        "pinned": skill.pinned,
        "source": skill.source,
    }
    if skill.metadata:
        frontmatter["metadata"] = skill.metadata
    return f"{render_frontmatter(frontmatter)}\n\n{skill.body.strip()}\n"


def markdown_to_skill(content: str, fallback_name: str = "") -> EvolutionSkill:
    frontmatter, body = parse_frontmatter(content)
    name = str(frontmatter.get("name") or fallback_name).strip()
    skill_id = str(frontmatter.get("id") or name).strip()
    return EvolutionSkill(
        id=skill_id,
        name=name,
        description=str(frontmatter.get("description") or "Evolution skill"),
        domain=str(frontmatter.get("domain") or "stocker"),
        team=str(frontmatter.get("team") or "general"),
        node=str(frontmatter.get("node") or name or "general"),
        skill_type=str(frontmatter.get("skill_type") or "prompt_strategy"),
        version=int(frontmatter.get("version") or 1),
        status=str(frontmatter.get("status") or "draft"),
        risk_level=str(frontmatter.get("risk_level") or "low"),
        created_by=str(frontmatter.get("created_by") or "system"),
        requires_approval=bool(frontmatter.get("requires_approval") or False),
        pinned=bool(frontmatter.get("pinned") or False),
        source=str(frontmatter.get("source") or "stocker_adapter"),
        body=body,
        metadata=frontmatter.get("metadata") if isinstance(frontmatter.get("metadata"), dict) else {},
    )
