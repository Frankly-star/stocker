"""DataIntelligenceSubgraph: DataFetcher → 4 analysis agents → aggregation.

Architecture:
  1. DataFetcher node: calls all data sources ONCE, stores in shared_data
  2. 4 Analyst nodes: read from shared_data, produce text reports (NO tool calls)
  3. Aggregate node: combine reports into MarketIntelligenceReport

This eliminates duplicate API calls — data is fetched once, shared everywhere.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from stocker.agents.factory import create_analysis_node
from stocker.agents.intelligence.data_fetcher import create_data_fetcher_node
from stocker.agents.intelligence.market_data_agent import MARKET_DATA_SYSTEM_PROMPT
from stocker.agents.intelligence.news_agent import NEWS_AGENT_SYSTEM_PROMPT
from stocker.agents.intelligence.fundamentals_agent import FUNDAMENTALS_AGENT_SYSTEM_PROMPT
from stocker.agents.intelligence.social_agent import SOCIAL_AGENT_SYSTEM_PROMPT
from stocker.graphs.state import IntelligenceState

logger = logging.getLogger(__name__)


def build_intelligence_graph(llm: Any, dataflow_tools: list = None, news_tools: list = None) -> StateGraph:
    """Build the Data Intelligence Subgraph.

    Args:
        llm: LangChain chat model
        dataflow_tools: (legacy, ignored) — data fetching is now centralized in DataFetcher
        news_tools: (legacy, ignored)

    Returns:
        Compiled StateGraph
    """
    # DataFetcher: one node to fetch ALL data
    fetcher_node = create_data_fetcher_node()

    # 4 pure-analysis nodes: each reads specific slices of shared_data
    market_node = create_analysis_node(
        llm, MARKET_DATA_SYSTEM_PROMPT, "market_report",
        data_keys=["quote", "kline", "technical"],
    )
    news_node = create_analysis_node(
        llm, NEWS_AGENT_SYSTEM_PROMPT, "news_report",
        data_keys=["news", "global_news"],
    )
    fund_node = create_analysis_node(
        llm, FUNDAMENTALS_AGENT_SYSTEM_PROMPT, "fundamentals_report",
        data_keys=["quote", "fundamentals", "finance", "rating"],
    )
    social_node = create_analysis_node(
        llm, SOCIAL_AGENT_SYSTEM_PROMPT, "social_report",
        data_keys=["news", "fund_flow", "insider"],
    )

    def aggregate_intelligence(state: dict) -> dict:
        """Aggregate all 4 reports into a MarketIntelligenceReport."""
        from stocker.analysis.models import MarketIntelligenceReport

        shared = state.get("shared_data") or {}
        report = MarketIntelligenceReport(
            ticker=state.get("ticker", ""),
            raw_reports={
                "market": state.get("market_report", ""),
                "news": state.get("news_report", ""),
                "fundamentals": state.get("fundamentals_report", ""),
                "social": state.get("social_report", ""),
            },
            data_sources_used=shared.get("sources_used", []),
        )
        quality = report.assess_data_quality()
        logger.info("Intelligence report for %s: data_quality=%s, warnings=%d, sources=%s",
                     state.get("ticker", ""), quality, len(report.data_warnings),
                     shared.get("sources_used", []))
        return {"intelligence_report": report}

    # Build graph
    graph = StateGraph(IntelligenceState)

    # Nodes
    graph.add_node("data_fetcher", fetcher_node)
    graph.add_node("market_data", market_node)
    graph.add_node("news", news_node)
    graph.add_node("fundamentals", fund_node)
    graph.add_node("social", social_node)
    graph.add_node("aggregate", aggregate_intelligence)

    # Edges: fetch → all 4 analysts (sequential for now) → aggregate
    graph.set_entry_point("data_fetcher")
    graph.add_edge("data_fetcher", "market_data")
    graph.add_edge("market_data", "news")
    graph.add_edge("news", "fundamentals")
    graph.add_edge("fundamentals", "social")
    graph.add_edge("social", "aggregate")
    graph.add_edge("aggregate", END)

    return graph.compile()
