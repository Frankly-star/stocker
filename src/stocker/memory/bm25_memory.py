"""BM25 Memory system with JSON persistence. Extracted from TradingAgents memory.py.

Enhancements over original:
- JSON persistence to data/memory/ directory
- Per-ticker partitioning
- Capacity limit with auto-eviction
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from stocker.utils.helpers import atomic_json_write, json_read

logger = logging.getLogger(__name__)

MAX_MEMORIES = 500  # per collection


class BM25Memory:
    """Financial situation memory using BM25 for lexical similarity matching."""

    def __init__(self, name: str, persist_dir: str = "data/memory") -> None:
        self.name = name
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._filepath = self._persist_dir / f"{name}.json"

        self.documents: list[str] = []
        self.recommendations: list[str] = []
        self.bm25: BM25Okapi | None = None

        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        data = json_read(self._filepath, default={"documents": [], "recommendations": []})
        self.documents = data.get("documents", [])
        self.recommendations = data.get("recommendations", [])
        self._rebuild_index()

    def _save(self) -> None:
        atomic_json_write(self._filepath, {
            "documents": self.documents,
            "recommendations": self.recommendations,
        })

    # ------------------------------------------------------------------
    # BM25 index
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"\b\w+\b", text.lower())

    def _rebuild_index(self) -> None:
        if self.documents:
            tokenized = [self._tokenize(d) for d in self.documents]
            self.bm25 = BM25Okapi(tokenized)
        else:
            self.bm25 = None

    # ------------------------------------------------------------------
    # Core API (compatible with TradingAgents FinancialSituationMemory)
    # ------------------------------------------------------------------

    def add_situations(self, situations_and_advice: list[tuple[str, str]]) -> None:
        """Add financial situations and their corresponding advice."""
        for situation, recommendation in situations_and_advice:
            self.documents.append(situation)
            self.recommendations.append(recommendation)

        # Auto-evict oldest if over capacity
        while len(self.documents) > MAX_MEMORIES:
            self.documents.pop(0)
            self.recommendations.pop(0)

        self._rebuild_index()
        self._save()

    def get_memories(self, current_situation: str, n_matches: int = 1) -> list[dict]:
        """Find matching recommendations using BM25 similarity."""
        if not self.documents or self.bm25 is None:
            return []

        query_tokens = self._tokenize(current_situation)
        scores = self.bm25.get_scores(query_tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:n_matches]

        max_score = max(scores) if len(scores) > 0 and max(scores) > 0 else 1
        results = []
        for idx in top_indices:
            results.append({
                "matched_situation": self.documents[idx],
                "recommendation": self.recommendations[idx],
                "similarity_score": scores[idx] / max_score if max_score > 0 else 0,
            })
        return results

    def clear(self) -> None:
        self.documents = []
        self.recommendations = []
        self.bm25 = None
        self._save()

    @property
    def size(self) -> int:
        return len(self.documents)
