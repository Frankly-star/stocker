"""Skill adapter for self-improving: memory management and reflection."""

from __future__ import annotations

from langchain_core.tools import tool

from stocker.skills.base import SkillAdapter, SkillManifest


class SelfImprovingSkill(SkillAdapter):

    @property
    def name(self) -> str:
        return "self-improving"

    @property
    def description(self) -> str:
        return "Agent self-reflection, learning, and BM25-based trading memory retrieval"

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name=self.name,
            description=self.description,
            sub_capabilities=["reflect", "remember", "query_memory", "stats"],
            version="1.2.16",
        )

    def load(self) -> dict:
        prompt = (
            "You have access to self-improving trading memory.\n"
            "Use query_trading_memory to retrieve past trading lessons and reflections.\n"
            "The system stores Bull/Bear/Trader/Manager reflections via BM25 similarity.\n"
        )

        @tool
        def query_trading_memory(query: str, n_results: int = 3) -> str:
            """Search trading memory for relevant past experiences, lessons, and reflections.
            Returns the most similar past situations and their recommendations."""
            from stocker.memory.bm25_memory import BM25Memory

            all_results = []
            for role in ["bull", "bear", "trader", "manager", "portfolio_manager"]:
                try:
                    mem = BM25Memory(role)
                    results = mem.get_memories(query, n_matches=n_results)
                    for r in results:
                        r["role"] = role
                        all_results.append(r)
                except Exception:
                    continue

            if not all_results:
                return "No trading memories found. The system will accumulate memories as you trade and reflect."

            # Sort by similarity score, take top N
            all_results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
            top = all_results[:n_results]

            lines = [f"## Trading Memory: {len(top)} relevant experiences\n"]
            for i, r in enumerate(top, 1):
                score = r.get("similarity_score", 0)
                role = r.get("role", "unknown")
                lines.append(f"### {i}. [{role}] (similarity: {score:.2f})")
                lines.append(f"**Situation**: {r.get('matched_situation', '')[:200]}...")
                lines.append(f"**Recommendation**: {r.get('recommendation', '')[:300]}")
                lines.append("")
            return "\n".join(lines)

        return {"prompt": prompt, "tools": [query_trading_memory]}
