"""Skill adapter for westock-data: Tencent WeStock data API (A-shares, HK, US).

This skill wraps the westock-data Node.js CLI as LangChain tools.
It provides rich Chinese market data that yfinance cannot offer,
including A-share financials, fund flows, chip analysis, and more.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from langchain_core.tools import tool

from stocker.skills.base import SkillAdapter, SkillManifest

logger = logging.getLogger(__name__)

# Path to the westock-data CLI script
_SKILL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "skills" / "westock-data"
_SCRIPT = _SKILL_DIR / "scripts" / "index.js"


def _run_westock(args: list[str], timeout: int = 30) -> str:
    """Execute westock-data CLI command and return output."""
    if not _SCRIPT.exists():
        return f"westock-data script not found at {_SCRIPT}"

    cmd = ["node", str(_SCRIPT)] + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return f"westock-data error: {result.stderr.strip() or 'unknown error'}"
    except subprocess.TimeoutExpired:
        return f"westock-data timeout ({timeout}s)"
    except FileNotFoundError:
        return "Node.js not found. westock-data requires Node.js >= 18."
    except Exception as e:
        return f"westock-data error: {e}"


class WeStockDataSkill(SkillAdapter):

    @property
    def name(self) -> str:
        return "westock-data"

    @property
    def description(self) -> str:
        return (
            "Tencent WeStock data: real-time quotes, K-line, financials, fund flows, "
            "technical indicators, chip analysis, news, ratings for A-shares/HK/US stocks. "
            "No API key needed, optimized for China mainland access."
        )

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name=self.name,
            description=self.description,
            sub_capabilities=[
                "quote", "kline", "finance", "news", "technical",
                "fund_flow", "chip", "rating", "search", "market",
            ],
            version="1.0.0",
        )

    def load(self) -> dict:
        prompt = (
            "You have access to westock-data (腾讯自选股数据).\n"
            "Stock code format: A-shares=sh600000/sz000001, HK=hk00700, US=usAAPL\n"
            "Use westock_quote for real-time quotes with PE/PB.\n"
            "Use westock_kline for K-line/candlestick data.\n"
            "Use westock_finance for financial statements.\n"
            "Use westock_news for stock-specific news.\n"
            "Use westock_technical for technical indicators (MA/MACD/KDJ/RSI/BOLL).\n"
            "Use westock_search to find stock codes.\n"
        )

        @tool
        def westock_search(keyword: str) -> str:
            """Search for stocks/ETFs/indices by name or keyword. Returns stock codes."""
            return _run_westock(["search", keyword])

        @tool
        def westock_quote(codes: str) -> str:
            """Get real-time quote with PE/PB/PS/volume for one or more stocks.
            codes: comma-separated stock codes like 'sh600000,hk00700,usAAPL'"""
            return _run_westock(["quote", codes])

        @tool
        def westock_kline(code: str, period: str = "day", count: int = 20, adjust: str = "") -> str:
            """Get K-line data. period: day/week/month. adjust: qfq(前复权)/hfq(后复权)/empty.
            Example: westock_kline('hk00700', 'day', 60, 'qfq')"""
            args = ["kline", code, period, str(count)]
            if adjust:
                args.append(adjust)
            return _run_westock(args)

        @tool
        def westock_finance(code: str, periods: int = 4) -> str:
            """Get financial statements (income/balance/cashflow) for recent N periods.
            Example: westock_finance('hk00700', 4)"""
            return _run_westock(["finance", code, str(periods)], timeout=45)

        @tool
        def westock_news(code: str) -> str:
            """Get recent news and announcements for a stock.
            Example: westock_news('hk00700')"""
            return _run_westock(["news", code])

        @tool
        def westock_technical(code: str, indicators: str = "all") -> str:
            """Get technical indicators: ma/macd/kdj/rsi/boll/bias/wr/dmi/all.
            Example: westock_technical('sh600000', 'macd,rsi')"""
            return _run_westock(["technical", code, indicators])

        @tool
        def westock_fund_flow(code: str) -> str:
            """Get fund flow data (main/retail net flow, short ratio).
            Auto-detects market: A-share→asfund, HK→hkfund, US→usfund."""
            code_upper = code.upper()
            if code_upper.startswith("HK"):
                return _run_westock(["hkfund", code])
            elif code_upper.startswith("US"):
                return _run_westock(["usfund", code])
            else:
                return _run_westock(["asfund", code])

        @tool
        def westock_rating(code: str) -> str:
            """Get analyst ratings and consensus target prices.
            Example: westock_rating('sh600519')"""
            return _run_westock(["rating", code])

        return {
            "prompt": prompt,
            "tools": [
                westock_search,
                westock_quote,
                westock_kline,
                westock_finance,
                westock_news,
                westock_technical,
                westock_fund_flow,
                westock_rating,
            ],
        }
