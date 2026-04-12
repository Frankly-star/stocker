"""PortfolioScanner: batch analysis of all positions for swing trading suggestions."""

from __future__ import annotations

import logging
from typing import Any

from stocker.portfolio.store import PositionStore

logger = logging.getLogger(__name__)


class PortfolioScanner:
    """Scans all positions through the analysis pipeline."""

    def __init__(self, store: PositionStore) -> None:
        self._store = store

    async def scan_all(self, analyze_func: Any = None) -> list[dict]:
        """Scan all positions and generate swing trading suggestions.

        Args:
            analyze_func: Async callable(ticker) -> analysis result.
                          Will be wired to Supervisor's run_intelligence + run_risk_assessment.

        Returns:
            List of per-position analysis summaries.
        """
        positions = self._store.list_all()
        if not positions:
            return [{"message": "No positions to scan"}]

        results = []
        for pos in positions:
            logger.info("Scanning %s (%d shares @ $%.2f)", pos.ticker, pos.quantity, pos.avg_cost)
            if analyze_func:
                try:
                    analysis = await analyze_func(pos.ticker)
                    results.append({
                        "ticker": pos.ticker,
                        "quantity": pos.quantity,
                        "avg_cost": pos.avg_cost,
                        "analysis": analysis,
                    })
                except Exception as e:
                    results.append({
                        "ticker": pos.ticker,
                        "error": str(e),
                    })
            else:
                results.append({
                    "ticker": pos.ticker,
                    "quantity": pos.quantity,
                    "avg_cost": pos.avg_cost,
                    "analysis": "No analyze_func provided",
                })

        return results
