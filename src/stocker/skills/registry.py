"""SkillRegistry: singleton that manages all skill adapters."""

from __future__ import annotations

import logging
from typing import Any

from stocker.skills.base import SkillAdapter, SkillManifest

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Central registry for all Skill adapters. Supports auto-discovery."""

    _instance: SkillRegistry | None = None

    def __init__(self) -> None:
        self._skills: dict[str, SkillAdapter] = {}

    @classmethod
    def get_instance(cls) -> SkillRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, adapter: SkillAdapter) -> None:
        """Register a skill adapter."""
        self._skills[adapter.name] = adapter
        logger.info("Registered skill: %s", adapter.name)

    def get(self, name: str) -> SkillAdapter | None:
        return self._skills.get(name)

    def list_manifests(self) -> list[SkillManifest]:
        """Return lightweight manifests for all registered skills."""
        return [s.get_manifest() for s in self._skills.values()]

    def list_names(self) -> list[str]:
        return list(self._skills.keys())

    def discover_and_register(self) -> None:
        """Auto-discover and register built-in skill adapters."""
        try:
            from stocker.skills.stock_market_pro import StockMarketProSkill
            self.register(StockMarketProSkill())
        except ImportError:
            logger.debug("stock-market-pro skill not available")

        try:
            from stocker.skills.finance_news import FinanceNewsSkill
            self.register(FinanceNewsSkill())
        except ImportError:
            logger.debug("finance-news skill not available")

        try:
            from stocker.skills.tencent_finance import TencentFinanceSkill
            self.register(TencentFinanceSkill())
        except ImportError:
            logger.debug("tencent-finance skill not available")

        try:
            from stocker.skills.westock_data import WeStockDataSkill
            self.register(WeStockDataSkill())
        except ImportError:
            logger.debug("westock-data skill not available")

        try:
            from stocker.skills.trading_agents import TradingAgentsSkill
            self.register(TradingAgentsSkill())
        except (ImportError, Exception) as e:
            logger.debug("trading-agents skill not available: %s", e)

        try:
            from stocker.skills.self_improving import SelfImprovingSkill
            self.register(SelfImprovingSkill())
        except ImportError:
            logger.debug("self-improving skill not available")

        logger.info("Discovered %d skills: %s", len(self._skills), self.list_names())

    def get_manifests_text(self) -> str:
        """Generate a text summary of all skills for injection into system prompts."""
        manifests = self.list_manifests()
        if not manifests:
            return "No skills available."
        lines = ["Available Skills (use load_skill to load):"]
        for m in manifests:
            caps = f" (capabilities: {', '.join(m.sub_capabilities)})" if m.sub_capabilities else ""
            lines.append(f"  - {m.name}: {m.description}{caps}")
        return "\n".join(lines)
