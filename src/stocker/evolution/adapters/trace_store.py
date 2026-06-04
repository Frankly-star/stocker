"""Append-only trace store for Stocker evolution evidence."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from stocker.evolution.models import NodeTrace
from stocker.evolution.paths import traces_root

logger = logging.getLogger(__name__)
_MAX_TEXT = 1200


def summarize_text(value: Any, max_chars: int = _MAX_TEXT) -> str:
    text = str(value or "").strip()
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + " ...[truncated]"


class TraceStore:
    """JSONL store for node traces. Write failures are non-fatal."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else traces_root()

    def record_node_run(self, trace: NodeTrace) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        day = datetime.now().strftime("%Y%m%d")
        path = self.root / f"{day}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(trace.model_dump(mode="json"), ensure_ascii=False) + "\n")

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*.jsonl"), reverse=True):
            for line in reversed(path.read_text(encoding="utf-8").splitlines()):
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(rows) >= limit:
                    return rows
        return rows


def record_node_trace(
    *,
    team: str,
    node: str,
    state: dict | None,
    input_text: Any,
    output_text: Any,
    resolved_prompt: Any = None,
    duration_ms: int = 0,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Best-effort trace writer used from LangGraph nodes."""
    try:
        state = state or {}
        shared = state.get("shared_data") or {}
        warnings = shared.get("data_warnings") or state.get("data_warnings") or []
        graph_run_id = state.get("graph_run_id") or state.get("_graph_run_id") or "default"
        trace = NodeTrace(
            graph_run_id=str(graph_run_id),
            team=team,
            node=node,
            ticker=state.get("ticker"),
            trade_date=state.get("trade_date"),
            skill_id=getattr(resolved_prompt, "skill_id", None),
            skill_version=getattr(resolved_prompt, "skill_version", None),
            prompt_hash=getattr(resolved_prompt, "prompt_hash", None),
            input_summary=summarize_text(input_text),
            output_summary=summarize_text(output_text),
            data_warnings=list(warnings) if isinstance(warnings, list) else [str(warnings)],
            duration_ms=duration_ms,
            error=error,
            metadata=metadata or {},
        )
        TraceStore().record_node_run(trace)
    except Exception as exc:
        logger.warning("Evolution trace write failed for %s/%s: %s", team, node, exc)
