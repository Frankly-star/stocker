"""Approval policy for evolution skill activation."""

from __future__ import annotations

from stocker.evolution.models import EvolutionSkill, SkillPatchDraft

_HIGH_RISK_NODES = {"trader", "portfolio_manager", "supervisor"}


def requires_human_or_simulation_approval(skill: EvolutionSkill | None = None, patch: SkillPatchDraft | None = None, node: str | None = None) -> bool:
    if skill is not None:
        return skill.requires_approval or skill.risk_level == "high" or skill.node in _HIGH_RISK_NODES
    if patch is not None:
        return patch.risk_level == "high" or node in _HIGH_RISK_NODES
    return node in _HIGH_RISK_NODES
