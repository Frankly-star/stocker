from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_reports_api_reads_canonical_analysis_cache(monkeypatch, tmp_path):
    from stocker.agents.supervisor import AnalysisCache
    from stocker.analysis.models import MarketIntelligenceReport
    from stocker.api.routes import create_router

    monkeypatch.chdir(tmp_path)

    cache = AnalysisCache()
    cache.save(
        "AAPL",
        MarketIntelligenceReport(
            ticker="AAPL",
            timestamp=datetime(2026, 5, 7, 21, 51),
            current_price=123.45,
            market_environment="trending_up",
            raw_reports={"market": "Market report with real westock-data content " * 4},
            data_quality="good",
            data_sources_used=["westock:quote", "finance-news-rss:ticker"],
        ),
    )

    app = FastAPI()
    app.include_router(create_router(), prefix="/api/v1")
    client = TestClient(app)

    response = client.get("/api/v1/reports")

    assert response.status_code == 200
    reports = response.json()["reports"]
    assert len(reports) == 1
    assert reports[0]["ticker"] == "AAPL"
    assert reports[0]["date"] == "2026-05-07"
    assert reports[0]["environment"] == "trending_up"
    assert reports[0]["summary"].startswith("Market report with real westock-data content")


def test_reports_api_ignores_legacy_report_files(monkeypatch, tmp_path):
    from stocker.agents.supervisor import AnalysisCache
    from stocker.analysis.models import MarketIntelligenceReport
    from stocker.api.routes import create_router

    monkeypatch.chdir(tmp_path)
    data_dir = Path("data")
    data_dir.mkdir(parents=True)
    (data_dir / "analysis_cache.json").write_text('{"LEGACY": {"ticker": "LEGACY"}}', encoding="utf-8")
    (data_dir / "report_legacy.json").write_text('{"ticker": "LEGACY2"}', encoding="utf-8")

    AnalysisCache().save(
        "TSLA",
        MarketIntelligenceReport(
            ticker="TSLA",
            timestamp=datetime(2026, 5, 7, 22, 0),
            raw_reports={"news": "Canonical finance-news RSS report"},
            data_quality="partial",
        ),
    )

    app = FastAPI()
    app.include_router(create_router(), prefix="/api/v1")
    client = TestClient(app)

    reports = client.get("/api/v1/reports").json()["reports"]

    assert [report["ticker"] for report in reports] == ["TSLA"]
