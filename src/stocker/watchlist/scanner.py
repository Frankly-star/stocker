"""WatchlistScanner: batch analysis of watchlist stocks for swing trading signals."""

from __future__ import annotations

import logging
from typing import Any

from stocker.analysis.models import SwingSignal
from stocker.analysis.swing_signals import SwingSignalEngine
from stocker.utils.data_helpers import fetch_ohlcv_westock
from stocker.watchlist.models import ScanFilter
from stocker.watchlist.store import WatchlistStore

logger = logging.getLogger(__name__)

MAX_SCAN_BATCH = 50  # prevent excessive API calls


class WatchlistScanner:
    """Scans watchlist stocks through the SwingSignalEngine."""

    def __init__(self, store: WatchlistStore) -> None:
        self._store = store
        self._engine = SwingSignalEngine()

    async def scan_all(
        self,
        scan_filter: ScanFilter | None = None,
        data_fetch_func: Any = None,
    ) -> list[dict]:
        """Scan all watchlist items and generate swing signals.

        Args:
            scan_filter: Optional filter criteria to narrow results.
            data_fetch_func: Async callable(ticker) -> pd.DataFrame (OHLCV).
                             If None, will use westock-data fixed source.

        Returns:
            List of scan results sorted by signal strength.
        """
        items = self._store.list_all()
        if not items:
            return [{"message": "Watchlist is empty. Add stocks first."}]

        # Limit batch size
        items = items[:MAX_SCAN_BATCH]
        results = []

        for item in items:
            ticker = item.ticker
            logger.info("Scanning watchlist item: %s", ticker)

            try:
                # Get OHLCV data
                df = None
                if data_fetch_func:
                    df = await data_fetch_func(ticker)
                else:
                    df = fetch_ohlcv_westock(ticker)

                # Generate signal
                signal = self._engine.analyze(ticker, df)

                # Apply filter
                if scan_filter and not self._passes_filter(signal, scan_filter):
                    continue

                # Update store with latest signal
                self._store.update_signal(ticker, signal.model_dump(mode="json"))

                results.append({
                    "ticker": ticker,
                    "name": item.name,
                    "market": item.market,
                    "tags": item.tags,
                    "signal_type": signal.signal_type.value,
                    "strength": signal.strength,
                    "suggested_price": signal.suggested_price,
                    "stop_loss": signal.stop_loss,
                    "take_profit": signal.take_profit,
                    "reasons": signal.reasons,
                    "market_environment": signal.market_environment,
                    "indicators": signal.indicators,
                })

            except Exception as e:
                logger.warning("Failed to scan %s: %s", ticker, e)
                results.append({
                    "ticker": ticker,
                    "name": item.name,
                    "error": str(e),
                })

        # Sort by signal strength (descending)
        results.sort(key=lambda r: r.get("strength", 0), reverse=True)
        return results

    def _passes_filter(self, signal: SwingSignal, f: ScanFilter) -> bool:
        """Check if a signal passes the scan filter criteria."""
        ind = signal.indicators

        if f.min_signal_strength and signal.strength < f.min_signal_strength:
            return False

        rsi = ind.get("rsi", 50)
        if f.rsi_below is not None and rsi >= f.rsi_below:
            return False
        if f.rsi_above is not None and rsi <= f.rsi_above:
            return False

        bb = ind.get("bb_position", 0.5)
        if f.bb_position_below is not None and bb >= f.bb_position_below:
            return False
        if f.bb_position_above is not None and bb <= f.bb_position_above:
            return False

        if f.macd_cross_up and signal.signal_type.value != "entry_long":
            return False
        if f.macd_cross_down and signal.signal_type.value != "exit_long":
            return False

        if f.near_support:
            supports = ind.get("supports", [])
            price = ind.get("current_price", 0)
            if not supports or not price:
                return False

        if f.near_resistance:
            resistances = ind.get("resistances", [])
            price = ind.get("current_price", 0)
            if not resistances or not price:
                return False

        if f.market_environment and signal.market_environment != f.market_environment:
            return False

        return True


