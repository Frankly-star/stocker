"""Prompt resolution adapter for LangGraph team nodes."""

from __future__ import annotations

import hashlib
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from stocker.evolution.hermes_compat.prompt_guidance import EVOLUTION_SKILLS_GUIDANCE
from stocker.evolution.hermes_compat.skill_reader import SkillReader
from stocker.evolution.hermes_compat.skill_usage import SkillUsageStore
from stocker.evolution.models import ResolvedPrompt
from stocker.evolution.paths import skills_root

logger = logging.getLogger(__name__)


def _hash_prompt(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class PromptResolver:
    """Inject active EvolutionSkill content into a LangGraph node prompt."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else skills_root()
        self.reader = SkillReader(self.root)
        self.usage = SkillUsageStore(self.root)

    def resolve(
        self,
        *,
        team: str,
        node: str,
        base_prompt: str,
        state: dict | None = None,
        domain: str = "stocker",
        skill_type: str = "prompt_strategy",
    ) -> ResolvedPrompt:
        active = self.reader.get_active_skill(domain=domain, team=team, node=node, skill_type=skill_type)
        if active is None:
            return ResolvedPrompt(prompt=base_prompt, prompt_hash=_hash_prompt(base_prompt), injected=False)
        skill, path = active
        block = (
            "\n\n---\n"
            f"## Evolution Skill: {skill.id} v{skill.version}\n"
            f"Risk level: {skill.risk_level}; status: {skill.status}\n\n"
            f"{EVOLUTION_SKILLS_GUIDANCE}\n"
            f"{skill.body.strip()}\n"
            "---\n"
        )
        prompt = base_prompt.rstrip() + block
        self.usage.bump_use(skill.id)
        return ResolvedPrompt(
            prompt=prompt,
            skill_id=skill.id,
            skill_version=skill.version,
            skill_path=str(path),
            prompt_hash=_hash_prompt(prompt),
            injected=True,
        )


@lru_cache(maxsize=1)
def default_prompt_resolver() -> PromptResolver:
    return PromptResolver()


def resolve_prompt(
    *,
    team: str,
    node: str,
    base_prompt: str,
    state: dict | None = None,
    domain: str = "stocker",
    skill_type: str = "prompt_strategy",
) -> ResolvedPrompt:
    """Best-effort prompt resolution. Failures return the base prompt."""
    try:
        return default_prompt_resolver().resolve(
            team=team,
            node=node,
            base_prompt=base_prompt,
            state=state,
            domain=domain,
            skill_type=skill_type,
        )
    except Exception as exc:
        logger.warning("Evolution prompt resolution failed for %s/%s: %s", team, node, exc)
        return ResolvedPrompt(prompt=base_prompt, prompt_hash=_hash_prompt(base_prompt), injected=False)
