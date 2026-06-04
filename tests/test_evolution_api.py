from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKER_DATA_DIR", str(tmp_path / "data"))
    from stocker.api.routes import create_router

    app = FastAPI()
    app.include_router(create_router(), prefix="/api/v1")
    return TestClient(app)


def test_evolution_api_seeds_lists_and_reviews(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    seeded = client.post("/api/v1/evolution/skills/seed-defaults").json()
    assert seeded["success"] is True
    assert "stocker.intelligence.market_data.baseline" in seeded["created"]

    skills = client.get("/api/v1/evolution/skills", params={"team": "intelligence"}).json()["skills"]
    assert any(row["id"] == "stocker.intelligence.market_data.baseline" for row in skills)

    review = client.post("/api/v1/evolution/review/weekly", json={"persist": False}).json()
    assert review["success"] is True
    assert review["review"]["stats"]["skills"] >= 1


def test_evolution_api_patch_validate_and_apply(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.post("/api/v1/evolution/skills/seed-defaults").json()["success"] is True

    from stocker.evolution.adapters.stocker_reviewer import StockerEvolutionReviewer

    reviewer = StockerEvolutionReviewer(tmp_path / "data" / "evolution" / "skills")
    patch = reviewer.propose_patch_from_reflection(
        target_skill_id="stocker.risk.research_manager.baseline",
        reflection="Add explicit data-quality downgrade checks before final stance.",
        reason="api test",
        risk_level="medium",
    )
    assert patch is not None

    listed = client.get("/api/v1/evolution/patches").json()["patches"]
    assert any(row["patch_id"] == patch.patch_id for row in listed)

    validated = client.post(f"/api/v1/evolution/patches/{patch.patch_id}/validate").json()
    assert validated["success"] is True

    applied = client.post(f"/api/v1/evolution/patches/{patch.patch_id}/apply").json()
    assert applied["success"] is True

    viewed = client.get("/api/v1/evolution/skills/stocker.risk.research_manager.baseline").json()
    assert viewed["success"] is True
    assert "data-quality downgrade" in viewed["content"]


def test_evolution_api_high_risk_patch_requires_approval(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.post("/api/v1/evolution/skills/seed-defaults").json()["success"] is True

    from stocker.evolution.adapters.stocker_reviewer import StockerEvolutionReviewer

    reviewer = StockerEvolutionReviewer(tmp_path / "data" / "evolution" / "skills")
    patch = reviewer.propose_patch_from_reflection(
        target_skill_id="stocker.risk.trader.baseline",
        reflection="Require fresh current price in every plan.",
        reason="api test",
        risk_level="high",
    )
    assert patch is not None

    first_apply = client.post(f"/api/v1/evolution/patches/{patch.patch_id}/apply").json()
    assert first_apply["success"] is False
    assert "requires approval" in first_apply["error"]

    approved_without_evidence = client.post(
        f"/api/v1/evolution/patches/{patch.patch_id}/approve",
        json={"approved_by": "tester"},
    ).json()
    assert approved_without_evidence["success"] is True

    second_apply = client.post(f"/api/v1/evolution/patches/{patch.patch_id}/apply").json()
    assert second_apply["success"] is False
    assert "paper/backtest evidence" in second_apply["error"]

    approved = client.post(
        f"/api/v1/evolution/patches/{patch.patch_id}/approve",
        json={"approved_by": "tester", "evidence_ids": ["paper:test-order-1"]},
    ).json()
    assert approved["success"] is True

    applied = client.post(f"/api/v1/evolution/patches/{patch.patch_id}/apply").json()
    assert applied["success"] is True

