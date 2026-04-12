"""EventBus: asyncio pub/sub for inter-component communication."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event definitions
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """Base event class."""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TradeSignalEvent(Event):
    """Emitted when analysis produces a trade signal."""
    ticker: str = ""
    rating: str = ""          # BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL
    confidence: float = 0.0
    suggested_action: str = ""
    position_size_pct: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_level: str = ""
    source: str = ""          # "scheduled" / "manual" / "api"


@dataclass
class TradeExecutedEvent(Event):
    """Emitted after a trade is executed through the broker."""
    ticker: str = ""
    action: str = ""          # "buy" / "sell"
    quantity: int = 0
    price: float = 0.0
    order_id: str = ""
    broker: str = ""
    success: bool = True
    error: str | None = None


@dataclass
class PositionUpdateEvent(Event):
    """Emitted when positions are updated (sync/trade/manual)."""
    ticker: str = ""
    source: str = ""          # "broker_synced" / "trade" / "manual_import"
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisCompleteEvent(Event):
    """Emitted when data intelligence analysis completes."""
    ticker: str = ""
    market_environment: str = ""
    cached: bool = False


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

EventHandler = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    """Simple asyncio-based pub/sub event bus."""

    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[EventHandler]] = {}
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running = False
        self._task: asyncio.Task | None = None

    def subscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        """Register a handler for an event type."""
        self._handlers.setdefault(event_type, []).append(handler)
        logger.debug("Subscribed %s to %s", handler.__name__, event_type.__name__)

    def unsubscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        """Remove a handler for an event type."""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        """Publish an event to the bus (non-blocking)."""
        await self._queue.put(event)
        logger.info("Published %s for %s", type(event).__name__, getattr(event, "ticker", ""))

    async def _process_events(self) -> None:
        """Main loop: dequeue events and dispatch to handlers."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            event_type = type(event)
            handlers = self._handlers.get(event_type, [])
            for handler in handlers:
                try:
                    await handler(event)
                except Exception:
                    logger.exception(
                        "Error in handler %s for %s", handler.__name__, event_type.__name__
                    )

    async def start(self) -> None:
        """Start the event processing loop."""
        self._running = True
        self._task = asyncio.create_task(self._process_events())
        logger.info("EventBus started")

    async def stop(self) -> None:
        """Stop the event processing loop gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("EventBus stopped")
