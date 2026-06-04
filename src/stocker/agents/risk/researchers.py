"""Bull/Bear Researchers: extracted from TradingAgents, adapted to receive MarketIntelligenceReport."""

from __future__ import annotations

from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from stocker.memory.bm25_memory import BM25Memory


def create_bull_researcher(llm: Any, memory: BM25Memory) -> Callable:
    """Create Bull Researcher node. Argues the bullish case."""

    def bull_researcher_node(state: dict) -> dict:
        # Get MIR situation text from state
        situation = state.get("situation_text", "No market data available.")

        # Retrieve relevant memories
        memories = memory.get_memories(situation, n_matches=2)
        memory_context = ""
        if memories:
            memory_context = "\n\nRelevant past experiences:\n" + "\n".join(
                f"- {m['recommendation']}" for m in memories
            )

        # Get debate history
        debate_state = state.get("investment_debate_state", {})
        history = debate_state.get("history", "")
        bear_history = debate_state.get("bear_history", "")

        system_prompt = (
            "You are a Bull Researcher. Your role is to present the BULLISH case for the stock.\n"
            "Analyze the market intelligence data and argue why this is a good investment opportunity.\n"
            "Focus on: positive technical signals, favorable sentiment, strong fundamentals, growth catalysts.\n"
            "Be persuasive but grounded in data. Counter the bear's arguments if any."
            + memory_context
        )
        try:
            from stocker.evolution.adapters.langgraph_prompt_resolver import resolve_prompt
            resolved_prompt = resolve_prompt(
                team="risk",
                node="bull_researcher",
                base_prompt=system_prompt,
                state=state,
            )
        except Exception:
            resolved_prompt = None

        human_msg = f"Market Intelligence:\n{situation}"
        if bear_history:
            human_msg += f"\n\nBear's previous argument:\n{bear_history}"

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
                node="bull_researcher",
                state=state,
                input_text=human_msg,
                output_text=content,
                resolved_prompt=resolved_prompt,
                duration_ms=duration_ms,
            )
        except Exception:
            pass

        # Update debate state
        new_debate = dict(debate_state)
        new_debate["bull_history"] = content
        new_debate["current_response"] = f"Bull: {content[:50]}"
        new_debate["history"] = history + f"\n\n**Bull:** {content}"
        new_debate["count"] = new_debate.get("count", 0) + 1

        return {
            "messages": [response],
            "investment_debate_state": new_debate,
        }

    return bull_researcher_node


def create_bear_researcher(llm: Any, memory: BM25Memory) -> Callable:
    """Create Bear Researcher node. Argues the bearish case."""

    def bear_researcher_node(state: dict) -> dict:
        situation = state.get("situation_text", "No market data available.")

        memories = memory.get_memories(situation, n_matches=2)
        memory_context = ""
        if memories:
            memory_context = "\n\nRelevant past experiences:\n" + "\n".join(
                f"- {m['recommendation']}" for m in memories
            )

        debate_state = state.get("investment_debate_state", {})
        history = debate_state.get("history", "")
        bull_history = debate_state.get("bull_history", "")

        system_prompt = (
            "You are a Bear Researcher. Your role is to present the BEARISH case for the stock.\n"
            "Analyze the market intelligence data and argue why this is a risky investment.\n"
            "Focus on: negative technical signals, unfavorable sentiment, weak fundamentals, risk factors.\n"
            "Be persuasive but grounded in data. Counter the bull's arguments."
            + memory_context
        )
        try:
            from stocker.evolution.adapters.langgraph_prompt_resolver import resolve_prompt
            resolved_prompt = resolve_prompt(
                team="risk",
                node="bear_researcher",
                base_prompt=system_prompt,
                state=state,
            )
        except Exception:
            resolved_prompt = None

        human_msg = f"Market Intelligence:\n{situation}"
        if bull_history:
            human_msg += f"\n\nBull's previous argument:\n{bull_history}"

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
                node="bear_researcher",
                state=state,
                input_text=human_msg,
                output_text=content,
                resolved_prompt=resolved_prompt,
                duration_ms=duration_ms,
            )
        except Exception:
            pass

        new_debate = dict(debate_state)
        new_debate["bear_history"] = content
        new_debate["current_response"] = f"Bear: {content[:50]}"
        new_debate["history"] = history + f"\n\n**Bear:** {content}"
        new_debate["count"] = new_debate.get("count", 0) + 1

        return {
            "messages": [response],
            "investment_debate_state": new_debate,
        }

    return bear_researcher_node
