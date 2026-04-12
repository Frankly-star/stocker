"""Shared runtime state: singleton dict accessible by routes, supervisor tools, and service.

When running via `runserver.py` (no StockerService), this module provides a
process-global store so that `/execution-mode` changes are visible to the
Supervisor's `get_system_status` tool and the `/trade` endpoint.
"""

from __future__ import annotations

_state: dict[str, str] = {
    "execution_mode": "observe",
}


def get_execution_mode() -> str:
    return _state["execution_mode"]


def set_execution_mode(mode: str) -> None:
    _state["execution_mode"] = mode
