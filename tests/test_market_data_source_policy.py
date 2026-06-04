from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_data_fetcher_uses_only_fixed_sources(monkeypatch):
    from stocker.agents.intelligence import data_fetcher as df_module
    from stocker.skills import westock_data

    calls: list[tuple[str, ...]] = []

    def fake_news(ticker: str, **kwargs):
        return f"news for {ticker}", "global headlines"

    def fake_westock(args, timeout=30):
        calls.append(tuple(args))
        command = args[0]
        return {
            "quote": "price: 100",
            "kline": "date,open,high,low,close,volume\n2026-01-01,1,2,1,2,100",
            "technical": "RSI: 55",
            "finance": "PE: 20",
            "usfund": "fund flow: neutral",
            "hkfund": "fund flow: neutral",
            "asfund": "fund flow: neutral",
            "rating": "rating: buy",
        }[command]

    monkeypatch.setattr(df_module, "_fetch_finance_news_rss", fake_news)
    monkeypatch.setattr(westock_data, "_run_westock", fake_westock)

    node = df_module.create_data_fetcher_node()
    result = node({"ticker": "AAPL", "trade_date": "2026-05-07"})
    shared = result["shared_data"]

    assert shared["source_policy"] == {
        "market_data": "westock-data",
        "news": "finance-news-rss",
        "fallback": "disabled",
    }
    assert shared["sources_used"] == [
        "finance-news-rss:ticker",
        "finance-news-rss:global",
        "westock:quote",
        "westock:kline",
        "westock:technical",
        "westock:finance",
        "westock:fund_flow",
        "westock:rating",
    ]
    assert all(not source.startswith(("yfinance", "ta:", "ddg", "futu")) for source in shared["sources_used"])
    assert calls == [
        ("quote", "usAAPL"),
        ("kline", "usAAPL", "day", "120", "qfq"),
        ("technical", "usAAPL", "all"),
        ("finance", "usAAPL", "4"),
        ("usfund", "usAAPL"),
        ("rating", "usAAPL"),
    ]


def test_data_fetcher_does_not_fallback_when_fixed_sources_fail(monkeypatch):
    from stocker.agents.intelligence import data_fetcher as df_module
    from stocker.skills import westock_data

    calls: list[tuple[str, ...]] = []

    def fake_news(ticker: str, **kwargs):
        return "", ""

    def fake_westock(args, timeout=30):
        calls.append(tuple(args))
        return "westock-data error: unavailable"

    monkeypatch.setattr(df_module, "_fetch_finance_news_rss", fake_news)
    monkeypatch.setattr(westock_data, "_run_westock", fake_westock)

    node = df_module.create_data_fetcher_node()
    shared = node({"ticker": "0700.HK", "trade_date": "2026-05-07"})["shared_data"]

    assert shared["sources_used"] == []
    assert shared["quote"] == ""
    assert shared["kline"] == ""
    assert shared["news"] == ""
    assert any("fallback disabled" in warning for warning in shared["data_warnings"])
    assert all("yfinance" not in warning.lower() for warning in shared["data_warnings"])
    assert calls == [
        ("quote", "hk00700"),
        ("kline", "hk00700", "day", "120", "qfq"),
        ("technical", "hk00700", "all"),
        ("finance", "hk00700", "4"),
        ("hkfund", "hk00700"),
        ("rating", "hk00700"),
    ]


def test_parse_westock_kline_json_records():
    from stocker.utils.data_helpers import parse_westock_kline

    raw = json.dumps({
        "data": [
            {"date": "2026-01-01", "open": 10, "high": 12, "low": 9, "close": 11, "volume": 1000},
            {"date": "2026-01-02", "open": 11, "high": 13, "low": 10, "close": 12, "volume": 1200},
        ]
    })

    df = parse_westock_kline(raw)

    assert df is not None
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(df) == 2
    assert float(df.iloc[-1]["Close"]) == 12.0
