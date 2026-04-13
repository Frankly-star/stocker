"""Shared runtime state: singleton dict accessible by routes, supervisor tools, and service.

When running via `runserver.py` (no StockerService), this module provides a
process-global store so that `/execution-mode` changes are visible to the
Supervisor's `get_system_status` tool and the `/trade` endpoint.
"""

from __future__ import annotations

_state: dict[str, object] = {
    "execution_mode": "observe",
    "auto_pilot": False,
    "auto_pilot_interval_minutes": 60,  # how often the auto-pilot cycle runs
}


def get_execution_mode() -> str:
    return str(_state["execution_mode"])


def set_execution_mode(mode: str) -> None:
    _state["execution_mode"] = mode


def get_auto_pilot() -> bool:
    return bool(_state.get("auto_pilot", False))


def set_auto_pilot(enabled: bool) -> None:
    _state["auto_pilot"] = enabled


def get_auto_pilot_interval() -> int:
    return int(_state.get("auto_pilot_interval_minutes", 60))


def set_auto_pilot_interval(minutes: int) -> None:
    _state["auto_pilot_interval_minutes"] = max(5, minutes)
