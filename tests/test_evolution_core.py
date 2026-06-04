from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _skill():
    from stocker.evolution.models import EvolutionSkill

    return EvolutionSkill(
        id="stocker.risk.trader.swing-plan",
        name="swing-plan",
        description="This skill guides swing trading plan generation.",
        domain="stocker",
        team="risk",
        node="trader",
        status="active",
        risk_level="high",
        requires_approval=True,
        body="## Trigger\nUse for trader node.\n\n## Strategy\nAnchor prices to current data.",
    )


def test_skill_manager_reader_patch_and_usage(tmp_path):
    from stocker.evolution.hermes_compat.skill_manager import SkillManager
    from stocker.evolution.hermes_compat.skill_reader import SkillReader
    from stocker.evolution.hermes_compat.skill_usage import SkillUsageStore

    manager = SkillManager(tmp_path / "skills")
    created = manager.create(_skill())
    assert created["success"] is True

    reader = SkillReader(tmp_path / "skills")
    rows = reader.list_skills(domain="stocker", team="risk", node="trader", status="active")
    assert len(rows) == 1
    assert rows[0]["id"] == "stocker.risk.trader.swing-plan"

    viewed = reader.view_skill("stocker.risk.trader.swing-plan")
    assert viewed.success is True
    assert viewed.skill is not None
    assert viewed.skill.requires_approval is True

    patched = manager.patch(
        "stocker.risk.trader.swing-plan",
        "Anchor prices to current data.",
        "Anchor prices to current market data and configured risk limits.",
    )
    assert patched["success"] is True
    assert "configured risk limits" in reader.view_skill("stocker.risk.trader.swing-plan").content

    usage = SkillUsageStore(tmp_path / "skills")
    rec = usage.get_record("stocker.risk.trader.swing-plan")
    assert rec["patch_count"] >= 1


def test_prompt_resolver_injects_active_skill(tmp_path):
    from stocker.evolution.adapters.langgraph_prompt_resolver import PromptResolver
    from stocker.evolution.hermes_compat.skill_manager import SkillManager

    manager = SkillManager(tmp_path / "skills")
    assert manager.create(_skill())["success"] is True

    resolver = PromptResolver(tmp_path / "skills")
    resolved = resolver.resolve(
        team="risk",
        node="trader",
        base_prompt="Base trader prompt.",
        state={"ticker": "AAPL"},
    )

    assert resolved.injected is True
    assert resolved.skill_id == "stocker.risk.trader.swing-plan"
    assert "Evolution Skill" in resolved.prompt
    assert "Base trader prompt." in resolved.prompt


def test_trace_store_records_jsonl(tmp_path):
    from stocker.evolution.adapters.trace_store import TraceStore
    from stocker.evolution.models import NodeTrace

    store = TraceStore(tmp_path / "traces")
    store.record_node_run(NodeTrace(team="risk", node="trader", ticker="AAPL"))
    rows = store.list_recent()

    assert len(rows) == 1
    assert rows[0]["team"] == "risk"
    assert rows[0]["node"] == "trader"
