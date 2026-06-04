"""Pydantic models for the Stocker evolution runtime."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

SkillStatus = Literal["active", "draft", "review", "archived"]
RiskLevel = Literal["low", "medium", "high"]
SkillCreator = Literal["system", "reviewer", "user"]
SkillType = Literal[
    "prompt_strategy",
    "workflow",
    "validation_rule",
    "review_template",
    "support_reference",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvolutionSkill(BaseModel):
    """Generic self-evolving skill bound to a domain/team/node."""

    id: str
    name: str
    description: str
    domain: str = "stocker"
    team: str
    node: str
    skill_type: SkillType = "prompt_strategy"
    version: int = 1
    status: SkillStatus = "draft"
    risk_level: RiskLevel = "low"
    created_by: SkillCreator = "system"
    requires_approval: bool = False
    pinned: bool = False
    source: Literal["hermes_compat", "stocker_adapter", "user"] = "stocker_adapter"
    body: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class SkillBinding(BaseModel):
    """Mapping from a runtime node to an evolution skill."""

    domain: str = "stocker"
    team: str
    node: str
    skill_type: SkillType = "prompt_strategy"
    fallback_behavior: Literal["base_prompt_only", "error"] = "base_prompt_only"


class ResolvedPrompt(BaseModel):
    """Effective prompt after optional evolution skill injection."""

    prompt: str
    skill_id: str | None = None
    skill_version: int | None = None
    skill_path: str | None = None
    prompt_hash: str
    injected: bool = False


class NodeTrace(BaseModel):
    """Append-only trace for a LangGraph node run."""

    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    graph_run_id: str = Field(default_factory=lambda: uuid4().hex)
    domain: str = "stocker"
    team: str
    node: str
    ticker: str | None = None
    trade_date: str | None = None
    skill_id: str | None = None
    skill_version: int | None = None
    prompt_hash: str | None = None
    input_summary: str = ""
    output_summary: str = ""
    data_warnings: list[str] = Field(default_factory=list)
    decision_ref: str | None = None
    started_at: str = Field(default_factory=utc_now_iso)
    ended_at: str = Field(default_factory=utc_now_iso)
    duration_ms: int = 0
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillPatchDraft(BaseModel):
    """Reviewer-produced skill patch proposal. It never auto-applies by itself."""

    patch_id: str = Field(default_factory=lambda: uuid4().hex)
    target_skill_id: str
    target_version: int
    proposed_version: int
    old_text: str | None = None
    new_text: str
    reason: str
    evidence_trace_ids: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = "low"
    status: Literal["draft", "validated", "rejected", "approved", "applied"] = "draft"
    created_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    """Result of validating a skill or patch."""

    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requires_approval: bool = False
