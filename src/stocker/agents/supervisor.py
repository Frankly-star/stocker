"""Supervisor Agent: LLM-driven global coordinator.

The Supervisor is the system's "brain" — it understands user intent from
conversation context and autonomously decides which tools to call.

Execution mode (ACTIVE / OBSERVE) only controls whether trades are actually
sent to the broker.  Everything else (analyze, assess, status, portfolio) is
decided by the Supervisor LLM at runtime — no manual mode selection needed.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from stocker.analysis.models import ExecutionMode, MarketIntelligenceReport, RiskAssessmentResult
from stocker.utils.helpers import atomic_json_write, json_read, today_str

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Analysis Cache
# ---------------------------------------------------------------------------

class AnalysisCache:
    """Caches analysis results by ticker + timestamp."""

    def __init__(self, cache_dir: str = "data/analysis_cache") -> None:
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, ticker: str, report: MarketIntelligenceReport) -> None:
        filepath = self._dir / f"{ticker.upper()}_latest.json"
        atomic_json_write(filepath, report.model_dump(mode="json"))

    def get(self, ticker: str) -> MarketIntelligenceReport | None:
        filepath = self._dir / f"{ticker.upper()}_latest.json"
        data = json_read(filepath)
        if data:
            try:
                return MarketIntelligenceReport(**data)
            except Exception:
                return None
        return None

    def get_text(self, ticker: str) -> str:
        report = self.get(ticker)
        if report:
            return report.to_situation_text()
        return f"No cached analysis for {ticker}"


# ---------------------------------------------------------------------------
# Supervisor system prompt
# ---------------------------------------------------------------------------

SUPERVISOR_SYSTEM_PROMPT = """You are the Stocker Supervisor, the central coordinator of an automated range/swing trading system. You speak Chinese (简体中文) by default unless the user uses another language.

## Execution Mode
The system has two execution modes — you MUST respect the current mode:
- **ACTIVE**: You may execute trades via `run_execution`. Full autonomy.
- **OBSERVE** (default): You may analyze, assess, and recommend, but you must NEVER call `run_execution`. If the user asks to trade while in OBSERVE mode, explain that the system is in observe-only mode and suggest switching to ACTIVE mode first.

## Available Tools

1. **run_intelligence(ticker)** — Run the Data Intelligence Team. Returns analysis report covering technicals, news, fundamentals, and sentiment.
2. **run_risk_assessment(ticker, use_cached)** — Run the Risk Assessment Team. Returns risk rating and recommendation.
3. **run_execution(ticker, action, quantity, price)** — Execute a trade. Only in ACTIVE mode.
4. **get_system_status()** — Get system status.
5. **manage_portfolio(action, ticker, quantity, avg_cost)** — Manage positions.
6. **get_cached_analysis(ticker)** — Get cached analysis.
7. **manage_watchlist(action, ticker, name, market, tags)** — Manage the watchlist/stock pool: list/add/remove/count. Add stocks you want to monitor.
8. **scan_watchlist_signals(min_strength)** — Scan all watchlist stocks for swing trading signals. Returns entry/exit signals with strength scores.
9. **get_realtime_quote(ticker)** — Get real-time stock quote (price, change%, PE, volume) via WeStock API. Lightweight, no full pipeline needed.
10. **discover_market_opportunities(market)** — Fetch real-time market data: hot stocks, hot sectors, fund flows, market news. Use this to discover candidates before deep analysis.

## Decision Logic
You decide what to do based on the conversation — no manual mode selection needed:
- User asks to "analyze" a stock → call run_intelligence AND run_risk_assessment, then provide a comprehensive investment recommendation
- User asks for a "recommendation" → run_intelligence + run_risk_assessment
- User asks to "buy" or "sell" → check mode, then run_execution if ACTIVE
- User asks about status / portfolio → use appropriate tools
- User asks about price / quote → use get_realtime_quote (fast) instead of run_intelligence (slow)
- User asks to watch / monitor a stock → use manage_watchlist to add it
- User asks to "scan" or "find opportunities" → use scan_watchlist_signals
- User asks to "discover" or "research market/sectors" → use discover_market_opportunities first, then run_intelligence on candidates
- For scheduled tasks (prefixed with "scheduled:") → run full pipeline

