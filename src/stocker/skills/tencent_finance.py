"""Skill adapter for tencent-finance: China mainland direct access."""

from __future__ import annotations

from langchain_core.tools import tool

from stocker.skills.base import SkillAdapter, SkillManifest


class TencentFinanceSkill(SkillAdapter):

    @property
    def name(self) -> str:
        return "tencent-finance"

    @property
    def description(self) -> str:
        return "Tencent Finance API: real-time quotes for A-shares, HK stocks, US stocks. No API key needed, China mainland direct."

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name=self.name,
            description=self.description,
            sub_capabilities=["price", "quote", "compare", "search"],
            version="1.0.0",
        )

    def load(self) -> dict:
        prompt = (
            "You have access to tencent-finance for China-accessible stock data.\n"
            "Use tfin_quote for real-time quotes of A-shares, HK, or US stocks."
        )

        @tool
        def tfin_quote(symbol: str) -> str:
            """Get stock quote from Tencent Finance. Supports A-shares (e.g. 000001), HK (e.g. 00700), US (e.g. AAPL)."""
            # Placeholder: will call tencent-finance Skill's actual script
            return f"[tencent-finance] Quote for {symbol}: placeholder — integrate with skills/tencent-finance script"

        return {"prompt": prompt, "tools": [tfin_quote]}
