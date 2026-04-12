"""Skill adapter for finance-news: multi-source news aggregation."""

from __future__ import annotations

from langchain_core.tools import tool

from stocker.skills.base import SkillAdapter, SkillManifest


class FinanceNewsSkill(SkillAdapter):

    @property
    def name(self) -> str:
        return "finance-news"

    @property
    def description(self) -> str:
        return "Multi-source financial news aggregation, sentiment analysis, and market briefings"

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name=self.name,
            description=self.description,
            sub_capabilities=["news_fetch", "rss_aggregate", "summarize", "alerts", "earnings"],
            version="1.0.1",
        )

    def load(self) -> dict:
        prompt = (
            "You now have access to the finance-news skill.\n"
            "- fetch_ticker_news: Get recent news for a specific stock\n"
            "- fetch_market_news: Get global market and economic news\n"
            "- search_stock_news: Search web for stock-related news via DuckDuckGo\n"
        )

        @tool
        def fetch_ticker_news(ticker: str) -> str:
            """Fetch recent news for a specific stock ticker from Yahoo Finance RSS."""
            from stocker.dataflows.yfinance_news import get_news
            from stocker.utils.helpers import today_str
            from datetime import datetime, timedelta
            start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            return get_news(ticker, start, today_str())

        @tool
        def fetch_market_news() -> str:
            """Fetch global market and economic news from multiple sources."""
            from stocker.dataflows.yfinance_news import get_global_news
            from stocker.utils.helpers import today_str
            return get_global_news(today_str())

        @tool
        def search_stock_news(query: str, max_results: int = 8) -> str:
            """Search web for stock-related news via DuckDuckGo. Use for tickers or topics not covered by RSS feeds."""
            try:
                from ddgs import DDGS
            except ImportError:
                try:
                    from duckduckgo_search import DDGS
                except ImportError:
                    return "DuckDuckGo search unavailable (install: pip install ddgs)"

            try:
                ddgs = DDGS(timeout=10)
                results = list(ddgs.news(
                    f"{query} stock market",
                    region="wt-wt",
                    safesearch="moderate",
                    max_results=max_results,
                ))
                if not results:
                    return f"No news found for: {query}"

                lines = [f"## Web News Search: {query}\n"]
                for i, r in enumerate(results, 1):
                    title = r.get("title", "")
                    body = r.get("body", "")[:150]
                    source = r.get("source", "")
                    url = r.get("url", "")
                    lines.append(f"{i}. **{title}** ({source})")
                    if body:
                        lines.append(f"   {body}")
                    if url:
                        lines.append(f"   {url}")
                    lines.append("")
                return "\n".join(lines)
            except Exception as e:
                return f"Search error: {e}"

        return {"prompt": prompt, "tools": [fetch_ticker_news, fetch_market_news, search_stock_news]}
