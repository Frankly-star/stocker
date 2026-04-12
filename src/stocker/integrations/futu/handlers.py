"""Futu quote callback handlers.

Each handler inherits from the corresponding Futu *HandlerBase and overrides
``on_recv_rsp``.  The contract is:

    - **Thread safety**: every write goes through a ``threading.Lock``.
    - **No blocking I/O**: callbacks must complete in < 1 ms.
    - **Minimal logging**: only ``DEBUG`` on normal ticks; ``WARNING`` on errors.

Data is stored in shared ``cache`` dicts supplied by ``FutuRuntime``.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


# ======================================================================
# Quote handler
# ======================================================================


class QuoteHandler:
    """Handles real-time quote pushes (``SubType.QUOTE``).

    Stores latest quote snapshot per code in *cache["quote"]*.
    """

    def __init__(self, cache: dict[str, Any], lock: threading.Lock) -> None:
        self._cache = cache
        self._lock = lock

    def _make_handler(self):
        """Build and return a Futu ``StockQuoteHandlerBase`` subclass instance."""
        try:
            from futu import StockQuoteHandlerBase
        except ImportError:
            return None

        outer = self

        class _Handler(StockQuoteHandlerBase):
            def on_recv_rsp(self, rsp_pb):
                ret_code, df = super().on_recv_rsp(rsp_pb)
                if ret_code != 0 or df is None or df.empty:
                    logger.debug("QuoteHandler: ret=%s", ret_code)
                    return ret_code, df
                with outer._lock:
                    for _, row in df.iterrows():
                        code = str(row.get("code", ""))
                        if code:
                            outer._cache.setdefault("quote", {})[code] = row.to_dict()
                return ret_code, df

        return _Handler()


# ======================================================================
# K-line handler
# ======================================================================


class KlineHandler:
    """Handles real-time K-line pushes (``SubType.K_*``).

    Stores latest kline bar per ``(code, ktype)`` in *cache["kline"]*.
    """

    def __init__(self, cache: dict[str, Any], lock: threading.Lock) -> None:
        self._cache = cache
        self._lock = lock

    def _make_handler(self):
        try:
            from futu import CurKlineHandlerBase
        except ImportError:
            return None

        outer = self

        class _Handler(CurKlineHandlerBase):
            def on_recv_rsp(self, rsp_pb):
                ret_code, df = super().on_recv_rsp(rsp_pb)
                if ret_code != 0 or df is None or df.empty:
                    return ret_code, df
                with outer._lock:
                    for _, row in df.iterrows():
                        code = str(row.get("code", ""))
                        ktype = str(row.get("k_type", ""))
                        if code:
                            key = f"{code}:{ktype}"
                            outer._cache.setdefault("kline", {})[key] = row.to_dict()
                return ret_code, df

        return _Handler()


# ======================================================================
# Ticker (trade tick) handler
# ======================================================================


class TickerHandler:
    """Handles real-time ticker pushes (``SubType.TICKER``).

    Stores last N ticks per code in *cache["ticker"]* (ring buffer, max 50).
    """

    MAX_TICKS = 50

    def __init__(self, cache: dict[str, Any], lock: threading.Lock) -> None:
        self._cache = cache
        self._lock = lock

    def _make_handler(self):
        try:
            from futu import TickerHandlerBase
        except ImportError:
            return None

        outer = self

        class _Handler(TickerHandlerBase):
            def on_recv_rsp(self, rsp_pb):
                ret_code, df = super().on_recv_rsp(rsp_pb)
                if ret_code != 0 or df is None or df.empty:
                    return ret_code, df
                with outer._lock:
                    for _, row in df.iterrows():
                        code = str(row.get("code", ""))
                        if code:
                            buf = outer._cache.setdefault("ticker", {}).setdefault(code, [])
                            buf.append(row.to_dict())
                            if len(buf) > outer.MAX_TICKS:
                                del buf[: len(buf) - outer.MAX_TICKS]
                return ret_code, df

        return _Handler()


# ======================================================================
# Order-book handler
# ======================================================================


class OrderBookHandler:
    """Handles real-time order-book pushes (``SubType.ORDER_BOOK``).

    Stores latest order book per code in *cache["order_book"]*.
    """

    def __init__(self, cache: dict[str, Any], lock: threading.Lock) -> None:
        self._cache = cache
        self._lock = lock

    def _make_handler(self):
        try:
            from futu import OrderBookHandlerBase
        except ImportError:
            return None

        outer = self

        class _Handler(OrderBookHandlerBase):
            def on_recv_rsp(self, rsp_pb):
                ret_code, df = super().on_recv_rsp(rsp_pb)
                if ret_code != 0 or df is None or df.empty:
                    return ret_code, df
                with outer._lock:
                    code = str(df.get("code", "")) if isinstance(df, dict) else ""
                    if not code and hasattr(df, "iloc"):
                        code = str(df.iloc[0].get("code", "")) if len(df) > 0 else ""
                    if code:
                        outer._cache.setdefault("order_book", {})[code] = (
                            df.to_dict() if hasattr(df, "to_dict") else df
                        )
                return ret_code, df

        return _Handler()
