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
    "monitoring_enabled": True,
    "monitoring_interval_seconds": 300,
    "monitoring_running": False,
    "monitoring_in_cycle": False,
    "monitoring_last_started_at": None,
    "monitoring_last_completed_at": None,
    "monitoring_last_error": None,
    "monitoring_cycle_count": 0,
    "monitoring_last_summary": {},
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


def get_monitoring_enabled() -> bool:
    return bool(_state.get("monitoring_enabled", True))


def set_monitoring_enabled(enabled: bool) -> None:
    _state["monitoring_enabled"] = enabled


def get_monitoring_interval_seconds() -> int:
    return int(_state.get("monitoring_interval_seconds", 300))


def set_monitoring_interval_seconds(seconds: int) -> None:
    _state["monitoring_interval_seconds"] = max(5, int(seconds))


def set_monitoring_running(running: bool) -> None:
    _state["monitoring_running"] = running


def mark_monitoring_cycle_started() -> None:
    from datetime import datetime

    _state["monitoring_in_cycle"] = True
    _state["monitoring_last_started_at"] = datetime.now().isoformat()
    _state["monitoring_last_error"] = None


def mark_monitoring_cycle_completed(summary: dict | None = None) -> None:
    from datetime import datetime

    _state["monitoring_in_cycle"] = False
    _state["monitoring_last_completed_at"] = datetime.now().isoformat()
    _state["monitoring_cycle_count"] = int(_state.get("monitoring_cycle_count", 0)) + 1
    _state["monitoring_last_summary"] = summary or {}
    _state["monitoring_last_error"] = None


def mark_monitoring_cycle_failed(error: str) -> None:
    from datetime import datetime

    _state["monitoring_in_cycle"] = False
    _state["monitoring_last_completed_at"] = datetime.now().isoformat()
    _state["monitoring_cycle_count"] = int(_state.get("monitoring_cycle_count", 0)) + 1
    _state["monitoring_last_error"] = error


def get_monitoring_status() -> dict:
    return {
        "enabled": get_monitoring_enabled(),
        "running": bool(_state.get("monitoring_running", False)),
        "in_cycle": bool(_state.get("monitoring_in_cycle", False)),
        "interval_seconds": get_monitoring_interval_seconds(),
        "last_started_at": _state.get("monitoring_last_started_at"),
        "last_completed_at": _state.get("monitoring_last_completed_at"),
        "last_error": _state.get("monitoring_last_error"),
        "cycle_count": int(_state.get("monitoring_cycle_count", 0)),
        "last_summary": _state.get("monitoring_last_summary", {}),
    }

