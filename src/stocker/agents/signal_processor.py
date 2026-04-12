"""SignalProcessor: extract structured trading signals from risk assessment output.

Enhanced from TradingAgents: outputs confidence, position size, stop/take profit.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from stocker.analysis.models import RiskAssessmentResult

logger = logging.getLogger(__name__)

SIGNAL_EXTRACTION_PROMPT = """Extract a structured trading decision from the portfolio manager's analysis.

Output ONLY valid JSON with these fields:
{
    "rating": "BUY" or "OVERWEIGHT" or "HOLD" or "UNDERWEIGHT" or "SELL",
    "confidence": 0.0 to 1.0,
    "suggested_action": "specific action description",
    "position_size_pct": 0.0 to 100.0,
    "stop_loss": price or null,
    "take_profit": price or null,
    "risk_level": "LOW" or "MEDIUM" or "HIGH",
    "key_reasons": ["reason1", "reason2", "reason3"],
    "investment_thesis": "one paragraph summary"
}"""


class SignalProcessor:
    """Processes trading signals to extract structured decisions."""

    def __init__(self, llm: Any) -> None:
        self._llm = llm

    def process_signal(self, full_signal: str, ticker: str = "") -> RiskAssessmentResult:
        """Extract structured RiskAssessmentResult from full analysis text."""
        messages = [
            ("system", SIGNAL_EXTRACTION_PROMPT),
            ("human", full_signal),
        ]

        try:
            response = self._llm.invoke(messages).content

            # Try to parse JSON from the response
            json_str = response.strip()
            if json_str.startswith("```"):
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]

            data = json.loads(json_str)
            data["ticker"] = ticker
            return RiskAssessmentResult(**data)

        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Failed to parse signal JSON, falling back to simple extraction: %s", e)
            # Fallback: simple rating extraction
            rating = self._extract_simple_rating(full_signal)
            return RiskAssessmentResult(
                ticker=ticker,
                rating=rating,
                confidence=0.5,
                suggested_action=f"{rating} based on analysis",
                investment_thesis=full_signal[:500],
            )

    def _extract_simple_rating(self, text: str) -> str:
        """Extract simple rating from text as fallback."""
        messages = [
            ("system", "Extract the trading decision. Output exactly one of: BUY, OVERWEIGHT, HOLD, UNDERWEIGHT, SELL"),
            ("human", text),
        ]
        try:
            result = self._llm.invoke(messages).content.strip().upper()
            valid = {"BUY", "OVERWEIGHT", "HOLD", "UNDERWEIGHT", "SELL"}
            return result if result in valid else "HOLD"
        except Exception:
            return "HOLD"
