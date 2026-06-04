"""MainGraph: Supervisor-driven top-level graph with ReAct tool execution loop.

Flow: START → supervisor_node → (tool_calls?) → execute_tools → supervisor_node → ... → END

Supports an optional `on_event` callback for real-time dispatch logging.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from stocker.agents.supervisor import SUPERVISOR_SYSTEM_PROMPT, create_supervisor_tools
from stocker.graphs.state import StockerState

logger = logging.getLogger(__name__)


def build_main_graph(
    llm: Any,
    supervisor_tools: list | None = None,
    **kwargs: Any,
) -> StateGraph:
    """Build the top-level Supervisor-driven graph.

    Args:
        llm: LangChain chat model for the Supervisor
        supervisor_tools: List of tools for the Supervisor (from create_supervisor_tools)

    Returns:
        Compiled StateGraph
    """
    tools = supervisor_tools or create_supervisor_tools(**kwargs)
    bound_llm = llm.bind_tools(tools)
    raw_tool_node = ToolNode(tools)

    # Build a tool name lookup for logging
    tool_names = {t.name: t for t in tools}

    def supervisor_node(state: dict) -> dict:
        """The Supervisor Agent node: LLM with tools."""
        on_event = state.get("_on_event")
        messages = state.get("messages", [])

        # Build system prompt with current execution mode injected
        from stocker.engine.runtime_state import get_execution_mode
        current_mode = get_execution_mode().upper()
        dynamic_system_prompt = (
            f"[SYSTEM STATUS] Current execution_mode = {current_mode}\n\n"
            + SUPERVISOR_SYSTEM_PROMPT
        )
        try:
            from stocker.evolution.adapters.langgraph_prompt_resolver import resolve_prompt
            resolved_prompt = resolve_prompt(
                team="supervisor",
                node="supervisor",
                base_prompt=dynamic_system_prompt,
                state=state,
            )
        except Exception:
            resolved_prompt = None

        # Always replace/inject system prompt with latest mode
        non_system = [m for m in messages if not isinstance(m, SystemMessage)]
        messages = [SystemMessage(content=resolved_prompt.prompt if resolved_prompt else dynamic_system_prompt)] + non_system

        if on_event:
            on_event("supervisor", "thinking", "Supervisor 正在分析意图...")

        t0 = time.time()
        response = bound_llm.invoke(messages)
        elapsed = time.time() - t0

        if on_event:
            if response.tool_calls:
                tool_call_names = [tc["name"] for tc in response.tool_calls]
                on_event("supervisor", "tool_decision",
                         f"Supervisor 决定调用: {', '.join(tool_call_names)}",
                         {"tools": tool_call_names, "elapsed": f"{elapsed:.1f}s"})
            else:
                on_event("supervisor", "responding",
                         f"Supervisor 生成最终回复 ({elapsed:.1f}s)")

        tool_call_names = [tc["name"] for tc in response.tool_calls] if response.tool_calls else []
        try:
            from stocker.evolution.adapters.trace_store import record_node_trace
            record_node_trace(
                team="supervisor",
                node="supervisor",
                state=state,
                input_text="\n".join(str(m.content) for m in non_system[-3:] if hasattr(m, "content")),
                output_text=", ".join(tool_call_names) if tool_call_names else getattr(response, "content", ""),
                resolved_prompt=resolved_prompt,
                duration_ms=int(elapsed * 1000),
                metadata={"tool_calls": tool_call_names, "execution_mode": current_mode},
            )
        except Exception:
            pass

        logger.info("Supervisor responded in %.1fs, tool_calls=%s",
                    elapsed, tool_call_names or "none")

        return {"messages": [response]}

    def tools_node(state: dict) -> dict:
        """Execute tools and log each call."""
        on_event = state.get("_on_event")
        messages = state.get("messages", [])

        # Find the tool calls from the last AI message
        last_msg = messages[-1] if messages else None
        if last_msg and isinstance(last_msg, AIMessage) and last_msg.tool_calls:
            for tc in last_msg.tool_calls:
                tool_name = tc["name"]
                tool_args = tc.get("args", {})

                if on_event:
                    # Friendly label
                    label = _tool_display_name(tool_name, tool_args)
                    on_event("tool", "calling", f"调用工具: {label}",
                             {"tool": tool_name, "args": tool_args})

                logger.info("Executing tool: %s(%s)", tool_name, tool_args)

        # Execute all tools
        t0 = time.time()
        result = raw_tool_node.invoke(state)
        elapsed = time.time() - t0

        if on_event:
            on_event("tool", "completed", f"工具执行完成 ({elapsed:.1f}s)")

        logger.info("Tools executed in %.1fs", elapsed)
        return result

    def should_continue(state: dict) -> str:
        """Check if supervisor wants to call tools or is done."""
        messages = state.get("messages", [])
        if not messages:
            return "end"
        last = messages[-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return "end"

    # Build graph
    graph = StateGraph(StockerState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("tools", tools_node)

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        should_continue,
        {"tools": "tools", "end": END},
    )
    graph.add_edge("tools", "supervisor")

    return graph.compile()


def _tool_display_name(tool_name: str, args: dict) -> str:
    """Generate a user-friendly display name for a tool call."""
    labels = {
        "run_intelligence": "数据分析团队",
        "run_risk_assessment": "风险评估团队",
        "run_execution": "交易执行",
        "get_system_status": "系统状态查询",
        "manage_portfolio": "持仓管理",
        "get_cached_analysis": "读取缓存分析",
        "manage_watchlist": "股票池管理",
        "scan_watchlist_signals": "信号扫描",
        "get_realtime_quote": "实时报价",
        "discover_market_opportunities": "市场机会发现",
    }
    base = labels.get(tool_name, tool_name)
    ticker = args.get("ticker", "")
    if ticker:
        return f"{base} → {ticker}"
    action = args.get("action", "")
    if action:
        return f"{base} → {action}"
    return base
