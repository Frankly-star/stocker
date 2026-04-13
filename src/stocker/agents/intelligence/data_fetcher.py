"""DataFetcher: centralized data acquisition node for the Intelligence subgraph.

This node runs ONCE before all analyst agents. It fetches all required data
from multiple sources with automatic fallback, then stores everything in
`shared_data` so analysts only read from state — no duplicate API calls.

News source priority:
  1. finance-news skill RSS (WSJ/Bloomberg/FT/Reuters/CNBC — pure HTTP, zero rate limits)
  2. westock-data news (Tencent — no rate limits)
  3. DDG search (fallback)
  4. yfinance / TradingAgents (last resort)

Price/technical source priority:
  1. westock-data (quote, kline, technical, finance, fund_flow, rating)
  2. yfinance (kline, fundamentals)
  3. TradingAgents (yfinance + Alpha Vantage auto-fallback)
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


def _try_call(func, *args, label="", **kwargs) -> str:
    """Safely call a data function, return result string or empty on failure."""
    try:
        result = func(*args, **kwargs)
        if result and "error" not in str(result).lower()[:80]:
            logger.info("[DataFetcher] %s: got %d chars", label, len(str(result)))
            return str(result)
    except Exception as e:
        logger.debug("[DataFetcher] %s failed: %s", label, e)
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

        # 1. Ticker-specific news via Yahoo RSS (pure HTTP)
        # Strip exchange suffix for Yahoo RSS compatibility
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
        }

        # =============================================================
        # FUTU QUOTE (highest priority for HK/US when runtime is available)
        # =============================================================
        futu_used = False
        try:
            from stocker.engine.runtime import get_active_runtime
            from stocker.integrations.futu.mappers import convert_ticker_to_futu

            futu_rt = get_active_runtime()
            if futu_rt is not None and futu_rt.started:
                futu_code = convert_ticker_to_futu(ticker, futu_rt.config.market)

                # Quote / snapshot
                snap = futu_rt.get_cached_quote(futu_code)
                if not snap:
                    snap = futu_rt.get_snapshot(futu_code)
                if snap:
                    lines = [f"{k}: {v}" for k, v in snap.items() if v is not None]
                    shared["quote"] = "\n".join(lines)
                    shared["sources_used"].append("futu:quote")
                    futu_used = True

                # K-line (daily)
                kbars = futu_rt.get_kline(futu_code, "K_DAY", kline_count)
                if kbars:
                    import csv, io
                    buf = io.StringIO()
                    if kbars:
                        writer = csv.DictWriter(buf, fieldnames=kbars[0].keys())
                        writer.writeheader()
                        writer.writerows(kbars)
                    shared["kline"] = buf.getvalue()
                    shared["sources_used"].append("futu:kline")
                    futu_used = True

                if futu_used:
                    logger.info("[DataFetcher] Futu data acquired for %s (%s)", ticker, futu_code)
        except Exception as e:
            logger.debug("[DataFetcher] Futu data source unavailable: %s", e)

        # =============================================================
        # NEWS FIRST: finance-news RSS (pure HTTP, zero rate limit risk)
        # Sources: WSJ, Bloomberg, FT, Reuters, CNBC, Yahoo, MarketWatch
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
        if fn_global_news:
            shared["global_news"] = fn_global_news
            shared["sources_used"].append("finance-news-rss:global")

        # =============================================================
        # PRICE/TECHNICAL/FUNDAMENTALS: westock-data (no rate limits)
        # =============================================================
        ws_available = False
        try:
            from stocker.skills.westock_data import _run_westock
            ws_available = True
        except ImportError:
            logger.debug("[DataFetcher] westock-data not available")

        if ws_available:
            q = _try_call(_run_westock, ["quote", ws_code], label="ws.quote", timeout=15)
            if q:
                shared["quote"] = q
                shared["sources_used"].append("westock:quote")

            k = _try_call(_run_westock, ["kline", ws_code, "day", str(kline_count), "qfq"],
                          label="ws.kline", timeout=30)
            if k:
                shared["kline"] = k
                shared["sources_used"].append("westock:kline")

            t = _try_call(_run_westock, ["technical", ws_code, "all"],
                          label="ws.technical", timeout=20)
            if t:
                shared["technical"] = t
                shared["sources_used"].append("westock:technical")

            # Supplement news from westock if RSS didn't get ticker news
            if not shared["news"]:
                n = _try_call(_run_westock, ["news", ws_code], label="ws.news", timeout=20)
                if n:
                    shared["news"] = n
                    shared["sources_used"].append("westock:news")

            f = _try_call(_run_westock, ["finance", ws_code, "4"],
                          label="ws.finance", timeout=45)
            if f:
                shared["finance"] = f
                shared["fundamentals"] = f
                shared["sources_used"].append("westock:finance")

            ff = _try_call(_run_westock,
                           ["hkfund" if ws_code.startswith("hk") else
                            "usfund" if ws_code.startswith("us") else "asfund",
                            ws_code],
                           label="ws.fund_flow", timeout=20)
            if ff:
                shared["fund_flow"] = ff
                shared["sources_used"].append("westock:fund_flow")

            r = _try_call(_run_westock, ["rating", ws_code], label="ws.rating", timeout=20)
            if r:
                shared["rating"] = r
                shared["sources_used"].append("westock:rating")

        # =============================================================
        # Early exit if core data is complete — skip all slow fallbacks
        # =============================================================
        has_price = bool(shared["quote"] or shared["kline"])
        has_news = bool(shared["news"])
        has_fundamentals = bool(shared["fundamentals"] or shared["finance"])

        if has_price and has_news and has_fundamentals:
            logger.info("[DataFetcher] Core data complete, skipping fallback layers")
        else:
            # ----- DDG search for news -----
            if not shared["news"]:
                try:
                    from stocker.skills.finance_news import FinanceNewsSkill
                    skill = FinanceNewsSkill()
                    loaded = skill.load()
                    tools_map = {tool.name: tool for tool in loaded["tools"]}
                    if "search_stock_news" in tools_map:
                        n2 = _try_call(tools_map["search_stock_news"].invoke,
                                       {"query": f"{ticker} stock"}, label="ddg.news")
                        if n2:
                            shared["news"] = n2
                            shared["sources_used"].append("ddg:news")
                except Exception as e:
                    logger.debug("[DataFetcher] DDG news fallback: %s", e)

            # ----- yfinance (fill remaining gaps ONLY) -----
            if not shared["kline"]:
                try:
                    from stocker.agents.intelligence.market_data_agent import _fetch_yfinance_ohlcv
                    df, src = _fetch_yfinance_ohlcv(ticker)
                    if df is not None and not df.empty and len(df) >= 50:
                        shared["kline"] = df.tail(kline_count).to_csv(index=False)
                        shared["sources_used"].append(f"yfinance:kline({src})")
                except Exception as e:
                    logger.debug("[DataFetcher] yfinance kline: %s", e)

            if not shared["fundamentals"] and not shared["finance"]:
                try:
                    import yfinance as yf
                    from stocker.dataflows.yfinance_provider import _yf_retry
                    obj = yf.Ticker(ticker.upper())
                    info = _yf_retry(lambda: obj.info)
                    if info:
                        lines = [f"{k}: {v}" for k, v in info.items()
                                 if v is not None and k not in ("companyOfficers",)]
                        shared["fundamentals"] = "\n".join(lines[:40])
                        shared["sources_used"].append("yfinance:fundamentals")
                except Exception as e:
                    logger.debug("[DataFetcher] yfinance fundamentals: %s", e)

            # ----- TradingAgents (last resort) -----
            if not shared["quote"] and not shared["kline"]:
                try:
                    from stocker.skills.trading_agents import _safe_route
                    sd = _safe_route("get_stock_data", ticker, start_date, trade_date)
                    if sd and "error" not in sd.lower()[:80]:
                        shared["kline"] = sd
                        shared["sources_used"].append("ta:stock_data")
                except Exception as e:
                    logger.debug("[DataFetcher] TA stock_data: %s", e)

            if not shared["fundamentals"] and not shared["finance"]:
                try:
                    from stocker.skills.trading_agents import _safe_route
                    fd = _safe_route("get_fundamentals", ticker, trade_date)
                    if fd and "error" not in fd.lower()[:80]:
                        shared["fundamentals"] = fd
                        shared["sources_used"].append("ta:fundamentals")
                except Exception as e:
                    logger.debug("[DataFetcher] TA fundamentals: %s", e)

            if not shared["news"]:
                try:
                    from stocker.skills.trading_agents import _safe_route
                    nd = _safe_route("get_news", ticker, start_date, trade_date)
                    if nd and "error" not in nd.lower()[:80]:
                        shared["news"] = nd
                        shared["sources_used"].append("ta:news")
                except Exception as e:
                    logger.debug("[DataFetcher] TA news: %s", e)

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
