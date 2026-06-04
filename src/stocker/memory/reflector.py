"""Reflector: post-trade reflection mechanism. Extracted from TradingAgents reflection.py.

Changes: accepts MarketIntelligenceReport instead of 4 separate report strings.
Reflects on both Data Intelligence Team and Risk Assessment Team quality.
"""

from __future__ import annotations

import logging
from typing import Any

from stocker.memory.bm25_memory import BM25Memory

logger = logging.getLogger(__name__)

REFLECTION_SYSTEM_PROMPT = """You are an expert financial analyst reviewing trading decisions.
Analyze whether each decision was correct (increased returns) or incorrect.

For each decision, evaluate:
1. Market intelligence quality (technical indicators, support/resistance identification)
2. News and sentiment analysis accuracy
3. Fundamental data interpretation
4. Risk assessment quality (debate conclusions)
5. Overall decision-making process

Provide:
- Reasoning: Why did this succeed or fail?
- Improvement: What should be done differently next time?
- Summary: Key lessons in one concise paragraph (under 500 tokens).
"""


class Reflector:
    """Reflects on trading decisions and updates BM25 memories."""

    def __init__(self, llm: Any) -> None:
        self._llm = llm

    def _reflect(self, component: str, report: str, situation: str, returns: str) -> str:
        """Generate reflection for a component."""
        messages = [
            ("system", REFLECTION_SYSTEM_PROMPT),
            ("human", (
                f"Component: {component}\n"
                f"Returns/Losses: {returns}\n\n"
                f"Analysis/Decision:\n{report}\n\n"
                f"Market Situation:\n{situation}"
            )),
        ]
        return self._llm.invoke(messages).content

    def reflect_and_remember(
        self,
        situation_text: str,
        decisions: dict[str, str],
        returns: str,
        memories: dict[str, BM25Memory],
    ) -> dict[str, str]:
        """Reflect on all components and update their memories.

        Args:
            situation_text: MarketIntelligenceReport.to_situation_text() output
            decisions: {component_name: decision_text} — e.g. {"bull": "...", "trader": "..."}
            returns: String describing the trade outcome
            memories: {component_name: BM25Memory} — memories to update

        Returns:
            {component_name: reflection_text}
        """
        reflections = {}
        for component, decision in decisions.items():
            try:
                reflection = self._reflect(component, decision, situation_text, returns)
                reflections[component] = reflection

                # Update memory if available
                if component in memories:
                    memories[component].add_situations([(situation_text, reflection)])
                    logger.info("Updated %s memory (now %d entries)", component, memories[component].size)
            except Exception as e:
                logger.error("Reflection failed for %s: %s", component, e)
                reflections[component] = f"Reflection error: {e}"

        return reflections

    def reflect_and_propose_patches(
        self,
        situation_text: str,
        decisions: dict[str, str],
        returns: str,
        memories: dict[str, BM25Memory],
        skill_targets: dict[str, str],
    ) -> dict[str, object]:
        """Reflect as before, then create optional EvolutionSkill patch drafts.

        ``skill_targets`` maps component names (for example ``trader``) to
        target evolution skill ids. Patch drafts are persisted but never applied.
        """
        reflections = self.reflect_and_remember(situation_text, decisions, returns, memories)
        patches = {}
        try:
            from stocker.evolution.adapters.stocker_reviewer import StockerEvolutionReviewer
            reviewer = StockerEvolutionReviewer()
            for component, reflection in reflections.items():
                target = skill_targets.get(component)
                if not target:
                    continue
                patch = reviewer.propose_patch_from_reflection(
                    target_skill_id=target,
                    reflection=str(reflection),
                    reason=f"Post-run reflection for {component}",
                    evidence_trace_ids=[],
                    risk_level="high" if component in {"trader", "portfolio_manager"} else "medium",
                )
                if patch is not None:
                    patches[component] = patch.model_dump(mode="json")
        except Exception as e:
            logger.error("Evolution patch proposal failed: %s", e)
        return {"reflections": reflections, "patches": patches}

