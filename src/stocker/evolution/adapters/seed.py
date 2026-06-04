"""Default seed EvolutionSkill assets for Stocker teams."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from stocker.evolution.adapters.stocker_validator import validate_skill
from stocker.evolution.hermes_compat.skill_manager import SkillManager
from stocker.evolution.hermes_compat.skill_reader import SkillReader
from stocker.evolution.hermes_compat.skill_schema import skill_to_markdown
from stocker.evolution.models import EvolutionSkill



_SEEDS = [
    EvolutionSkill(
        id="stocker.intelligence.market_data.baseline",
        name="market-data-baseline",
        description="Baseline analysis strategy for market data analyst nodes.",
        team="intelligence",
        node="market_data",
        status="active",
        risk_level="low",
        created_by="system",
        body=(
            "## Strategy\n"
            "Use only data already present in shared_data. Highlight trend, volatility, support/resistance, and data quality.\n\n"
            "## Anti-patterns\n"
            "Do not introduce fallback data sources. If data is missing, downgrade confidence and expose the warning.\n\n"
            "## Output contract\n"
            "Return concise evidence, uncertainty, and actionable implications."
        ),
    ),
    EvolutionSkill(
        id="stocker.intelligence.news.baseline",
        name="news-baseline",
        description="Baseline strategy for news and event analysis.",
        team="intelligence",
        node="news",
        status="active",
        risk_level="low",
        created_by="system",
        body=(
            "## Strategy\n"
            "Classify news by relevance, recency, event type, and likely position impact.\n\n"
            "## Anti-patterns\n"
            "Do not invent events. Missing news means lower confidence, not synthetic evidence.\n\n"
            "## Output contract\n"
            "Return key events, impact direction, urgency, and data-quality notes."
        ),
    ),
    EvolutionSkill(
        id="stocker.risk.research_manager.baseline",
        name="research-manager-baseline",
        description="Baseline strategy for balancing bull and bear research evidence.",
        team="risk",
        node="research_manager",
        status="active",
        risk_level="medium",
        created_by="system",
        body=(
            "## Strategy\n"
            "Compare bull and bear arguments by evidence quality, data freshness, and downside asymmetry.\n\n"
            "## Anti-patterns\n"
            "Do not let persuasive wording override missing or stale data.\n\n"
            "## Output contract\n"
            "Return the strongest bull case, strongest bear case, unresolved risks, and a clear investment stance."
        ),
    ),
    EvolutionSkill(
        id="stocker.risk.trader.baseline",
        name="trader-baseline",
        description="Baseline high-risk strategy for turning research into controlled trade plans.",
        team="risk",
        node="trader",
        status="draft",
        risk_level="high",
        created_by="system",
        requires_approval=True,
        body=(
            "## Strategy\n"
            "Convert the investment plan into an entry, stop, target, invalidation, and position-size proposal anchored to current market data and configured risk limits.\n\n"
            "## Anti-patterns\n"
            "Never bypass execution mode, user confirmation, or strategy validators. Never reuse stale absolute prices.\n\n"
            "## Output contract\n"
            "Return Current Price, Entry, Stop Loss, Target, Position Size, Risk:Reward, and Invalidation."
        ),
    ),
    EvolutionSkill(
        id="stocker.risk.portfolio_manager.baseline",
        name="portfolio-manager-baseline",
        description="Baseline high-risk strategy for final portfolio risk decisions.",
        team="risk",
        node="portfolio_manager",
        status="draft",
        risk_level="high",
        created_by="system",
        requires_approval=True,
        body=(
            "## Strategy\n"
            "Approve only decisions with explicit downside, data-quality, and portfolio-impact checks.\n\n"
            "## Anti-patterns\n"
            "Do not turn analysis into automatic real trading or relax risk limits without approval.\n\n"
            "## Output contract\n"
            "Return action, confidence, risk_score, rationale, and safety notes."
        ),
    ),
    EvolutionSkill(
        id="stocker.supervisor.supervisor.baseline",
        name="supervisor-baseline",
        description="Baseline high-risk routing strategy for Supervisor tool selection.",
        team="supervisor",
        node="supervisor",
        status="draft",
        risk_level="high",
        created_by="system",
        requires_approval=True,
        body=(
            "## Strategy\n"
            "Route user requests to the narrowest safe tool. Prefer observe-mode analysis unless the user explicitly asks for an allowed action.\n\n"
            "## Anti-patterns\n"
            "Do not bypass execution_mode, do not auto-place real orders, and do not infer missing user confirmation.\n\n"
            "## Output contract\n"
            "When trading-related, state whether the next step is analysis, draft plan, simulated execution, or rejected unsafe action."
        ),
    ),
]


def seed_default_skills(root: str | Path | None = None, overwrite: bool = False) -> dict[str, Any]:
    """Create baseline skills if absent. High-risk seeds remain draft."""
    manager = SkillManager(root)
    reader = SkillReader(root)
    created: list[str] = []
    skipped: list[str] = []
    errors: dict[str, str] = {}
    for skill in _SEEDS:
        existing = reader.find_skill_file(skill.id)
        validation = validate_skill(skill)
        if not validation.ok:
            errors[skill.id] = "; ".join(validation.errors)
            continue
        if existing and not overwrite:
            skipped.append(skill.id)
            continue
        if existing and overwrite:
            result = manager.edit(skill.id, skill_to_markdown(skill))
        else:
            result = manager.create(skill)

        if result.get("success"):
            created.append(skill.id)
        else:
            errors[skill.id] = str(result.get("error"))
    return {"created": created, "skipped": skipped, "errors": errors}
