"""Risk Debators: Aggressive, Conservative, Neutral. Extracted from TradingAgents."""

from __future__ import annotations

from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage


def _get_price_validation_rule() -> str:
    """Build price validation rule string from active strategy config."""
    try:
        from stocker.strategy import get_strategy
        r = get_strategy().risk
        min_pct = r.price_validation_min_pct
    except Exception:
        min_pct = 1.0

    return (
        f"\n\nIMPORTANT: Check the trader's stop loss and target prices against the CURRENT stock price "
        f"from the market data. If the stop loss is less than {min_pct}% from the current price, or if the target "
        f"price seems to come from a completely different price range, call this out as an error and "
        f"suggest corrected values."
    )


def _create_risk_debator(llm: Any, role: str, system_prompt: str) -> Callable:
    """Generic factory for risk debator nodes."""

    def debator_node(state: dict) -> dict:
        risk_state = state.get("risk_debate_state", {})
        trader_plan = state.get("trader_investment_plan", "")
        situation = state.get("situation_text", "")
        history = risk_state.get("history", "")

        human_msg = f"Current Market Data (use for price validation):\n{situation[:1500]}\n\n"
        human_msg += f"Trader's investment plan:\n{trader_plan}"
        if history:
            human_msg += f"\n\nDebate so far:\n{history}"

        node_name = role.lower()
        try:
            from stocker.evolution.adapters.langgraph_prompt_resolver import resolve_prompt
            resolved_prompt = resolve_prompt(
                team="risk",
                node=node_name,
                base_prompt=system_prompt,
                state=state,
            )
        except Exception:
            resolved_prompt = None
        messages = [
            SystemMessage(content=resolved_prompt.prompt if resolved_prompt else system_prompt),
            HumanMessage(content=human_msg),
        ]

        import time
        t0 = time.time()
        response = llm.invoke(messages)
        duration_ms = int((time.time() - t0) * 1000)
        content = response.content
        try:
            from stocker.evolution.adapters.trace_store import record_node_trace
            record_node_trace(
                team="risk",
                node=node_name,
                state=state,
                input_text=human_msg,
                output_text=content,
                resolved_prompt=resolved_prompt,
                duration_ms=duration_ms,
            )
        except Exception:
            pass

        new_state = dict(risk_state)
        new_state[f"{role.lower()}_history"] = content
        new_state["latest_speaker"] = f"{role} Analyst"
        new_state["history"] = history + f"\n\n**{role}:** {content}"
        new_state["count"] = new_state.get("count", 0) + 1

        return {
            "messages": [response],
            "risk_debate_state": new_state,
        }

    return debator_node


def create_aggressive_debator(llm: Any) -> Callable:
    return _create_risk_debator(llm, "Aggressive", (
        "You are an Aggressive Risk Analyst. You believe in taking calculated risks for higher returns.\n"
        "Evaluate the trader's plan from a growth and opportunity perspective.\n"
        "Argue for larger position sizes, tighter take-profits to capture momentum, and accepting reasonable risk."
        + _get_price_validation_rule()
    ))


def create_conservative_debator(llm: Any) -> Callable:
    return _create_risk_debator(llm, "Conservative", (
        "You are a Conservative Risk Analyst. You prioritize capital preservation.\n"
        "Evaluate the trader's plan from a risk-management perspective.\n"
        "Argue for smaller position sizes, wider stop-losses, and more cautious entry criteria."
        + _get_price_validation_rule()
    ))


def create_neutral_debator(llm: Any) -> Callable:
    return _create_risk_debator(llm, "Neutral", (
        "You are a Neutral Risk Analyst. You balance growth and safety.\n"
        "Evaluate the trader's plan by synthesizing the aggressive and conservative views.\n"
        "Provide a balanced recommendation considering both upside potential and downside risk."
        + _get_price_validation_rule()
    ))
