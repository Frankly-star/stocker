"""Legacy dynamic data routing layer.

This module is no longer part of the main Intelligence data route. Stock analysis
uses `agents/intelligence/data_fetcher.py` with fixed sources only:
westock-data for market data and finance-news RSS for news. Keep this module for
older/backtest integrations only; do not wire it into the main analysis graph.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class DataRouter:
    """Legacy provider router; not used by the main Intelligence graph."""

    def __init__(self, default_provider: str = "yfinance") -> None:
        self.default_provider = default_provider
        # method_name -> {provider_name: callable}
        self._methods: dict[str, dict[str, Callable]] = {}
        # category -> [method_names]
        self._categories: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_method(
        self, method_name: str, provider: str, func: Callable, category: str = "misc"
    ) -> None:
        """Register a provider implementation for a method."""
        self._methods.setdefault(method_name, {})[provider] = func
        cat_methods = self._categories.setdefault(category, [])
        if method_name not in cat_methods:
            cat_methods.append(method_name)
        logger.debug("Registered %s.%s in category %s", provider, method_name, category)

    def register_provider_batch(
        self, provider: str, methods: dict[str, Callable], category: str = "misc"
    ) -> None:
        """Register multiple methods from one provider at once."""
        for name, func in methods.items():
            self.register_method(name, provider, func, category)

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def route(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Route a legacy method call.

        This legacy router may try registered providers in order, but it is not
        wired into Stocker's fixed main data route.
        """
        if method not in self._methods:
            raise ValueError(f"Method '{method}' not registered in DataRouter")

        providers = self._methods[method]
        # Legacy provider order: default first, then other registered providers
        order = []
        if self.default_provider in providers:
            order.append(self.default_provider)
        for p in providers:
            if p not in order:
                order.append(p)

        last_error = None
        for provider in order:
            try:
                result = providers[provider](*args, **kwargs)
                return result
            except Exception as e:
                logger.warning("Provider %s.%s failed: %s", provider, method, e)
                last_error = e

        raise RuntimeError(
            f"All providers failed for '{method}': {last_error}"
        )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_methods(self) -> dict[str, list[str]]:
        """Return {method_name: [provider_names]}."""
        return {m: list(p.keys()) for m, p in self._methods.items()}

    def list_categories(self) -> dict[str, list[str]]:
        """Return {category: [method_names]}."""
        return dict(self._categories)

    def has_method(self, method: str) -> bool:
        return method in self._methods


def create_default_router() -> DataRouter:
    """Create a DataRouter pre-registered with yfinance providers.

    Imports are deferred to avoid import-time side effects.
    """
    router = DataRouter(default_provider="yfinance")

    from stocker.dataflows.yfinance_provider import (
        get_stock_data,
        get_fundamentals,
        get_balance_sheet,
        get_cashflow,
        get_income_statement,
        get_insider_transactions,
    )
    from stocker.dataflows.yfinance_news import get_news, get_global_news

    router.register_provider_batch(
        "yfinance",
        {
            "get_stock_data": get_stock_data,
            "get_fundamentals": get_fundamentals,
            "get_balance_sheet": get_balance_sheet,
            "get_cashflow": get_cashflow,
            "get_income_statement": get_income_statement,
            "get_insider_transactions": get_insider_transactions,
        },
        category="yfinance_core",
    )
    router.register_provider_batch(
        "yfinance",
        {
            "get_news": get_news,
            "get_global_news": get_global_news,
        },
        category="news",
    )

    return router
