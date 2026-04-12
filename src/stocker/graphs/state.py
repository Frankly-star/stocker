"""LangGraph State definitions for all subgraphs."""

from __future__ import annotations

from typing import Annotated, Any, Callable

from langgraph.graph import MessagesState

from stocker.analysis.models import ExecutionMode, MarketIntelligenceReport, RiskAssessmentResult


# ---------------------------------------------------------------------------
# Top-level state (Supervisor + cross-team)
# ---------------------------------------------------------------------------

class StockerState(MessagesState):
    """Top-level state shared across Supervisor and all subgraphs.

    execution_mode controls ONLY whether trades are executed:
      - ACTIVE:  Supervisor can execute trades via broker
      - OBSERVE: Supervisor analyzes and recommends but never executes trades
    All other routing (analyze, assess, status, portfolio, etc.) is decided
    by the Supervisor LLM based on conversation context.
    """
    ticker: str | None = None
    trade_date: str | None = None
    execution_mode: ExecutionMode = ExecutionMode.OBSERVE  # safe default

    # Team outputs
    intelligence_report: MarketIntelligenceReport | None = None
    risk_assessment: RiskAssessmentResult | None = None
    execution_result: dict | None = None

    # Status / portfolio
    system_status: dict | None = None
    portfolio_action: str | None = None
    portfolio_result: dict | None = None

    # Runtime callback for streaming dispatch events (not persisted)
    _on_event: Callable | None = None


# ---------------------------------------------------------------------------
# Intelligence Team state
# ---------------------------------------------------------------------------

class IntelligenceState(MessagesState):
    """State for the Data Intelligence Subgraph."""
    ticker: str = ""
    trade_date: str = ""  # yyyy-mm-dd, auto-set to today if empty

    # Shared data — populated once by DataFetcher node, read by all analysts
    shared_data: dict = None  # type: ignore  # {quote, kline, technical, news, fundamentals, fund_flow, ...}

    # Per-agent reports (populated by analyst nodes)
    market_report: str = ""
    news_report: str = ""
    fundamentals_report: str = ""
    social_report: str = ""

    # Aggregated output
    intelligence_report: MarketIntelligenceReport | None = None


# ---------------------------------------------------------------------------
# Risk Assessment Team state
# ---------------------------------------------------------------------------

class InvestDebateState(dict):
    """Investment debate state (Bull vs Bear). Kept as dict for TradingAgents compat."""
    pass


class RiskDebateState(dict):
    """Risk debate state (Aggressive/Conservative/Neutral). Dict for compat."""
    pass


def default_invest_debate() -> dict:
    return {
        "bull_history": "",
        "bear_history": "",
        "history": "",
        "current_response": "",
        "judge_decision": "",
        "count": 0,
    }


def default_risk_debate() -> dict:
    return {
        "aggressive_history": "",
        "conservative_history": "",
        "neutral_history": "",
        "history": "",
        "latest_speaker": "",
        "judge_decision": "",
        "count": 0,
    }


class RiskAssessmentState(MessagesState):
    """State for the Risk Assessment Subgraph."""
    ticker: str = ""
    situation_text: str = ""  # MarketIntelligenceReport.to_situation_text()

    # Debate states
    investment_debate_state: dict = None  # type: ignore
    risk_debate_state: dict = None  # type: ignore

    # Intermediate outputs
    investment_plan: str = ""
    trader_investment_plan: str = ""
    final_trade_decision: str = ""

    # Final output
    risk_assessment: RiskAssessmentResult | None = None


# ---------------------------------------------------------------------------
# Execution Team state
# ---------------------------------------------------------------------------

class ExecutionState(MessagesState):
    """State for the Execution Subgraph."""
    ticker: str = ""
    order_params: dict | None = None
    risk_check_passed: bool = False
    execution_result: dict | None = None


# ---------------------------------------------------------------------------
# Portfolio state
# ---------------------------------------------------------------------------

class PortfolioState(MessagesState):
    """State for the Portfolio Management Subgraph."""
    action: str = ""  # add/remove/list/scan/sync
    ticker: str = ""
    params: dict | None = None
    result: dict | None = None