## Autonomous Investment Research Flow (for AutoPilot scheduled tasks)
When executing a scheduled autonomous research cycle:
1. **Market Discovery**: Call discover_market_opportunities to get real-time hot stocks, sector fund flows, and market news. This provides DATA-DRIVEN candidates, not guesswork.
2. **Candidate Selection**: From the market data, identify 3-5 stocks with strong momentum, fund inflows, or sector tailwinds.
3. **Full Pipeline Analysis**: For EACH candidate, run the complete analysis pipeline:
   - run_intelligence(ticker) → Data Intelligence Team fetches K-line, technicals, news, fundamentals, fund flows via westock-data + yfinance + RSS
   - run_risk_assessment(ticker) → Risk Assessment Team runs bull/bear debate + risk debate → produces BUY/HOLD/SELL rating
4. **Watchlist Management**: Stocks rated BUY or OVERWEIGHT → add to watchlist via manage_watchlist(action='add'). Stocks rated SELL → remove if already watching.
5. **Signal Scan**: Run scan_watchlist_signals on the full watchlist to find entry/exit signals.
6. **Trade Execution** (ACTIVE mode only): For watchlist stocks with entry signals (strength >= 60) AND BUY rating from risk team → run_execution to build position. For held stocks with exit signals → run_execution to close position.
7. **Report**: Summarize actions taken in this cycle.

This ensures ALL stock selection is driven by real market data and validated through the full analysis + risk assessment pipeline — never by LLM guesswork.

## Response Format for Analysis
Use clean Markdown formatting. Use `###` for main section titles (NOT h1/h2, and do NOT nest h4/h5 inside — use **bold** for sub-items). Separate major sections with `---`. Keep content compact — use short bullet points, avoid repeating the same info.

Structure your response EXACTLY like this:

```
### 📊 市场数据概览
(price, trend, support/resistance — keep it brief, 3-5 bullet points)

---

### 📈 技术面分析
(RSI, MACD, KDJ, Bollinger — brief summary with interpretation)

---

### 📰 基本面/新闻
(valuation, key news, growth drivers — brief)

---

### ⚠️ 风险评估
(risk rating, risk-reward ratio, key risk factors)

---

### 🎯 针对性投资策略
(THE MOST IMPORTANT SECTION — see rules below)
```

Rules for 针对性投资策略:
- Do NOT repeat position data the user already knows. Jump straight into strategy.
- If user HOLDS: analyze cost basis vs support/resistance, then give specific actions:
  **止盈**: price (相对成本价 +X.X%)
  **止损**: price (相对成本价 -X.X%)
  **加仓条件**: price and trigger
  **减仓条件**: price and trigger
  **仓位建议**: keep / add / reduce with reasoning
- If user does NOT hold: 是否建仓, 建仓价位, 建议仓位, 入场条件
- EVERY price level MUST show percentage relative to user's cost basis
- End with a one-sentence **总结** of the recommended action

Never end an analysis without a clear, actionable investment strategy.

## CRITICAL: Handling Tool Responses
- If a tool returns actual data/report → summarize and present it clearly to the user.
- If a tool returns partial data or notes about limited data → STILL provide a useful analysis based on whatever data IS available. Supplement with your own knowledge about the company, sector, and market conditions.
- If a tool returns a degradation message (e.g., "子图未构建") → DO NOT just echo the error. Acknowledge the limitation and use your own knowledge to provide the user with a helpful, substantive response.
- **NEVER tell the user "data is insufficient" and stop there.** Instead:
  1. Present whatever data you DO have
  2. Add your own analysis and context about the stock
  3. Explain what additional data sources could improve the analysis
  4. If it's a well-known stock, provide general market context from your knowledge
