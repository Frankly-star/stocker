"""StockerService: the main backend service orchestrating Scheduler, EventBus, and FastAPI."""

from __future__ import annotations

import asyncio
import logging
import signal
import threading
from typing import Any

import uvicorn

from stocker.engine.events import EventBus
from stocker.engine.scheduler import StockerScheduler

logger = logging.getLogger(__name__)


class StockerService:
    """Main service: manages Scheduler + EventBus + FastAPI in a single asyncio loop."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.scheduler = StockerScheduler()
        self.event_bus = EventBus()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event = asyncio.Event()
        self._api_thread: threading.Thread | None = None

        # Futu runtime & broker (created during startup if broker_type=futu)
        self.runtime: Any = None
        self.broker: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _start_async(self) -> None:
        """Async startup sequence."""
        logger.info("Starting StockerService...")

        # 1. Start EventBus
        await self.event_bus.start()

        # 2. Start FutuRuntime (default broker)
        if self.config.get("broker_type", "futu") != "simulated":
            try:
                from stocker.integrations.futu.config import FutuConfig
                from stocker.engine.runtime import FutuRuntime

                futu_config = FutuConfig.from_stocker_config(self.config)
                self.runtime = FutuRuntime(futu_config)
                self.runtime.start()
                logger.info("FutuRuntime started via StockerService")
            except Exception as e:
                logger.warning("Failed to start FutuRuntime in service: %s", e)
                self.runtime = None

        # 3. Create broker
        try:
            from stocker.broker.factory import create_broker

            self.broker = create_broker(self.config, runtime=self.runtime)
        except Exception as e:
            logger.warning("Failed to create broker in service: %s", e)

        # 4. Start Scheduler
        self._register_scheduled_tasks()
        self.scheduler.start()

        # 5. Start FastAPI in a separate thread
        self._start_api_server()

        logger.info("StockerService is running. Press Ctrl+C to stop.")

        # Block until stop signal
        await self._stop_event.wait()

    async def _stop_async(self) -> None:
        """Async shutdown sequence."""
        logger.info("Stopping StockerService...")

        # 1. Stop Scheduler
        self.scheduler.shutdown()

        # 2. Stop FutuRuntime
        if self.runtime is not None:
            try:
                self.runtime.stop()
                logger.info("FutuRuntime stopped via StockerService")
            except Exception as e:
                logger.warning("Error stopping FutuRuntime: %s", e)

        # 3. Stop EventBus
        await self.event_bus.stop()

        logger.info("StockerService stopped.")

    def start(self) -> None:
        """Start the service (blocking)."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        # Register signal handlers for graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self._loop.add_signal_handler(sig, self._handle_signal)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler for SIGTERM
                signal.signal(sig, lambda s, f: self._handle_signal())

        try:
            self._loop.run_until_complete(self._start_async())
        finally:
            self._loop.run_until_complete(self._stop_async())
            self._loop.close()

    def stop(self) -> None:
        """Signal the service to stop."""
        self._stop_event.set()

    def _handle_signal(self) -> None:
        """Handle SIGINT/SIGTERM for graceful shutdown."""
        logger.info("Received shutdown signal")
        self.stop()

    # ------------------------------------------------------------------
    # Scheduled tasks registration
    # ------------------------------------------------------------------

    def _register_scheduled_tasks(self) -> None:
        """Register default scheduled tasks from config."""
        scan_cron = self.config.get("scan_cron", "0 9 * * 1-5")
        report_cron = self.config.get("report_cron", "0 16 * * 1-5")
        reflect_cron = self.config.get("reflect_cron", "30 16 * * 1-5")
        sync_interval = int(self.config.get("sync_interval_minutes", 5))

        self.scheduler.add_cron_job("portfolio_scan", self._task_portfolio_scan, scan_cron)
        self.scheduler.add_cron_job("daily_report", self._task_daily_report, report_cron)
        self.scheduler.add_cron_job("reflect", self._task_reflect, reflect_cron)
        self.scheduler.add_interval_job("broker_sync", self._task_broker_sync, sync_interval)

    # ------------------------------------------------------------------
    # Task stubs (will be wired to graph invocations)
    # ------------------------------------------------------------------

    async def _task_portfolio_scan(self) -> None:
        """Scheduled: scan all positions through intelligence + risk pipeline."""
        logger.info("[Scheduled] Portfolio scan triggered")
        # Will be wired to: Supervisor.run("scheduled: scan portfolio")

    async def _task_broker_sync(self) -> None:
        """Scheduled: sync positions from broker."""
        logger.info("[Scheduled] Broker sync triggered")
        if self.broker is not None:
            try:
                positions = await self.broker.sync_positions()
                if positions:
                    from stocker.portfolio.store import PositionStore

                    store = PositionStore()
                    result = store.sync_from_broker(positions)
                    logger.info("[Scheduled] Broker sync complete: %s", result)
                else:
                    logger.debug("[Scheduled] Broker sync: no positions returned")
            except Exception as e:
                logger.warning("[Scheduled] Broker sync failed: %s", e)

    async def _task_daily_report(self) -> None:
        """Scheduled: generate daily report."""
        logger.info("[Scheduled] Daily report triggered")

    async def _task_reflect(self) -> None:
        """Scheduled: trigger reflection on today's trades."""
        logger.info("[Scheduled] Reflection triggered")

    # ------------------------------------------------------------------
    # Embedded FastAPI
    # ------------------------------------------------------------------

    def _start_api_server(self) -> None:
        """Start FastAPI/uvicorn in a daemon thread."""
        host = self.config.get("api_host", "0.0.0.0")
        port = int(self.config.get("api_port", 8000))

        def _run() -> None:
            from stocker.api.app import create_app
            app = create_app(self)
            uvicorn.run(app, host=host, port=port, log_level="info")

        self._api_thread = threading.Thread(target=_run, daemon=True, name="stocker-api")
        self._api_thread.start()
        logger.info("FastAPI server started on %s:%d", host, port)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Get service status for Supervisor queries."""
        status = {
            "service": "running",
            "scheduler": self.scheduler.get_status(),
            "execution_mode": self.config.get("execution_mode", "observe"),
            "broker_type": self.config.get("broker_type", "simulated"),
        }

        if self.broker is not None:
            status["broker_name"] = self.broker.broker_name

        if self.runtime is not None:
            status["futu_runtime"] = self.runtime.get_runtime_status()

        return status
