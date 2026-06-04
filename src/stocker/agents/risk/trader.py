"""Trader Agent: makes trading plan based on research manager's investment plan + BM25 memory."""

from __future__ import annotations

from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage

from stocker.memory.bm25_memory import BM25Memory

# Prompt template — placeholders filled at runtime from strategy config
_TRADER_PROMPT_TEMPLATE = """\
You are an experienced Swing Trader specializing in range-bound markets.
Based on the investment plan from the Research Manager, create a concrete trading plan.

## CRITICAL: Price Consistency Rules
You will be given the current stock price in the market data. ALL your price levels MUST be \
anchored to this current price. Specifically:
- **Stop loss**: Must be {stop_loss_min_pct}-{stop_loss_max_pct}% below entry depending on volatility.
  Calculate: stop_loss = current_price * (1 - stop_pct). State the EXACT dollar amount.
- **Take profit targets**: Must be based on identified support/resistance levels from the data.
  If no clear levels, use risk:reward ratio of at least 1:{take_profit_min_ratio}.
- **Position sizing**: {position_size_min_pct}-{position_size_max_pct}% of portfolio for a single trade.
- **NEVER use stop/target values from previous analyses or memory that don't match the current price.**
  For example, if the stock is at $850, a $3.50 stop loss (0.4%) is absurd — that's noise, not a stop.

## Required Output Format
- Current Price: $XXX.XX (from market data)
- Entry Point: $XXX.XX (specific level or 'market')
- Stop Loss: $XXX.XX (= entry - X%, state both the $ level and the %)
- Target 1: $XXX.XX (= entry + X%, state the key resistance level)
- Target 2: $XXX.XX (secondary target if applicable)
- Position Size: X% of portfolio
- Risk:Reward Ratio: 1:X.X
- Trade Management: trailing stop, partial exit rules

Be specific with price levels. Double-check that stop_loss < entry < targets."""


def create_trader(llm: Any, memory: BM25Memory) -> Callable:
    """Trader: translates investment plan into concrete trading action."""

    def trader_node(state: dict) -> dict:
        investment_plan = state.get("investment_plan", "")
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
            )

        # Memory-augmented decision
        memories = memory.get_memories(situation[:500], n_matches=2)
        memory_ctx = ""
        if memories:
            memory_ctx = "\n\nRelevant trading memories:\n" + "\n".join(
                f"- (score: {m['similarity_score']:.2f}) {m['recommendation'][:200]}"
                for m in memories
            )

        system_prompt = _TRADER_PROMPT_TEMPLATE.format(
            stop_loss_min_pct=r.stop_loss_min_pct,
            stop_loss_max_pct=r.stop_loss_max_pct,
            take_profit_min_ratio=r.take_profit_min_ratio,
            position_size_min_pct=r.position_size_min_pct,
            position_size_max_pct=r.position_size_max_pct,
        ) + memory_ctx
        try:
            from stocker.evolution.adapters.langgraph_prompt_resolver import resolve_prompt
            resolved_prompt = resolve_prompt(
                team="risk",
                node="trader",
                base_prompt=system_prompt,
                state=state,
            )
        except Exception:
            resolved_prompt = None

        human_content = f"Investment Plan:\n{investment_plan}\n\nMarket Data:\n{situation[:3000]}"
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
                node="trader",
                state=state,
                input_text=human_content,
                output_text=response.content,
                resolved_prompt=resolved_prompt,
                duration_ms=duration_ms,
            )
        except Exception:
            pass

        return {
            "messages": [response],
            "trader_investment_plan": response.content,
        }

    return trader_node
