"""Research Manager and Portfolio Manager. Extracted from TradingAgents."""

from __future__ import annotations

from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage

from stocker.memory.bm25_memory import BM25Memory


def create_research_manager(llm: Any, memory: BM25Memory) -> Callable:
    """Research Manager: judges the bull/bear debate and produces an investment plan."""

    def research_manager_node(state: dict) -> dict:
        debate_state = state.get("investment_debate_state", {})
        debate_history = debate_state.get("history", "")

        memories = memory.get_memories(debate_history[:500], n_matches=1)
        memory_ctx = ""
        if memories:
            memory_ctx = f"\n\nPast relevant judgment:\n{memories[0]['recommendation']}"

        system_prompt = (
            "You are a Research Manager. You judge the bull vs bear debate and produce a clear investment plan.\n"
            "Weigh both sides' arguments based on data quality and reasoning strength.\n"
            "Output a clear investment recommendation with:\n"
            "- Overall thesis (bullish/bearish/neutral)\n"
            "- Key factors supporting the decision\n"
            "- Suggested entry strategy for range/swing trading\n"
            "- Risk factors to monitor"
            + memory_ctx
        )

        try:
            from stocker.evolution.adapters.langgraph_prompt_resolver import resolve_prompt
            resolved_prompt = resolve_prompt(
                team="risk",
                node="research_manager",
                base_prompt=system_prompt,
                state=state,
            )
        except Exception:
            resolved_prompt = None
        human_content = f"Debate:\n{debate_history}"
        messages = [
            SystemMessage(content=resolved_prompt.prompt if resolved_prompt else system_prompt),
            HumanMessage(content=human_content),
        ]

        import time
        t0 = time.time()
        response = llm.invoke(messages)
        duration_ms = int((time.time() - t0) * 1000)
        try:
            from stocker.evolution.adapters.trace_store import record_node_trace
            record_node_trace(
                team="risk",
                node="research_manager",
                state=state,
                input_text=human_content,
                output_text=response.content,
                resolved_prompt=resolved_prompt,
                duration_ms=duration_ms,
            )
        except Exception:
            pass

        new_debate = dict(debate_state)
        new_debate["judge_decision"] = response.content

        return {
            "messages": [response],
            "investment_debate_state": new_debate,
            "investment_plan": response.content,
        }

    return research_manager_node


# Prompt template — placeholders filled at runtime from strategy config
_PM_PROMPT_TEMPLATE = """\
You are the Portfolio Manager making the FINAL trading decision.
Review the risk debate (aggressive/conservative/neutral views) and investment plan.

## CRITICAL: Price Consistency Validation
Before outputting your decision, you MUST verify:
1. Extract the current stock price from the market data in the situation text.
2. Ensure stop_loss is {stop_loss_min_pct}-{stop_loss_max_pct}% BELOW the current price \
(never less than {price_validation_min_pct}%).
3. Ensure take_profit is ABOVE the current price by a reasonable margin.
4. Risk:Reward ratio should be at least 1:{take_profit_min_ratio}.
5. If the trader's plan has stop/target levels that don't match the current price \
(e.g., stop is <{price_validation_min_pct}% from price, or target is from a completely \
different price range), OVERRIDE them with sensible values anchored to the current price.

## Output Format
- Rating: BUY / OVERWEIGHT / HOLD / UNDERWEIGHT / SELL
- Confidence: 0-100%
- Position size: {position_size_min_pct}-{position_size_max_pct}% of portfolio
- Current Price: $XXX.XX (from market data)
- Stop Loss: $XXX.XX (= price - X%)
- Take Profit: $XXX.XX (= price + X%, primary target)
- Take Profit 2: $XXX.XX (secondary target, if applicable)
- Risk:Reward: 1:X.X
- Key reasons (top 3)
- One-paragraph investment thesis

Be decisive. This is the final output that drives actual trade execution."""


