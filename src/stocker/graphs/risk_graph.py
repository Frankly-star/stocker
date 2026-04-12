"""RiskAssessmentSubgraph: receives MarketIntelligenceReport, runs debates, outputs RiskAssessmentResult.

Debate flow: Bull↔Bear → ResearchManager → Trader → Aggressive→Conservative→Neutral → PortfolioManager
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from stocker.agents.risk.managers import create_portfolio_manager, create_research_manager
from stocker.agents.risk.researchers import create_bear_researcher, create_bull_researcher
from stocker.agents.risk.risk_debators import (
    create_aggressive_debator,
    create_conservative_debator,
    create_neutral_debator,
)
from stocker.agents.risk.trader import create_trader
from stocker.graphs.debate_graph import DebateController
from stocker.graphs.state import RiskAssessmentState, default_invest_debate, default_risk_debate
from stocker.memory.bm25_memory import BM25Memory


def build_risk_graph(
    llm: Any,
    bull_memory: BM25Memory,
    bear_memory: BM25Memory,
    trader_memory: BM25Memory,
    manager_memory: BM25Memory,
    pm_memory: BM25Memory,
    max_debate_rounds: int = 1,
    max_risk_rounds: int = 1,
) -> StateGraph:
    """Build the Risk Assessment Subgraph."""

    controller = DebateController(max_debate_rounds, max_risk_rounds)

    # Create agent nodes
    bull = create_bull_researcher(llm, bull_memory)
    bear = create_bear_researcher(llm, bear_memory)
    rm = create_research_manager(llm, manager_memory)
    trader = create_trader(llm, trader_memory)
    aggressive = create_aggressive_debator(llm)
    conservative = create_conservative_debator(llm)
    neutral = create_neutral_debator(llm)
    pm = create_portfolio_manager(llm, pm_memory)

    def init_debate_states(state: dict) -> dict:
        """Initialize debate states if not already set."""
        updates = {}
        if not state.get("investment_debate_state"):
            updates["investment_debate_state"] = default_invest_debate()
        if not state.get("risk_debate_state"):
            updates["risk_debate_state"] = default_risk_debate()
        return updates

    # Build graph
    graph = StateGraph(RiskAssessmentState)

    graph.add_node("init", init_debate_states)
    graph.add_node("bull_researcher", bull)
    graph.add_node("bear_researcher", bear)
    graph.add_node("research_manager", rm)
    graph.add_node("trader", trader)
    graph.add_node("aggressive", aggressive)
    graph.add_node("conservative", conservative)
    graph.add_node("neutral", neutral)
    graph.add_node("portfolio_manager", pm)

    graph.set_entry_point("init")
    graph.add_edge("init", "bull_researcher")

    # Investment debate loop
    graph.add_conditional_edges(
        "bull_researcher",
        controller.should_continue_invest_debate,
        {"bear_researcher": "bear_researcher", "research_manager": "research_manager"},
    )
    graph.add_conditional_edges(
        "bear_researcher",
        controller.should_continue_invest_debate,
        {"bull_researcher": "bull_researcher", "research_manager": "research_manager"},
    )

    graph.add_edge("research_manager", "trader")
    graph.add_edge("trader", "aggressive")

    # Risk debate loop
    graph.add_conditional_edges(
        "aggressive",
        controller.should_continue_risk_debate,
        {"conservative": "conservative", "portfolio_manager": "portfolio_manager"},
    )
    graph.add_conditional_edges(
        "conservative",
        controller.should_continue_risk_debate,
        {"neutral": "neutral", "portfolio_manager": "portfolio_manager"},
    )
    graph.add_conditional_edges(
        "neutral",
        controller.should_continue_risk_debate,
        {"aggressive": "aggressive", "portfolio_manager": "portfolio_manager"},
    )

    graph.add_edge("portfolio_manager", END)

    return graph.compile()