- ALWAYS give the user a complete, useful response. Never leave them hanging with just "triggered" or "processing" — they expect an answer NOW.

## Ticker Format
Preserve exact ticker format including exchange suffixes (e.g. 0700.HK, AAPL, TSM, 9988.HK). Hong Kong stocks use .HK suffix, London stocks use .L, etc.

## Style
- Use emoji to make responses more visual and scannable. For example: 📊 for data, 📈 for bullish/uptrend, 📉 for bearish/downtrend, ✅ for positive, ⚠️ for warnings/risks, 🎯 for targets, 💰 for profit, 🛡️ for stop-loss/protection, 🔍 for analysis, 💡 for suggestions.
- Use Markdown formatting (headers, bold, lists, tables) for structured output.
- Be conversational, helpful, and efficient."""


# ---------------------------------------------------------------------------
# Tool factory (creates tools bound to system services)
# ---------------------------------------------------------------------------

def create_supervisor_tools(
    intelligence_graph: Any = None,
    risk_graph: Any = None,
    execution_graph: Any = None,
    portfolio_store: Any = None,
    watchlist_store: Any = None,
    analysis_cache: AnalysisCache | None = None,
    service: Any = None,
) -> list:
    """Create the Supervisor tools bound to actual system components.

    If subgraphs are not provided, tools return descriptive messages so
    the Supervisor LLM can still reason about what *would* happen and
    give the user a meaningful response.
    """

    cache = analysis_cache or AnalysisCache()

    def _get_position_context(ticker: str) -> str:
        """Get the user's position info for a ticker, if any."""
        if not portfolio_store:
            return ""
        t = ticker.upper()
        pos = portfolio_store.get(t)
        if not pos or pos.quantity <= 0:
            return f"\n\n[持仓信息] 用户当前未持有 {t}。"
        pnl_pct = ((pos.current_price - pos.avg_cost) / pos.avg_cost * 100) if pos.avg_cost > 0 else 0
        return (
            f"\n\n[用户持仓数据 — 请勿直接复述，而是基于这些数据分析投资策略]\n"
            f"  股票: {pos.name or t}\n"
            f"  持仓: {pos.quantity} 股\n"
            f"  成本价: {pos.avg_cost:.2f}\n"
            f"  现价: {pos.current_price:.2f}\n"
            f"  浮动盈亏: {pos.unrealized_pnl:+.2f} ({pnl_pct:+.2f}%)\n"
            f"要求：所有止盈止损和加减仓价位必须标注相对于成本价 {pos.avg_cost:.2f} 的盈亏百分比。"
        )

    @tool
    def run_intelligence(ticker: str) -> str:
        """Run the Data Intelligence Team to analyze a stock. Returns market intelligence report and user's position info."""
        ticker = ticker.upper().strip()
        logger.info("run_intelligence called for %s", ticker)
        pos_ctx = _get_position_context(ticker)

        if intelligence_graph:
            try:
                from langchain_core.messages import HumanMessage
                result = intelligence_graph.invoke({
                    "ticker": ticker,
                    "trade_date": today_str(),
                    "messages": [HumanMessage(content=f"Analyze {ticker}")],
                })
                report = result.get("intelligence_report")
                if report:
                    cache.save(ticker, report)
                    return report.to_situation_text() + pos_ctx
                return f"Intelligence team completed for {ticker} but no structured report was generated." + pos_ctx
            except Exception as e:
                logger.error("Intelligence graph failed for %s: %s", ticker, e)
                return f"Intelligence analysis failed for {ticker}: {e}" + pos_ctx

        # No intelligence graph available — return helpful info so LLM can still assist
        cached = cache.get(ticker)
        if cached:
            return f"[使用缓存数据]\n{cached.to_situation_text()}" + pos_ctx

        return (
            f"数据分析团队尚未完全接入（Intelligence 子图未构建）。\n"
            f"无法为 {ticker} 运行实时数据分析。\n"
            f"你可以基于已有知识为用户提供一般性的分析思路和建议。"
        )

    @tool
    def run_risk_assessment(ticker: str, use_cached: bool = False) -> str:
        """Run the Risk Assessment Team (bull/bear debate + risk debate). Returns rating, recommendation, and user's position info."""
        ticker = ticker.upper().strip()
        logger.info("run_risk_assessment called for %s (cached=%s)", ticker, use_cached)
        pos_ctx = _get_position_context(ticker)

        if risk_graph:
            try:
                situation = cache.get_text(ticker)
                from langchain_core.messages import HumanMessage
                result = risk_graph.invoke({
                    "ticker": ticker,
                    "situation_text": situation,
                    "messages": [HumanMessage(content=f"Assess risk for {ticker}")],
                })
                assessment = result.get("risk_assessment")
                if assessment:
                    return (
                        f"Risk Assessment for {ticker}:\n"
                        f"  Rating: {assessment.rating}\n"
                        f"  Confidence: {assessment.confidence:.0%}\n"
                        f"  Action: {assessment.suggested_action}\n"
                        f"  Risk Level: {assessment.risk_level}\n"
                        f"  Thesis: {assessment.investment_thesis}"
                    ) + pos_ctx
                decision = result.get("final_trade_decision", "")
                if decision:
                    return f"Risk Assessment for {ticker}:\n{decision}" + pos_ctx
                return f"Risk assessment completed for {ticker} but no structured result was generated." + pos_ctx
            except Exception as e:
                logger.error("Risk graph failed for %s: %s", ticker, e)
                return f"Risk assessment failed for {ticker}: {e}" + pos_ctx

        return (
            f"风险评估团队尚未完全接入（Risk 子图未构建）。\n"
            f"无法为 {ticker} 运行牛熊辩论和风险评估。\n"
            f"你可以基于已有信息为用户提供初步的风险分析。"
        ) + pos_ctx

    @tool
    def run_execution(ticker: str, action: str, quantity: int, price: float = 0.0) -> str:
        """Execute a trade. action: 'buy' or 'sell'. Only works in ACTIVE mode."""
        ticker = ticker.upper().strip()
        logger.info("run_execution called: %s %s x%d @ %.2f", action, ticker, quantity, price)

        if execution_graph:
            try:
                from langchain_core.messages import HumanMessage
                result = execution_graph.invoke({
                    "ticker": ticker,
                    "order_params": {
                        "ticker": ticker,
                        "side": action.lower(),
                        "quantity": quantity,
                        "price": price,
                    },
                    "messages": [HumanMessage(content=f"{action} {ticker}")],
                })
                exec_result = result.get("execution_result", {})
                error = exec_result.get("error")
                if error:
                    return f"交易被拒绝: {error}"
                status = exec_result.get("status", "")
                order_id = exec_result.get("order_id", "")
                filled = exec_result.get("filled_price", 0)
                info = f"交易已提交: {action.upper()} {quantity} 股 {ticker}"
                if order_id:
                    info += f" (订单号: {order_id})"
                if filled:
                    info += f" 成交价: ${filled:.2f}"
                if status:
                    info += f" 状态: {status}"
                return info
            except Exception as e:
                logger.error("Execution graph failed: %s", e)
                return f"交易执行失败: {e}"

        return (
            f"交易执行团队尚未接入（Execution 子图未构建）。\n"
            f"无法执行 {action.upper()} {quantity} 股 {ticker}。\n"
            f"请在 Broker 配置完成后重试。"
        )

    @tool
    def get_system_status() -> str:
        """Get current system status: scheduler jobs, positions, execution mode."""
        from stocker.engine.runtime_state import get_execution_mode

        status = {
            "service": "running",
            "time": datetime.now().isoformat(),
            "execution_mode": get_execution_mode(),
            "intelligence_team": "ready" if intelligence_graph else "not_wired",
            "risk_team": "ready" if risk_graph else "not_wired",
            "execution_team": "ready" if execution_graph else "not_wired",
        }
        if portfolio_store:
            status["portfolio"] = portfolio_store.get_summary()
        if service:
            status.update(service.get_status())
        return json.dumps(status, indent=2, default=str)

    @tool
    def manage_portfolio(action: str, ticker: str = "", quantity: int = 0, avg_cost: float = 0.0) -> str:
        """Manage portfolio positions. action: list/add/remove/scan/sync."""
        if not portfolio_store:
            return "Portfolio store not initialized."
        if action == "list":
            positions = portfolio_store.list_all()
            if not positions:
                return "No positions in portfolio."
            lines = [f"  {p.ticker}: {p.quantity} shares @ ${p.avg_cost:.2f}" for p in positions]
            return "Current Portfolio:\n" + "\n".join(lines)
        elif action == "add":
            pos = portfolio_store.add(ticker, quantity, avg_cost)
            return f"Added: {pos.ticker} {pos.quantity} shares @ ${pos.avg_cost:.2f}"
        elif action == "remove":
            ok = portfolio_store.remove(ticker)
            return f"Removed {ticker}" if ok else f"{ticker} not found in portfolio"
        else:
            return f"Action '{action}' will be handled by portfolio subgraph."

    @tool
    def get_cached_analysis(ticker: str) -> str:
        """Get the most recent cached analysis for a ticker."""
        return cache.get_text(ticker)

    @tool
    def manage_watchlist(action: str, ticker: str = "", name: str = "", market: str = "", tags: str = "") -> str:
        """Manage the watchlist (stock pool). action: list/add/remove/count.
        For add: provide ticker (required), name, market (HK/US/CN), tags (comma-separated).
        Use this to add stocks you want to monitor for swing trading opportunities."""
        if not watchlist_store:
            return "Watchlist store not initialized."
        if action == "list":
            items = watchlist_store.list_all()
            if not items:
                return "Watchlist is empty."
            lines = []
            for wi in items:
                sig_info = ""
                if wi.latest_signal:
                    sig = wi.latest_signal
                    sig_type = sig.signal_type if hasattr(sig, 'signal_type') else (sig.get('signal_type', '') if isinstance(sig, dict) else '')
                    strength = sig.strength if hasattr(sig, 'strength') else (sig.get('strength', 0) if isinstance(sig, dict) else 0)
                    if sig_type:
                        sig_info = f" | 信号: {sig_type} ({strength:.0f})"
                lines.append(f"  {wi.ticker} ({wi.name or '-'}) [{wi.market or '?'}]{sig_info}")
            return f"Watchlist ({len(items)} stocks):\n" + "\n".join(lines)
        elif action == "add":
            if not ticker:
                return "Error: ticker is required for add."
            tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
            wi = watchlist_store.add(ticker=ticker.upper(), name=name, market=market, tags=tag_list)
            return f"Added to watchlist: {wi.ticker} ({wi.name})"
        elif action == "remove":
            ok = watchlist_store.remove(ticker)
            return f"Removed {ticker} from watchlist" if ok else f"{ticker} not found in watchlist"
        elif action == "count":
            return f"Watchlist has {watchlist_store.count()} stocks."
        return f"Unknown watchlist action: {action}"

    @tool
    def scan_watchlist_signals(min_strength: float = 30.0) -> str:
        """Scan all watchlist stocks for swing trading signals using technical analysis.
        Returns entry/exit signals with strength scores. Use this to find trading opportunities.
        min_strength: minimum signal strength (0-100) to include in results."""
        if not watchlist_store:
            return "Watchlist store not initialized."
        items = watchlist_store.list_all()
        if not items:
            return "Watchlist is empty. Add stocks first with manage_watchlist(action='add', ticker='...')."

        try:
            from stocker.analysis.swing_signals import SwingSignalEngine
            from stocker.utils.data_helpers import fetch_ohlcv_yfinance
            engine = SwingSignalEngine()
            results = []
            for wi in items[:30]:  # limit batch
                try:
                    df = fetch_ohlcv_yfinance(wi.ticker)
                    if df is None or df.empty:
                        continue
                    signal = engine.analyze(wi.ticker, df)
                    if signal.strength >= min_strength:
                        watchlist_store.update_signal(wi.ticker, signal.model_dump(mode="json"))
                        results.append(
                            f"  {wi.ticker}: {signal.signal_type.value} "
                            f"(strength={signal.strength:.0f}, price={signal.suggested_price:.2f}) "
                            f"- {'; '.join(signal.reasons[:2])}"
                        )
                except Exception as e:
                    logger.debug("Scan failed for %s: %s", wi.ticker, e)

            if not results:
                return f"Scanned {len(items)} stocks, no signals above strength {min_strength}."
            return f"Scan results ({len(results)} signals from {len(items)} stocks):\n" + "\n".join(results)
        except Exception as e:
            return f"Scan failed: {e}"

    @tool
    def get_realtime_quote(ticker: str) -> str:
        """Get real-time stock quote (price, change%, PE, volume) via WeStock data API.
        Use this for quick price checks without running the full intelligence pipeline.
        ticker: stock symbol (e.g. AAPL, 0700.HK, 600519.SS)."""
        try:
            from stocker.skills.westock_data import _run_westock

            t = ticker.upper().strip()
            # Convert to westock code
            if t.endswith(".HK"):
                code = f"hk{t.replace('.HK', '').zfill(5)}"
            elif t.endswith(".SS"):
                code = f"sh{t.replace('.SS', '')}"
            elif t.endswith(".SZ"):
                code = f"sz{t.replace('.SZ', '')}"
            elif t.isdigit():
                code = f"sh{t}" if t.startswith("6") else f"sz{t}"
            elif t.isalpha():
                code = f"us{t}"
            else:
                code = t

            raw = _run_westock(["quote", code], timeout=15)
            if raw and "error" not in raw.lower()[:100]:
                return f"Real-time quote for {ticker} (code={code}):\n{raw}"
            return f"Quote unavailable for {ticker}: {raw[:200] if raw else 'no data'}"
        except Exception as e:
            return f"Quote failed for {ticker}: {e}"

    @tool
    def discover_market_opportunities(market: str = "hs") -> str:
        """Discover current market opportunities by fetching real-time market data:
        hot stocks, hot sectors/boards, sector fund flows, and market overview.
        market: 'hs' (A-shares, default), 'hk' (Hong Kong), 'us' (US).
        Returns raw market data for you to analyze and pick promising candidates.
        After identifying candidates, run run_intelligence + run_risk_assessment on each."""
        try:
            from stocker.skills.westock_data import _run_westock
        except ImportError:
            return "westock-data not available. Cannot discover market opportunities."

        sections = []

        # 1. Hot stocks
        hot = _run_westock(["hot", "stock"], timeout=15)
        if hot and "error" not in hot.lower()[:80]:
            sections.append(f"## 热搜股票\n{hot[:2000]}")

        # 2. Hot sectors/boards
        board = _run_westock(["board"], timeout=15)
        if board and "error" not in board.lower()[:80]:
            sections.append(f"## 热门板块（行业资金流向+涨幅排名）\n{board[:3000]}")

        # 3. Market news
        mnews = _run_westock(["marketnews", market], timeout=15)
        if mnews and "error" not in mnews.lower()[:80]:
            sections.append(f"## 市场资讯\n{mnews[:2000]}")

        if not sections:
            return "Failed to fetch market data from all sources."

        return (
            f"Market opportunities scan ({market.upper()}):\n\n"
            + "\n\n".join(sections)
            + "\n\n---\n"
            "Based on the above data, identify 3-5 promising stocks. "
            "For each candidate, run run_intelligence(ticker) and run_risk_assessment(ticker) "
            "to get a full analysis before adding to watchlist or trading."
        )

    return [
        run_intelligence,
        run_risk_assessment,
        run_execution,
        get_system_status,
        manage_portfolio,
        get_cached_analysis,
        manage_watchlist,
        scan_watchlist_signals,
        get_realtime_quote,
        discover_market_opportunities,
    ]
