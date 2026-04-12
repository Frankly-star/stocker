"""yfinance news provider. Extracted from TradingAgents yfinance_news.py."""

from __future__ import annotations

import logging
from datetime import datetime

import yfinance as yf
from dateutil.relativedelta import relativedelta

from stocker.dataflows.yfinance_provider import _yf_retry

logger = logging.getLogger(__name__)


def _extract_article(article: dict) -> dict:
    """Extract article data handling nested 'content' structure."""
    if "content" in article:
        c = article["content"]
        url_obj = c.get("canonicalUrl") or c.get("clickThroughUrl") or {}
        pub_str = c.get("pubDate", "")
        pub_date = None
        if pub_str:
            try:
                pub_date = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        return {
            "title": c.get("title", "No title"),
            "summary": c.get("summary", ""),
            "publisher": c.get("provider", {}).get("displayName", "Unknown"),
            "link": url_obj.get("url", ""),
            "pub_date": pub_date,
        }
    return {
        "title": article.get("title", "No title"),
        "summary": article.get("summary", ""),
        "publisher": article.get("publisher", "Unknown"),
        "link": article.get("link", ""),
        "pub_date": None,
    }


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """Get news for a ticker within a date range."""
    try:
        stock = yf.Ticker(ticker)
        news = _yf_retry(lambda: stock.get_news(count=20))
        if not news:
            return f"No news found for {ticker}"

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        parts = []
        for article in news:
            data = _extract_article(article)
            if data["pub_date"]:
                naive = data["pub_date"].replace(tzinfo=None)
                if not (start_dt <= naive <= end_dt + relativedelta(days=1)):
                    continue
            parts.append(f"### {data['title']} ({data['publisher']})")
            if data["summary"]:
                parts.append(data["summary"])
            parts.append("")

        if not parts:
            return f"No news for {ticker} between {start_date} and {end_date}"
        return f"## {ticker} News ({start_date} to {end_date}):\n\n" + "\n".join(parts)
    except Exception as e:
        return f"Error fetching news for {ticker}: {e}"


def get_global_news(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    """Get global market news via yfinance Search."""
    queries = [
        "stock market economy",
        "Federal Reserve interest rates",
        "inflation economic outlook",
    ]
    all_news = []
    seen = set()

    try:
        for q in queries:
            search = _yf_retry(lambda query=q: yf.Search(query=query, news_count=limit, enable_fuzzy_query=True))
            if search.news:
                for article in search.news:
                    data = _extract_article(article)
                    if data["title"] not in seen:
                        seen.add(data["title"])
                        all_news.append(data)
            if len(all_news) >= limit:
                break

        if not all_news:
            return f"No global news found for {curr_date}"

        start_date = (datetime.strptime(curr_date, "%Y-%m-%d") - relativedelta(days=look_back_days)).strftime("%Y-%m-%d")
        parts = []
        for data in all_news[:limit]:
            parts.append(f"### {data['title']} ({data['publisher']})")
            if data["summary"]:
                parts.append(data["summary"])
            parts.append("")

        return f"## Global News ({start_date} to {curr_date}):\n\n" + "\n".join(parts)
    except Exception as e:
        return f"Error fetching global news: {e}"
