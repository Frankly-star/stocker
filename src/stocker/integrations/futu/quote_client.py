"""FutuQuoteClient: wraps ``futu.OpenQuoteContext`` for Stocker.

Responsibilities:
- Connect / close the quote context
- Subscribe / unsubscribe / query subscriptions
- Pull snapshots, stock quotes, K-lines, order books
- Register callback handlers
"""

from __future__ import annotations

import logging
from typing import Any

from stocker.integrations.futu.config import FutuConfig

logger = logging.getLogger(__name__)


class FutuQuoteClient:
    """Thin wrapper around ``futu.OpenQuoteContext``."""

    def __init__(self, config: FutuConfig) -> None:
        self._config = config
        self._ctx: Any = None  # futu.OpenQuoteContext
        self._connected = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Create and start the OpenQuoteContext."""
        from futu import OpenQuoteContext

        self._ctx = OpenQuoteContext(host=self._config.host, port=self._config.port)
        self._connected = True
        logger.info("FutuQuoteClient connected to %s:%d", self._config.host, self._config.port)

    def close(self) -> None:
        """Close the quote context."""
        if self._ctx is not None:
            try:
                self._ctx.close()
            except Exception as e:
                logger.warning("Error closing quote context: %s", e)
            finally:
                self._ctx = None
                self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected and self._ctx is not None

    @property
    def ctx(self):
        """Raw ``OpenQuoteContext`` for advanced usage."""
        return self._ctx

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def subscribe(self, codes: list[str], subtypes: list, push: bool = True) -> bool:
        """Subscribe to real-time data for *codes* with given *subtypes*.

        Args:
            codes: List of Futu-format codes, e.g. ``["HK.00700"]``.
            subtypes: List of ``futu.SubType`` values.
            push: Whether to receive push callbacks.

        Returns:
            True if subscription succeeded.
        """
        if not self._ctx:
            logger.warning("subscribe called but quote context is not connected")
            return False

        ret, err = self._ctx.subscribe(codes, subtypes, push=push)
        if ret != 0:
            logger.warning("subscribe failed: ret=%s err=%s codes=%s", ret, err, codes)
            return False
        logger.info("Subscribed: codes=%s subtypes=%s", codes, subtypes)
        return True

    def unsubscribe(self, codes: list[str], subtypes: list) -> bool:
        """Unsubscribe from real-time data."""
        if not self._ctx:
            return False
        ret, err = self._ctx.unsubscribe(codes, subtypes)
        if ret != 0:
            logger.warning("unsubscribe failed: ret=%s err=%s", ret, err)
            return False
        return True

    def query_subscription(self, is_all_conn: bool = False) -> dict:
        """Query current subscriptions."""
        if not self._ctx:
            return {}
        ret, data = self._ctx.query_subscription(is_all_conn=is_all_conn)
        if ret != 0:
            logger.warning("query_subscription failed: ret=%s", ret)
            return {}
        return data if isinstance(data, dict) else {"raw": data}

    # ------------------------------------------------------------------
    # Pull-based data retrieval
    # ------------------------------------------------------------------

    def get_market_snapshot(self, codes: list[str]) -> list[dict]:
        """Get market snapshot for a list of codes.

        Returns list of dicts (one per code), or empty list on failure.
        """
        if not self._ctx:
            return []
        ret, df = self._ctx.get_market_snapshot(codes)
        if ret != 0 or df is None or df.empty:
            logger.debug("get_market_snapshot: ret=%s codes=%s", ret, codes)
            return []
        return df.to_dict("records")

    def get_stock_quote(self, codes: list[str]) -> list[dict]:
        """Get real-time stock quotes (requires prior subscription)."""
        if not self._ctx:
            return []
        ret, df = self._ctx.get_stock_quote(codes)
        if ret != 0 or df is None or df.empty:
            return []
        return df.to_dict("records")

    def get_cur_kline(self, code: str, ktype, count: int = 120) -> list[dict]:
        """Get current K-line data for a single code.

        Args:
            code: Futu-format code (e.g. ``"HK.00700"``).
            ktype: ``futu.KLType`` value (e.g. ``KLType.K_DAY``).
            count: Number of bars to retrieve.

        Returns:
            List of K-line bar dicts, or empty list.
        """
        if not self._ctx:
            return []
        ret, df = self._ctx.get_cur_kline(code, ktype, count)
        if ret != 0 or df is None or df.empty:
            logger.debug("get_cur_kline: ret=%s code=%s", ret, code)
            return []
        return df.to_dict("records")

    def get_order_book(self, code: str) -> dict:
        """Get current order book for a single code."""
        if not self._ctx:
            return {}
        ret, data = self._ctx.get_order_book(code)
        if ret != 0:
            return {}
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def set_handler(self, handler) -> None:
        """Register a Futu callback handler on the quote context."""
        if self._ctx is not None:
            self._ctx.set_handler(handler)
