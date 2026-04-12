"""Scheduler: APScheduler AsyncIOScheduler wrapper for periodic tasks."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Coroutine

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


class StockerScheduler:
    """Wraps APScheduler for stocker's periodic tasks."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._jobs: dict[str, str] = {}  # name -> job_id

    # ------------------------------------------------------------------
    # Job registration
    # ------------------------------------------------------------------

    def add_cron_job(
        self,
        name: str,
        func: Callable[..., Coroutine[Any, Any, None]],
        cron_expr: str,
        **kwargs: Any,
    ) -> None:
        """Add a cron-triggered async job.

        cron_expr format: "minute hour day month day_of_week"
        e.g. "0 9 * * 1-5" = 09:00 Mon-Fri
        """
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression (need 5 fields): {cron_expr}")

        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )
        job = self._scheduler.add_job(func, trigger, id=name, name=name, **kwargs)
        self._jobs[name] = job.id
        logger.info("Added cron job '%s': %s", name, cron_expr)

    def add_interval_job(
        self,
        name: str,
        func: Callable[..., Coroutine[Any, Any, None]],
        minutes: int = 5,
        **kwargs: Any,
    ) -> None:
        """Add an interval-triggered async job."""
        trigger = IntervalTrigger(minutes=minutes)
        job = self._scheduler.add_job(func, trigger, id=name, name=name, **kwargs)
        self._jobs[name] = job.id
        logger.info("Added interval job '%s': every %d min", name, minutes)

    def remove_job(self, name: str) -> None:
        """Remove a job by name."""
        job_id = self._jobs.pop(name, None)
        if job_id:
            self._scheduler.remove_job(job_id)
            logger.info("Removed job '%s'", name)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the scheduler."""
        self._scheduler.start()
        logger.info("Scheduler started with %d jobs", len(self._jobs))

    def shutdown(self) -> None:
        """Shutdown the scheduler gracefully."""
        self._scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return scheduler status for Supervisor status query."""
        jobs_info = []
        for job in self._scheduler.get_jobs():
            next_run = job.next_run_time
            jobs_info.append({
                "name": job.name,
                "next_run": next_run.isoformat() if next_run else None,
                "trigger": str(job.trigger),
            })
        return {
            "running": self._scheduler.running,
            "job_count": len(jobs_info),
            "jobs": jobs_info,
            "checked_at": datetime.now().isoformat(),
        }
