"""Generic debate subgraph template. Supports 2-party and 3-party debates.

Extracted from TradingAgents conditional_logic.py and generalized.
"""

from __future__ import annotations


class DebateController:
    """Controls debate loop termination, extracted from TradingAgents ConditionalLogic."""

    def __init__(self, max_debate_rounds: int = 1, max_risk_rounds: int = 1) -> None:
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_rounds = max_risk_rounds

    def should_continue_invest_debate(self, state: dict) -> str:
        """2-party debate: Bull vs Bear."""
        debate = state.get("investment_debate_state", {})
        count = debate.get("count", 0)
        current = debate.get("current_response", "")

        if count >= 2 * self.max_debate_rounds:
            return "research_manager"
        if current.startswith("Bull"):
            return "bear_researcher"
        return "bull_researcher"

    def should_continue_risk_debate(self, state: dict) -> str:
        """3-party debate: Aggressive → Conservative → Neutral."""
        risk = state.get("risk_debate_state", {})
        count = risk.get("count", 0)
        speaker = risk.get("latest_speaker", "")

        if count >= 3 * self.max_risk_rounds:
            return "portfolio_manager"
        if speaker.startswith("Aggressive"):
            return "conservative"
        if speaker.startswith("Conservative"):
            return "neutral"
        return "aggressive"

    def should_continue_tool_call(self, state: dict) -> str:
        """Check if last message has tool calls (for agent tool-use loops)."""
        messages = state.get("messages", [])
        if messages and hasattr(messages[-1], "tool_calls") and messages[-1].tool_calls:
            return "tools"
        return "done"