def create_portfolio_manager(llm: Any, memory: BM25Memory) -> Callable:
    """Portfolio Manager: final risk arbiter, outputs the definitive trading decision."""

    def portfolio_manager_node(state: dict) -> dict:
        risk_state = state.get("risk_debate_state", {})
        risk_history = risk_state.get("history", "")
        investment_plan = state.get("investment_plan", "")
        trader_plan = state.get("trader_investment_plan", "")
        situation = state.get("situation_text", "")

        # Load risk parameters from strategy config
        try:
            from stocker.strategy import get_strategy
            r = get_strategy().risk
        except Exception:
            from types import SimpleNamespace
            r = SimpleNamespace(
                stop_loss_min_pct=2.0, stop_loss_max_pct=10.0,
                take_profit_min_ratio=1.5,
                position_size_min_pct=2.0, position_size_max_pct=10.0,
                price_validation_min_pct=1.0,
            )

        memories = memory.get_memories(risk_history[:500], n_matches=1)
        memory_ctx = ""
        if memories:
            memory_ctx = f"\n\nPast portfolio decision:\n{memories[0]['recommendation']}"

        system_prompt = _PM_PROMPT_TEMPLATE.format(
            stop_loss_min_pct=r.stop_loss_min_pct,
            stop_loss_max_pct=r.stop_loss_max_pct,
            take_profit_min_ratio=r.take_profit_min_ratio,
            position_size_min_pct=r.position_size_min_pct,
            position_size_max_pct=r.position_size_max_pct,
            price_validation_min_pct=r.price_validation_min_pct,
        ) + memory_ctx

        human_content = (
            f"Market Situation:\n{situation[:2000]}\n\n"
            f"Investment Plan:\n{investment_plan}\n\n"
            f"Trader's Plan:\n{trader_plan}\n\n"
            f"Risk Debate:\n{risk_history}"
        )

        try:
            from stocker.evolution.adapters.langgraph_prompt_resolver import resolve_prompt
            resolved_prompt = resolve_prompt(
                team="risk",
                node="portfolio_manager",
                base_prompt=system_prompt,
                state=state,
            )
        except Exception:
            resolved_prompt = None
        messages = [
            SystemMessage(content=resolved_prompt.prompt if resolved_prompt else system_prompt),
            HumanMessage(content=human_content),
        ]

        import time
        t0 = time.time()
        response = llm.invoke(messages)
        duration_ms = int((time.time() - t0) * 1000)
        try:
            from stocker.evolution.adapters.trace_store import record_node_trace
            record_node_trace(
                team="risk",
                node="portfolio_manager",
                state=state,
                input_text=human_content,
                output_text=response.content,
                resolved_prompt=resolved_prompt,
                duration_ms=duration_ms,
            )
        except Exception:
            pass

        new_risk = dict(risk_state)
        new_risk["judge_decision"] = response.content

        # Parse LLM response into structured RiskAssessmentResult
        risk_assessment = _parse_risk_assessment(response.content, state.get("ticker", ""))

        return {
            "messages": [response],
            "risk_debate_state": new_risk,
            "final_trade_decision": response.content,
            "risk_assessment": risk_assessment,
        }

    return portfolio_manager_node


def _parse_risk_assessment(text: str, ticker: str):
    """Best-effort parse portfolio manager's text response into RiskAssessmentResult."""
    import re
    from stocker.analysis.models import RiskAssessmentResult

    result = RiskAssessmentResult(ticker=ticker)

    # Rating
    m = re.search(r'Rating:\s*(BUY|OVERWEIGHT|HOLD|UNDERWEIGHT|SELL)', text, re.IGNORECASE)
    if m:
        result.rating = m.group(1).upper()

    # Confidence
    m = re.search(r'Confidence:\s*(\d+)\s*%', text, re.IGNORECASE)
    if m:
        result.confidence = int(m.group(1)) / 100.0

    # Stop Loss
    m = re.search(r'Stop\s*Loss:\s*\$?([\d.]+)', text, re.IGNORECASE)
    if m:
        result.stop_loss = float(m.group(1))

    # Take Profit (first one)
    m = re.search(r'Take\s*Profit(?:\s*1)?:\s*\$?([\d.]+)', text, re.IGNORECASE)
    if m:
        result.take_profit = float(m.group(1))

    # Position size
    m = re.search(r'Position\s*[Ss]ize:\s*([\d.]+)\s*%', text, re.IGNORECASE)
    if m:
        result.position_size_pct = float(m.group(1))

    # Risk level from Risk:Reward or explicit mention
    m = re.search(r'Risk(?::|\s*Level):\s*(LOW|MEDIUM|HIGH)', text, re.IGNORECASE)
    if m:
        result.risk_level = m.group(1).upper()

    # Suggested action — use rating as fallback
    action_map = {"BUY": "买入", "OVERWEIGHT": "加仓", "HOLD": "持有", "UNDERWEIGHT": "减仓", "SELL": "卖出"}
    result.suggested_action = action_map.get(result.rating, result.rating)

    # Investment thesis — last paragraph or everything after "thesis"
    m = re.search(r'(?:thesis|论点|总结)[:\s]*(.+)', text, re.IGNORECASE | re.DOTALL)
    if m:
        result.investment_thesis = m.group(1).strip()[:500]
    else:
        # Use last paragraph as thesis
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        if paragraphs:
            result.investment_thesis = paragraphs[-1][:500]

    # Key reasons
    reasons = re.findall(r'(?:^|\n)\s*[-•\d.]+\s*(.+?)(?=\n|$)', text)
    if reasons:
        result.key_reasons = [r.strip() for r in reasons[:5] if len(r.strip()) > 10]

    return result
