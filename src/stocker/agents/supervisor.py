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

## Decision Logic
You decide what to do based on the conversation — no manual mode selection needed:
- User asks to "analyze" a stock → call run_intelligence AND run_risk_assessment, then provide a comprehensive investment recommendation
- User asks for a "recommendation" → run_intelligence + run_risk_assessment
- User asks to "buy" or "sell" → check mode, then run_execution if ACTIVE
- User asks about status / portfolio → use appropriate tools
- For scheduled tasks (prefixed with "scheduled:") → run full pipeline

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

    return [
        run_intelligence,
        run_risk_assessment,
        run_execution,
        get_system_status,
        manage_portfolio,
        get_cached_analysis,
    ]
