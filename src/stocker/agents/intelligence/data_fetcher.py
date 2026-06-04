"""DataFetcher: single-source data acquisition node for Intelligence.

This node runs once before all analyst agents and is the only data entrance for
stock analysis. The source policy is intentionally simple:
- K-line, quote, technicals, fundamentals, fund flow, rating: westock-data only.
- News and global headlines: finance-news RSS only.

No automatic fallback is performed. If the fixed source fails or returns empty,
the failure is recorded in `data_warnings` and exposed to downstream reports.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to finance-news skill scripts
_FN_SKILL_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "skills" / "finance-news-1.0.1"
_FN_SCRIPTS = _FN_SKILL_DIR / "scripts"


def _convert_to_westock_code(ticker: str) -> str:
    """Convert standard ticker to westock code: AAPL->usAAPL, 0700.HK->hk00700.

    Also handles inputs that are already in westock format (SZ300750 -> sz300750).
    """
    t = ticker.strip()
    tu = t.upper()

    # Already in westock format (sh/sz/bj/hk/us prefix + code)
    for prefix in ("SH", "SZ", "BJ", "HK", "US"):
        if tu.startswith(prefix) and len(tu) > 2:
            # Keep prefix lowercase, preserve original case for US tickers
            if prefix == "US":
                return f"us{tu[2:]}"
            return f"{prefix.lower()}{tu[2:]}"

    if tu.endswith(".HK"):
        return f"hk{tu.replace('.HK', '').zfill(5)}"
    elif tu.endswith(".SS") or tu.endswith(".SH"):
        return f"sh{tu.split('.')[0]}"
    elif tu.endswith(".SZ"):
        return f"sz{tu.split('.')[0]}"
    elif tu.isalpha():
        return f"us{tu}"
    elif tu.isdigit():
        return f"sh{tu}" if tu.startswith("6") or tu.startswith("9") else f"sz{tu}"
    return t.lower()


def _try_call(func, *args, label="", warnings: list[str] | None = None, **kwargs) -> str:
    """Safely call the fixed data source, returning text or recording failure."""
    try:
        result = func(*args, **kwargs)
        text = str(result).strip() if result is not None else ""
        if text and "error" not in text.lower()[:120] and "timeout" not in text.lower()[:120]:
            logger.info("[DataFetcher] %s: got %d chars", label, len(text))
            return text
        reason = text[:200] if text else "empty response"
        logger.warning("[DataFetcher] %s unavailable: %s", label, reason)
        if warnings is not None:
            warnings.append(f"{label}: {reason}")
    except Exception as e:
        logger.warning("[DataFetcher] %s failed: %s", label, e)
        if warnings is not None:
            warnings.append(f"{label}: {e}")
    return ""


def _fetch_finance_news_rss(
    ticker: str,
    ticker_limit: int = 10,
    global_limit: int = 8,
    rss_timeout: int = 10,
    subprocess_timeout: int = 15,
) -> tuple[str, str]:
    """Fetch ticker news + global headlines via finance-news skill RSS feeds.

    Returns (ticker_news, global_news) as formatted strings, or empty.
    Uses pure HTTP RSS (WSJ/Bloomberg/FT/Reuters/CNBC/Yahoo) — zero yfinance risk.
    """
    ticker_news = ""
    global_news = ""

    fn_scripts_str = str(_FN_SCRIPTS)
    if fn_scripts_str not in sys.path:
        sys.path.insert(0, fn_scripts_str)

    try:
        from fetch_news import fetch_ticker_news, get_market_news

        # 1. Ticker-specific news via RSS (pure HTTP)
        # Strip exchange suffix for Yahoo RSS compatibility.
        if ticker and ticker_limit > 0:
            clean_ticker = ticker.upper().split(".")[0]
            articles = fetch_ticker_news(clean_ticker, limit=ticker_limit)
            if articles:
                lines = [f"## {ticker} News (RSS)\n"]
                for a in articles:
                    lines.append(f"- **{a.get('title', '')}**")
                    if a.get("description"):
                        lines.append(f"  {a['description'][:150]}")
                    if a.get("link"):
                        lines.append(f"  {a['link']}")
                    lines.append("")
                ticker_news = "\n".join(lines)
                logger.info("[DataFetcher] fn_rss.ticker_news: %d articles for %s", len(articles), ticker)

        # 2. Global headlines from premium RSS sources
        market = get_market_news(
            limit=global_limit, deadline=None,
            rss_timeout=rss_timeout, subprocess_timeout=subprocess_timeout,
        )
        if market and market.get("headlines"):
            lines = ["## Global Market Headlines\n"]
            for h in market["headlines"][:15]:
                src = h.get("source", h.get("source_id", ""))
                lines.append(f"- [{src}] **{h.get('title', '')}**")
                if h.get("description"):
                    lines.append(f"  {h['description'][:120]}")
                lines.append("")
            global_news = "\n".join(lines)
            logger.info("[DataFetcher] fn_rss.global_news: %d headlines", len(market["headlines"]))

    except Exception as e:
        logger.debug("[DataFetcher] finance-news RSS failed: %s", e)

    return ticker_news, global_news


def create_data_fetcher_node():
    """Create the DataFetcher node that populates shared_data in state."""

    def data_fetcher_node(state: dict) -> dict:
        ticker = state.get("ticker", "").strip()
        trade_date = state.get("trade_date", "")

        if not trade_date:
            trade_date = datetime.now().strftime("%Y-%m-%d")

        # Load data config from strategy
        try:
            from stocker.strategy import get_strategy
            dcfg = get_strategy().data
            lookback_days = dcfg.lookback_days
            kline_count = dcfg.kline_count
            news_ticker_limit = dcfg.news_ticker_limit
            news_global_limit = dcfg.news_global_limit
            rss_timeout = dcfg.rss_timeout
            subprocess_timeout = dcfg.subprocess_timeout
        except Exception:
            lookback_days = 30
            kline_count = 120
            news_ticker_limit = 10
            news_global_limit = 8
            rss_timeout = 10
            subprocess_timeout = 15

        end_dt = datetime.strptime(trade_date, "%Y-%m-%d")
        start_date = (end_dt - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        ws_code = _convert_to_westock_code(ticker)

        logger.info("[DataFetcher] Fetching all data for %s (ws=%s) date=%s",
                     ticker, ws_code, trade_date)

        shared = {
            "ticker": ticker,
            "ws_code": ws_code,
            "trade_date": trade_date,
            "start_date": start_date,
            "quote": "",
            "kline": "",
            "technical": "",
            "news": "",
            "global_news": "",
            "fundamentals": "",
            "finance": "",
            "fund_flow": "",
            "rating": "",
            "insider": "",
            "sources_used": [],
            "data_warnings": [],
            "source_policy": {
                "market_data": "westock-data",
                "news": "finance-news-rss",
                "fallback": "disabled",
            },
        }
        warnings = shared["data_warnings"]

        # =============================================================
        # NEWS: finance-news RSS only
        # =============================================================
        fn_ticker_news, fn_global_news = _fetch_finance_news_rss(
            ticker,
            ticker_limit=news_ticker_limit,
            global_limit=news_global_limit,
            rss_timeout=rss_timeout,
            subprocess_timeout=subprocess_timeout,
        )
        if fn_ticker_news:
            shared["news"] = fn_ticker_news
            shared["sources_used"].append("finance-news-rss:ticker")
        else:
            warnings.append("finance-news-rss:ticker: empty response")
        if fn_global_news:
            shared["global_news"] = fn_global_news
            shared["sources_used"].append("finance-news-rss:global")
        else:
            warnings.append("finance-news-rss:global: empty response")

        # =============================================================
        # MARKET DATA: westock-data only
        # =============================================================
        try:
            from stocker.skills.westock_data import _run_westock
        except ImportError as e:
            logger.warning("[DataFetcher] westock-data unavailable: %s", e)
            warnings.append(f"westock-data: import failed: {e}")
        else:
            q = _try_call(_run_westock, ["quote", ws_code], label="westock:quote", warnings=warnings, timeout=15)
            if q:
                shared["quote"] = q
                shared["sources_used"].append("westock:quote")

            k = _try_call(
                _run_westock,
                ["kline", ws_code, "day", str(kline_count), "qfq"],
                label="westock:kline",
                warnings=warnings,
                timeout=30,
            )
            if k:
                shared["kline"] = k
                shared["sources_used"].append("westock:kline")

            t = _try_call(_run_westock, ["technical", ws_code, "all"], label="westock:technical", warnings=warnings, timeout=20)
            if t:
                shared["technical"] = t
                shared["sources_used"].append("westock:technical")

            f = _try_call(_run_westock, ["finance", ws_code, "4"], label="westock:finance", warnings=warnings, timeout=45)
            if f:
                shared["finance"] = f
                shared["fundamentals"] = f
                shared["sources_used"].append("westock:finance")

            ff_cmd = "hkfund" if ws_code.startswith("hk") else "usfund" if ws_code.startswith("us") else "asfund"
            ff = _try_call(_run_westock, [ff_cmd, ws_code], label="westock:fund_flow", warnings=warnings, timeout=20)
            if ff:
                shared["fund_flow"] = ff
                shared["sources_used"].append("westock:fund_flow")

            r = _try_call(_run_westock, ["rating", ws_code], label="westock:rating", warnings=warnings, timeout=20)
            if r:
                shared["rating"] = r
                shared["sources_used"].append("westock:rating")

        for key, source in {
            "quote": "westock:quote",
            "kline": "westock:kline",
            "technical": "westock:technical",
            "news": "finance-news-rss:ticker",
            "finance": "westock:finance",
        }.items():
            if not shared.get(key):
                warnings.append(f"{source}: unavailable; fallback disabled")


        # =============================================================
        # Summary
        # =============================================================
        filled = sum(1 for k in ["quote", "kline", "technical", "news",
                                  "fundamentals", "finance", "fund_flow"]
                     if shared.get(k))
        logger.info("[DataFetcher] Done for %s: %d/7 data slots filled, sources=%s",
                     ticker, filled, shared["sources_used"])

        return {"shared_data": shared}

    return data_fetcher_node
