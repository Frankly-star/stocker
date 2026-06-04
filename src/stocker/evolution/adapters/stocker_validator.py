"""Stocker-specific validation gates for evolution skill patches."""

from __future__ import annotations

from typing import Iterable

from stocker.evolution.models import EvolutionSkill, SkillPatchDraft, ValidationResult

_FORBIDDEN_DATA_SOURCE_PATTERNS = (
    "yfinance",
    "duckduckgo",
    "ddg",
    "tradingagents",
    "datarouter",
    "futu quote",
    "futu行情",
)
_FORBIDDEN_EXECUTION_PATTERNS = (
    "auto real trade",
    "automatic real trade",
    "自动实盘",
    "跳过确认",
    "绕过确认",
    "bypass execution_mode",
    "ignore execution_mode",
    "直接下单",
)
_HIGH_RISK_NODES = {"trader", "portfolio_manager", "supervisor"}


def validate_skill(skill: EvolutionSkill) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    _check_forbidden(skill.body, errors)
    if skill.node in _HIGH_RISK_NODES and skill.risk_level != "high":
        warnings.append(f"Node {skill.node} is usually high risk; consider risk_level=high")
    requires_approval = skill.risk_level == "high" or skill.node in _HIGH_RISK_NODES
    if requires_approval and not skill.requires_approval:
        errors.append("High-risk evolution skills must require approval")
    return ValidationResult(ok=not errors, errors=errors, warnings=warnings, requires_approval=requires_approval)


def validate_patch(patch: SkillPatchDraft, target_node: str | None = None) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    _check_forbidden(patch.new_text, errors)
    requires_approval = patch.risk_level == "high" or target_node in _HIGH_RISK_NODES
    if requires_approval and patch.status not in {"draft", "validated", "approved"}:
        errors.append("High-risk patch has invalid lifecycle status")
    if requires_approval and patch.status == "applied":
        errors.append("High-risk patch cannot be applied directly")
    return ValidationResult(ok=not errors, errors=errors, warnings=warnings, requires_approval=requires_approval)


def _check_forbidden(text: str, errors: list[str]) -> None:
    lower = text.lower()
    for pattern in _FORBIDDEN_DATA_SOURCE_PATTERNS:
        if pattern in lower:
            errors.append(f"Forbidden data-source instruction detected: {pattern}")
    for pattern in _FORBIDDEN_EXECUTION_PATTERNS:
        if pattern in lower:
            errors.append(f"Forbidden execution-safety instruction detected: {pattern}")


def high_risk_nodes() -> Iterable[str]:
    return sorted(_HIGH_RISK_NODES)
