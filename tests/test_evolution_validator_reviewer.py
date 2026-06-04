from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_high_risk_skill_requires_approval():
    from stocker.evolution.adapters.stocker_validator import validate_skill
    from stocker.evolution.models import EvolutionSkill

    skill = EvolutionSkill(
        id="stocker.risk.trader.bad",
        name="bad-trader",
        description="Bad trader skill",
        team="risk",
        node="trader",
        risk_level="high",
        requires_approval=False,
        body="## Strategy\nUse current data.",
    )

    result = validate_skill(skill)
    assert result.ok is False
    assert result.requires_approval is True


def test_validator_rejects_forbidden_data_source():
    from stocker.evolution.adapters.stocker_validator import validate_patch
    from stocker.evolution.models import SkillPatchDraft

    patch = SkillPatchDraft(
        target_skill_id="stocker.intelligence.news",
        target_version=1,
        proposed_version=2,
        new_text="Use yfinance as fallback data source.",
        reason="bad idea",
    )

    result = validate_patch(patch)
    assert result.ok is False
    assert any("data-source" in err for err in result.errors)


def test_reviewer_persists_patch_draft(tmp_path):
    from stocker.evolution.adapters.stocker_reviewer import StockerEvolutionReviewer
    from stocker.evolution.hermes_compat.skill_manager import SkillManager
    from stocker.evolution.models import EvolutionSkill

    skill = EvolutionSkill(
        id="stocker.risk.research_manager.base",
        name="research-manager-base",
        description="Research manager base strategy",
        team="risk",
        node="research_manager",
        status="active",
        body="## Strategy\nWeigh bull and bear evidence.",
    )
    manager = SkillManager(tmp_path / "skills")
    assert manager.create(skill)["success"] is True

    reviewer = StockerEvolutionReviewer(tmp_path / "skills")
    patch = reviewer.propose_patch_from_reflection(
        target_skill_id=skill.id,
        reflection="Require explicit data quality downgrade when sources are missing.",
        reason="reflection",
    )

    assert patch is not None
    assert patch.target_skill_id == skill.id
    assert patch.proposed_version == 2
