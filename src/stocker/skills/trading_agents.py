"""Legacy skill adapter for TradingAgents multi-vendor data fetching.

TradingAgents is no longer part of Stocker's main market/news data route. The
fixed route is DataFetcher → westock-data for market data and finance-news RSS
for news. Keep this adapter only as a manually discoverable legacy skill.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from langchain_core.tools import tool

from stocker.skills.base import SkillAdapter, SkillManifest

logger = logging.getLogger(__name__)

# Add TradingAgents to sys.path so we can import its modules
_TA_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "TradingAgents"


def _ensure_ta_importable():
    """Ensure TradingAgents package is importable."""
    ta_str = str(_TA_ROOT)
    if ta_str not in sys.path:
        sys.path.insert(0, ta_str)


def _safe_route(method: str, *args, **kwargs) -> str:
    """Safely call TradingAgents' route_to_vendor with error handling."""
    try:
        _ensure_ta_importable()
        from tradingagents.dataflows.interface import route_to_vendor
        result = route_to_vendor(method, *args, **kwargs)
        if result is None:
            return f"No data returned for {method}"
        return str(result)
    except Exception as e:
        return f"TradingAgents {method} error: {e}"


class TradingAgentsSkill(SkillAdapter):

    @property
    def name(self) -> str:
        return "trading-agents"

    @property
    def description(self) -> str:
        return (
            "Legacy TradingAgents multi-vendor data tools. Not used by Stocker's fixed "
            "DataFetcher route; keep only for manual diagnostics or migration work."
        )

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name=self.name,
            description=self.description,
            sub_capabilities=[
                "stock_data", "indicators", "fundamentals",
                "balance_sheet", "cashflow", "income_statement",
                "news", "global_news", "insider_transactions",
            ],
            version="1.0.0",
        )

    def load(self) -> dict:
        prompt = (
            "You have access to legacy TradingAgents data tools.\n"
            "- ta_stock_data: OHLCV price data for a date range\n"
            "- ta_indicators: Technical indicators (rsi/macd/boll/atr/sma/ema etc.)\n"
            "- ta_fundamentals: Company overview (PE/PB/MarketCap/Revenue etc.)\n"
            "- ta_financials: Balance sheet, cashflow, income statement\n"
            "- ta_news: Ticker-specific and global news\n"
            "- ta_insider: Insider transactions\n"
            "These tools are not part of Stocker's fixed main data route.\n"
        )

        @tool
        def ta_stock_data(symbol: str, start_date: str, end_date: str) -> str:
            """Get OHLCV stock price data via legacy TradingAgents.
            symbol: ticker like AAPL, NVDA, TSM
            start_date/end_date: yyyy-mm-dd format"""
            return _safe_route("get_stock_data", symbol, start_date, end_date)

        @tool
        def ta_indicators(symbol: str, indicator: str, curr_date: str, look_back_days: int = 30) -> str:
            """Get technical indicator values over a time window.
            indicator: one of rsi, macd, macds, macdh, close_50_sma, close_200_sma, close_10_ema,
                       boll, boll_ub, boll_lb, atr, vwma, mfi
            curr_date: yyyy-mm-dd"""
            return _safe_route("get_indicators", symbol, indicator, curr_date, look_back_days)

        @tool
        def ta_fundamentals(ticker: str, curr_date: str = "") -> str:
            """Get company fundamentals overview (PE, PB, MarketCap, Revenue, etc.).
            ticker: e.g. AAPL, NVDA"""
            return _safe_route("get_fundamentals", ticker, curr_date or None)

        @tool
        def ta_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = "") -> str:
            """Get balance sheet data. freq: annual/quarterly"""
            return _safe_route("get_balance_sheet", ticker, freq, curr_date or None)

        @tool
        def ta_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = "") -> str:
            """Get cash flow statement data. freq: annual/quarterly"""
            return _safe_route("get_cashflow", ticker, freq, curr_date or None)

        @tool
        def ta_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = "") -> str:
            """Get income statement data. freq: annual/quarterly"""
            return _safe_route("get_income_statement", ticker, freq, curr_date or None)

        @tool
        def ta_news(ticker: str, start_date: str, end_date: str) -> str:
            """Get news and sentiment for a stock ticker.
            start_date/end_date: yyyy-mm-dd"""
            return _safe_route("get_news", ticker, start_date, end_date)

        @tool
        def ta_global_news(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
            """Get global market/macro economic news.
            curr_date: yyyy-mm-dd"""
            return _safe_route("get_global_news", curr_date, look_back_days, limit)

        @tool
        def ta_insider_transactions(ticker: str) -> str:
            """Get insider transaction data (buys/sells by executives, directors, etc.)."""
            return _safe_route("get_insider_transactions", ticker)

        return {
            "prompt": prompt,
            "tools": [
                ta_stock_data,
                ta_indicators,
                ta_fundamentals,
                ta_balance_sheet,
                ta_cashflow,
                ta_income_statement,
                ta_news,
                ta_global_news,
                ta_insider_transactions,
            ],
        }
