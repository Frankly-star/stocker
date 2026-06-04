"""Parameterized Agent factory with ReAct tool execution loop.

Both Intelligence and Risk teams use this factory to create agent nodes.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

# Max tool-call rounds to prevent infinite loops
MAX_TOOL_ROUNDS = 5


def create_agent_node(
    llm: Any,
    system_prompt: str,
    tools: list[BaseTool] | None = None,
    output_field: str | None = None,
) -> Callable:
    """Create a LangGraph node function with ReAct tool execution loop.

    Args:
        llm: LangChain chat model
        system_prompt: System message for the agent
        tools: Optional tools to bind (for ReAct-style tool calling)
        output_field: If set, store the response in this state field

    Returns:
        A callable(state) -> dict that can be used as a LangGraph node.
    """
    bound_llm = llm.bind_tools(tools) if tools else llm
    tool_map = {t.name: t for t in tools} if tools else {}

    def agent_node(state: dict) -> dict:
        messages = state.get("messages", [])

        full_messages = [SystemMessage(content=system_prompt)]
        for msg in messages:
            if isinstance(msg, (HumanMessage, AIMessage, SystemMessage)):
                full_messages.append(msg)

        # ReAct loop: LLM → tool_calls? → execute → feed back → LLM → ...
        for round_i in range(MAX_TOOL_ROUNDS + 1):
            response = bound_llm.invoke(full_messages)
            full_messages.append(response)

            if not response.tool_calls:
                break  # No more tools to call — done

            # Execute each tool call
            for tc in response.tool_calls:
                tool_name = tc["name"]
                tool_args = tc.get("args", {})
                tool_id = tc.get("id", "")

                if tool_name in tool_map:
                    try:
                        tool_result = tool_map[tool_name].invoke(tool_args)
                        logger.info("Agent tool %s(%s) → %d chars",
                                    tool_name, tool_args, len(str(tool_result)))
                    except Exception as e:
                        tool_result = f"Tool error: {e}"
                        logger.error("Agent tool %s failed: %s", tool_name, e)
                else:
                    tool_result = f"Unknown tool: {tool_name}"

                full_messages.append(ToolMessage(
                    content=str(tool_result),
                    tool_call_id=tool_id,
                ))

        # Final response is the last AI message with content
        final_content = response.content if hasattr(response, "content") else ""

        result = {"messages": [response]}
        if output_field:
            result[output_field] = final_content
        return result

    return agent_node


def create_analyst_node(
    llm: Any,
    system_prompt: str,
    tools: list[BaseTool],
    report_field: str,
) -> Callable:
    """Create an analyst node with ReAct tool execution loop.

    Used by Intelligence Team agents (market_data, news, fundamentals, social).
    The agent calls tools to gather data, then produces a text report.
    """
    bound_llm = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    def analyst_node(state: dict) -> dict:
        ticker = state.get("ticker", "")
        trade_date = state.get("trade_date", "")
        messages = state.get("messages", [])

        # If no trade_date provided, use today
        if not trade_date:
            from datetime import datetime
            trade_date = datetime.now().strftime("%Y-%m-%d")

        # Compute a reasonable lookback for news/data
        from datetime import datetime, timedelta
        end_dt = datetime.strptime(trade_date, "%Y-%m-%d")
        start_date = (end_dt - timedelta(days=30)).strftime("%Y-%m-%d")

        tool_names = ", ".join(t.name for t in tools)

        # Build initial messages with ticker context + date + tool guidance
        full_messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=(
                f"Analyze {ticker}. The current date is {trade_date}.\n"
                f"Date range for data: {start_date} to {trade_date}.\n"
                f"Available tools: {tool_names}\n"
                f"IMPORTANT: You MUST call your tools to gather real data first. "
                f"Use the exact ticker '{ticker}' in all tool calls (preserve any exchange suffix like .HK, .L, .TO). "
                f"When tools require date parameters, use start_date={start_date} and end_date={trade_date}. "
                f"After gathering data, provide your comprehensive analysis."
            )),
        ]

        # ReAct loop
        final_content = ""
        for round_i in range(MAX_TOOL_ROUNDS + 1):
            response = bound_llm.invoke(full_messages)
            full_messages.append(response)

            if not response.tool_calls:
                final_content = response.content if hasattr(response, "content") else ""
                break

            # Execute tools
            for tc in response.tool_calls:
                tool_name = tc["name"]
                tool_args = tc.get("args", {})
                tool_id = tc.get("id", "")

                logger.info("[%s] Agent calling tool: %s(%s)", report_field, tool_name, tool_args)

                if tool_name in tool_map:
                    try:
                        tool_result = tool_map[tool_name].invoke(tool_args)
                        logger.info("[%s] Tool %s returned %d chars",
                                    report_field, tool_name, len(str(tool_result)))
                    except Exception as e:
                        tool_result = f"Tool error: {e}"
                        logger.error("[%s] Tool %s failed: %s", report_field, tool_name, e)
                else:
                    tool_result = f"Unknown tool: {tool_name}"

                full_messages.append(ToolMessage(
                    content=str(tool_result),
                    tool_call_id=tool_id,
                ))

        logger.info("[%s] Agent produced %d chars of report", report_field, len(final_content))

        return {
            "messages": [response],
            report_field: final_content,
        }

    return analyst_node


def create_analysis_node(
    llm: Any,
    system_prompt: str,
    report_field: str,
    data_keys: list[str],
) -> Callable:
    """Create a pure-analysis node that reads from shared_data instead of calling tools.

    The DataFetcher node populates `shared_data` once. Each analysis node
    picks the relevant data slices (via data_keys) and asks the LLM to
    produce a report. No tool calls, no duplicate API requests.

    Args:
        llm: LangChain chat model (plain, no tools bound)
        system_prompt: System message describing the analyst role
        report_field: State field to store the output report
        data_keys: Which keys from shared_data this analyst needs
                   e.g. ["quote", "kline", "technical"] for market analyst
    """

    def analysis_node(state: dict) -> dict:
        ticker = state.get("ticker", "")
        trade_date = state.get("trade_date", "")
        shared = state.get("shared_data") or {}

        if not trade_date:
            from datetime import datetime
            trade_date = datetime.now().strftime("%Y-%m-%d")

        # Assemble the data context from shared_data
        data_sections = []
        for key in data_keys:
            value = shared.get(key, "")
            if value and len(str(value).strip()) > 10:
                data_sections.append(f"## {key.upper().replace('_', ' ')}\n{value}")

        if data_sections:
            data_context = "\n\n".join(data_sections)
        else:
            data_context = "WARNING: No data available for this analysis. Provide best assessment based on general knowledge."

        sources = shared.get("sources_used", [])
        warnings = shared.get("data_warnings", [])
        sources_text = ", ".join(sources) if sources else "none"
        warnings_text = "\n".join(f"- {w}" for w in warnings) if warnings else "none"

        user_message = (
            f"Analyze {ticker}. Current date: {trade_date}.\n"
            f"Data sources used: {sources_text}\n"
            f"Data warnings: {warnings_text}\n\n"
            f"--- BEGIN DATA ---\n{data_context}\n--- END DATA ---\n\n"
            f"Based on the data above, provide your comprehensive analysis. "
            f"Use ONLY the data provided. Do NOT make up numbers. "
            f"If fixed-source data is missing, state that clearly instead of inventing values."
        )

        node_name = {
            "market_report": "market_data",
            "news_report": "news",
            "fundamentals_report": "fundamentals",
            "social_report": "social",
        }.get(report_field, report_field)

        try:
            from stocker.evolution.adapters.langgraph_prompt_resolver import resolve_prompt
            resolved_prompt = resolve_prompt(
                team="intelligence",
                node=node_name,
                base_prompt=system_prompt,
                state=state,
            )
        except Exception:
            resolved_prompt = None

        messages = [
            SystemMessage(content=resolved_prompt.prompt if resolved_prompt else system_prompt),
            HumanMessage(content=user_message),
        ]

        import time
        t0 = time.time()
        response = llm.invoke(messages)
        duration_ms = int((time.time() - t0) * 1000)
        final_content = response.content if hasattr(response, "content") else ""

        try:
            from stocker.evolution.adapters.trace_store import record_node_trace
            record_node_trace(
                team="intelligence",
                node=node_name,
                state=state,
                input_text=user_message,
                output_text=final_content,
                resolved_prompt=resolved_prompt,
                duration_ms=duration_ms,
            )
        except Exception:
            pass

        logger.info("[%s] Analysis produced %d chars", report_field, len(final_content))

        return {
            "messages": [response],
            report_field: final_content,
        }

    return analysis_node
