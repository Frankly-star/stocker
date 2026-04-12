"""FutuRuntime: unified lifecycle manager for Futu Open API connections.

Manages:
- OpenQuoteContext & OpenSecTradeContext via FutuQuoteClient / FutuTradeClient
- Subscription tracking (dedup, subscribe, unsubscribe)
- Callback handler registration and thread-safe data cache
- Account discovery and trade unlock
- Connection status and runtime status reporting
- Graceful start / stop with retry on initial connect
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from stocker.integrations.futu.config import FutuConfig
from stocker.integrations.futu.handlers import (
    KlineHandler,
    OrderBookHandler,
    QuoteHandler,
    TickerHandler,
)
from stocker.integrations.futu.quote_client import FutuQuoteClient
from stocker.integrations.futu.trade_client import FutuTradeClient

logger = logging.getLogger(__name__)

# Module-level reference so DataFetcher can access it without DI plumbing.
_active_runtime: FutuRuntime | None = None


def get_active_runtime() -> FutuRuntime | None:
    """Return the currently active FutuRuntime, if any."""
    return _active_runtime


class FutuRuntime:
    """Unified runtime for the Futu Open API integration."""

    MAX_CONNECT_RETRIES = 3
    RETRY_BASE_DELAY = 2  # seconds

    def __init__(self, config: FutuConfig) -> None:
        self._config = config

        # Clients
        self._quote_client: FutuQuoteClient | None = None
        self._trade_client: FutuTradeClient | None = None

        # Thread-safe cache for callback data
        self._cache: dict[str, Any] = {}
        self._lock = threading.Lock()

        # Subscription tracking: set of (code, SubType)
        self._subscriptions: set[tuple[str, Any]] = set()

        # Handlers
        self._quote_handler: QuoteHandler | None = None
        self._kline_handler: KlineHandler | None = None
        self._ticker_handler: TickerHandler | None = None
        self._orderbook_handler: OrderBookHandler | None = None

        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start quote and trade connections, discover accounts, unlock trade, subscribe defaults.

        Automatically ensures OpenD is running before attempting to connect.
        If OpenD is not found locally, it will be downloaded and started.
        """
        global _active_runtime

        if self._started:
            logger.warning("FutuRuntime.start() called but already started")
            return

        # --- Ensure OpenD is running ---
        try:
            from stocker.integrations.futu.opend_manager import ensure_opend, wait_for_login

            opend_ok = ensure_opend(
                host=self._config.host,
                port=self._config.port,
            )
            if not opend_ok:
                logger.error(
                    "OpenD is not reachable at %s:%d — "
                    "FutuRuntime will attempt connection anyway, but it may fail",
                    self._config.host, self._config.port,
                )
            else:
                # OpenD is running — check if user is logged in
                login_ok = wait_for_login(
                    host=self._config.host,
                    port=self._config.port,
                    timeout=300,  # 5 minutes
                    poll_interval=5,
                )
                if not login_ok:
                    logger.warning(
                        "OpenD not logged in — connection will likely fail. "
                        "System will fall back to SimulatedBroker."
                    )
                    return  # Don't try to connect, let factory fall back
        except Exception as e:
            logger.warning("OpenD auto-start check failed: %s — continuing anyway", e)

        # --- Quote ---
        if self._config.quote_enabled:
            self._quote_client = FutuQuoteClient(self._config)
            self._connect_with_retry(self._quote_client.connect, "QuoteClient")
            if self._quote_client.connected:
                self._register_handlers()

        # --- Trade ---
        self._trade_client = FutuTradeClient(self._config)
        self._connect_with_retry(self._trade_client.connect, "TradeClient")

        if self._trade_client.connected:
            self._trade_client.discover_accounts()
            # Unlock trade (password may be empty for simulate)
            self._trade_client.unlock_trade()

        # --- Default subscriptions ---
        if self._config.subscribe_codes and self._quote_client and self._quote_client.connected:
            try:
                from futu import SubType

                default_subtypes = [SubType.QUOTE, SubType.K_DAY]
                self.subscribe(self._config.subscribe_codes, default_subtypes)
            except ImportError:
                logger.debug("futu not available for default subscriptions")

        self._started = True
        _active_runtime = self
        logger.info("FutuRuntime started (quote=%s, trade=%s)",
                     self._quote_client.connected if self._quote_client else False,
                     self._trade_client.connected if self._trade_client else False)

    def stop(self) -> None:
        """Close all connections and clean up."""
        global _active_runtime

        if not self._started:
            return

        # Unsubscribe all
        if self._quote_client and self._quote_client.connected and self._subscriptions:
            try:
                codes = list({code for code, _ in self._subscriptions})
                subtypes = list({st for _, st in self._subscriptions})
                self._quote_client.unsubscribe(codes, subtypes)
            except Exception as e:
                logger.debug("Error during unsubscribe-all: %s", e)

        if self._quote_client:
            self._quote_client.close()
        if self._trade_client:
            self._trade_client.close()

        self._subscriptions.clear()
        with self._lock:
            self._cache.clear()

        self._started = False
        if _active_runtime is self:
            _active_runtime = None

        # Stop managed OpenD process if we started it
        try:
            from stocker.integrations.futu.opend_manager import stop_opend
            stop_opend()
        except Exception:
            pass

        logger.info("FutuRuntime stopped")

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def subscribe(self, codes: list[str], subtypes: list) -> bool:
        """Subscribe to *codes* x *subtypes*, deduplicating against current subscriptions."""
        if not self._quote_client or not self._quote_client.connected:
            logger.warning("Cannot subscribe: quote client not connected")
            return False

        # Filter out already-subscribed pairs
        new_pairs = set()
        for code in codes:
            for st in subtypes:
                pair = (code, st)
                if pair not in self._subscriptions:
                    new_pairs.add(pair)

        if not new_pairs:
            logger.debug("All requested subscriptions already active")
            return True

        # Group by subtype for batch subscribe
        new_codes = list({code for code, _ in new_pairs})
        new_subtypes = list({st for _, st in new_pairs})

        ok = self._quote_client.subscribe(new_codes, new_subtypes)
        if ok:
            self._subscriptions.update(new_pairs)
        return ok

    def unsubscribe(self, codes: list[str], subtypes: list) -> bool:
        """Unsubscribe from *codes* x *subtypes*."""
        if not self._quote_client or not self._quote_client.connected:
            return False

        ok = self._quote_client.unsubscribe(codes, subtypes)
        if ok:
            for code in codes:
                for st in subtypes:
                    self._subscriptions.discard((code, st))
        return ok

    # ------------------------------------------------------------------
    # Data access (read from cache or pull)
    # ------------------------------------------------------------------

    def get_cached_quote(self, code: str) -> dict | None:
        """Get latest cached quote for *code* (from callback push)."""
        with self._lock:
            return self._cache.get("quote", {}).get(code)

    def get_snapshot(self, code: str) -> dict | None:
        """Pull a fresh market snapshot for a single code."""
        if not self._quote_client or not self._quote_client.connected:
            return None
        results = self._quote_client.get_market_snapshot([code])
        return results[0] if results else None

    def get_kline(self, code: str, ktype: str = "K_DAY", count: int = 120) -> list[dict]:
        """Pull K-line bars for *code*.

        Args:
            code: Futu format code (e.g. ``"HK.00700"``).
            ktype: K-line type string (``"K_DAY"``, ``"K_60M"``, etc.).
            count: Number of bars.

        Returns:
            List of bar dicts, or empty list.
        """
        if not self._quote_client or not self._quote_client.connected:
            return []

        try:
            from futu import KLType

            ktype_map = {
                "K_1M": KLType.K_1M,
                "K_5M": KLType.K_5M,
                "K_15M": KLType.K_15M,
                "K_30M": KLType.K_30M,
                "K_60M": KLType.K_60M,
                "K_DAY": KLType.K_DAY,
                "K_WEEK": KLType.K_WEEK,
                "K_MON": KLType.K_MON,
            }
            kl = ktype_map.get(ktype.upper(), KLType.K_DAY)
        except ImportError:
            return []

        return self._quote_client.get_cur_kline(code, kl, count)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_runtime_status(self) -> dict:
        """Return a status dict for API / CLI consumption."""
        return {
            "started": self._started,
            "quote_connected": self._quote_client.connected if self._quote_client else False,
            "trade_connected": self._trade_client.connected if self._trade_client else False,
            "trade_unlocked": self._trade_client.unlocked if self._trade_client else False,
            "acc_id": self._trade_client.acc_id if self._trade_client else None,
            "trd_env": self._config.trd_env,
            "market": self._config.market,
            "subscriptions_count": len(self._subscriptions),
            "cache_keys": list(self._cache.keys()),
        }

    @property
    def quote_client(self) -> FutuQuoteClient | None:
        return self._quote_client

    @property
    def trade_client(self) -> FutuTradeClient | None:
        return self._trade_client

    @property
    def config(self) -> FutuConfig:
        return self._config

    @property
    def started(self) -> bool:
        return self._started

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect_with_retry(self, connect_fn, label: str) -> None:
        """Attempt connection with exponential back-off."""
        for attempt in range(1, self.MAX_CONNECT_RETRIES + 1):
            try:
                connect_fn()
                return
            except Exception as e:
                delay = self.RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "%s connect attempt %d/%d failed: %s — retrying in %ds",
                    label, attempt, self.MAX_CONNECT_RETRIES, e, delay,
                )
                if attempt < self.MAX_CONNECT_RETRIES:
                    time.sleep(delay)
        logger.error("%s failed to connect after %d attempts", label, self.MAX_CONNECT_RETRIES)

    def _register_handlers(self) -> None:
        """Register callback handlers on the quote context."""
        if not self._quote_client or not self._quote_client.ctx:
            return

        self._quote_handler = QuoteHandler(self._cache, self._lock)
        self._kline_handler = KlineHandler(self._cache, self._lock)
        self._ticker_handler = TickerHandler(self._cache, self._lock)
        self._orderbook_handler = OrderBookHandler(self._cache, self._lock)

        for handler_wrapper in (
            self._quote_handler,
            self._kline_handler,
            self._ticker_handler,
            self._orderbook_handler,
        ):
            h = handler_wrapper._make_handler()
            if h is not None:
                self._quote_client.set_handler(h)
