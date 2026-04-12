"""BacktestRuntime: the main backtest orchestration engine.

Coordinates clock advancement, data feeding, strategy evaluation,
order execution, and result collection into a single run loop.

Supports two run modes:
  - **rule**: Pure rule-based signals (fast, no LLM calls)
  - **full**: Full LangGraph subgraph pipeline (slow, calls Intelligence + Execution)
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from stocker.backtest.broker import BacktestBroker
from stocker.backtest.clock import BacktestClock
from stocker.backtest.collector import BacktestResultCollector
from stocker.backtest.data_store import HistoricalDataStore
from stocker.backtest.models import BacktestConfig, BacktestReport, BacktestRunMode

logger = logging.getLogger(__name__)

_REPORTS_DIR = Path("data/backtest/reports")


class BacktestRuntime:
    """Orchestrates a complete backtest run.

    Usage::

        config = BacktestConfig(symbols=["AAPL"], start_date="2024-01-01", end_date="2024-12-31")
        runtime = BacktestRuntime(config)
        report = runtime.run()
    """

    def __init__(
        self,
        config: BacktestConfig,
        strategy_fn: Callable[[dict, BacktestBroker], None] | None = None,
    ) -> None:
        """
        Args:
            config: Backtest configuration.
            strategy_fn: For ``rule`` mode — a callable ``(bar_data, broker) -> None``
                that evaluates signals and calls ``broker.place_order()`` as needed.
                ``bar_data`` is ``{symbol: {Date, Open, High, Low, Close, Volume}}``.
                If None and run_mode is rule, a default no-op strategy is used.
        """
        self._config = config
        self._strategy_fn = strategy_fn

        # Core components (created in run())
        self._clock: BacktestClock | None = None
        self._data_store: HistoricalDataStore | None = None
        self._broker: BacktestBroker | None = None
        self._collector: BacktestResultCollector | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> BacktestReport:
        """Execute the complete backtest and return the report."""
        logger.info(
            "[BacktestRuntime] Starting backtest: symbols=%s, %s to %s, mode=%s",
            self._config.symbols, self._config.start_date, self._config.end_date,
            self._config.run_mode,
        )
        t0 = time.time()

        # 1. Initialize components
        self._clock = BacktestClock(
            self._config.start_date,
            self._config.end_date,
            self._config.bar_frequency.value,
        )
        self._data_store = HistoricalDataStore(self._clock)
        self._collector = BacktestResultCollector(self._config)

        # 2. Load historical data
        self._data_store.load(
            self._config.symbols,
            self._config.start_date,
            self._config.end_date,
            self._config.data_source,
            self._config.data_path,
        )

        # 3. Create broker
        self._broker = BacktestBroker(self._config, self._data_store, self._clock)

        # 4. Run main loop
        if self._config.run_mode == BacktestRunMode.FULL:
            self._run_full_mode()
        else:
            self._run_rule_mode()

        # 5. Finalize report
        elapsed = time.time() - t0
        report = self._collector.finalize()
        report.duration_seconds = elapsed

        logger.info(
            "[BacktestRuntime] Backtest completed in %.1fs: return=%.2f%%, "
            "max_dd=%.2f%%, sharpe=%.4f, trades=%d",
            elapsed,
            report.metrics.total_return_pct,
            report.metrics.max_drawdown_pct,
            report.metrics.sharpe_ratio,
            report.metrics.total_trades,
        )

        # 6. Save report
        self._save_report(report)
        return report

    # ------------------------------------------------------------------
    # Rule mode: pure signal-based, no LLM
    # ------------------------------------------------------------------

    def _run_rule_mode(self) -> None:
        """Main loop for rule-based backtest."""
        while True:
            dt = self._clock.advance()
            if dt is None:
                break

            # Gather current bars
            bars = self._gather_bars()
            if not bars:
                continue

            # Update broker prices + fill pending orders
            filled = self._broker.update_market_prices(bars)
            for result in filled:
                # Pending orders that just filled
                pass

            # Evaluate strategy
            if self._strategy_fn is not None:
                try:
                    import asyncio
                    # strategy_fn may call broker.place_order which is async
                    # Wrap in event loop for sync context
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(
                            self._async_strategy_wrapper(bars)
                        )
                    finally:
                        loop.close()
                except Exception as e:
                    logger.warning("[BacktestRuntime] Strategy error at %s: %s", dt, e)

            # Snapshot
            snap = self._broker.take_snapshot()
            self._collector.add_snapshot(snap)

        # Collect all trades
        self._collector.add_trades(self._broker.get_trade_log())

    async def _async_strategy_wrapper(self, bars: dict) -> None:
        """Wrap strategy_fn to handle both sync and async callers."""
        if self._strategy_fn and self._broker:
            self._strategy_fn(bars, self._broker)

    # ------------------------------------------------------------------
    # Full mode: uses LangGraph subgraphs
    # ------------------------------------------------------------------

    def _run_full_mode(self) -> None:
        """Main loop using Intelligence + Execution subgraphs.

        Constructs LangGraph graphs once, then invokes them per bar.
        Since LLM calls are expensive, this mode samples at configurable
        intervals (default: every bar, but can be tuned).
        """
        # Build subgraphs
        intelligence_graph, execution_graph, broker_for_exec = self._build_graphs()

        while True:
            dt = self._clock.advance()
            if dt is None:
                break

            bars = self._gather_bars()
            if not bars:
                continue

            # Update broker prices
            self._broker.update_market_prices(bars)

            # Run intelligence analysis for each symbol
            for symbol in self._config.symbols:
                bar = bars.get(symbol.upper())
                if not bar:
                    continue

                try:
                    self._run_intelligence_and_execute(
                        symbol, intelligence_graph, execution_graph
                    )
                except Exception as e:
                    logger.warning(
                        "[BacktestRuntime] Full-mode error for %s at %s: %s",
                        symbol, dt, e,
                    )

            # Snapshot
            snap = self._broker.take_snapshot()
            self._collector.add_snapshot(snap)

        self._collector.add_trades(self._broker.get_trade_log())

    def _build_graphs(self) -> tuple:
        """Build Intelligence and Execution LangGraph subgraphs for backtest.

        Returns (intelligence_graph, execution_graph, broker).
        """
        try:
            from stocker.config import create_llm, load_config
            from stocker.dataflows.router import DataRouter
            from stocker.graphs.execution_graph import build_execution_graph
            from stocker.graphs.intelligence_graph import build_intelligence_graph

            config = load_config()
            llm = create_llm(config)

            # Register historical data on a new DataRouter
            router = DataRouter(default_provider="historical")
            self._data_store.register_as_provider(router)

            ig = build_intelligence_graph(llm)
            eg = build_execution_graph(self._broker)

            logger.info("[BacktestRuntime] LangGraph subgraphs built for full mode")
            return ig, eg, self._broker
        except Exception as e:
            logger.error("[BacktestRuntime] Failed to build graphs: %s", e)
            raise RuntimeError(f"Cannot build LangGraph subgraphs for full mode: {e}") from e

    def _run_intelligence_and_execute(
        self,
        symbol: str,
        intelligence_graph: Any,
        execution_graph: Any,
    ) -> None:
        """Run Intelligence → parse signal → Execution for one symbol at current bar."""
        from langchain_core.messages import HumanMessage

        trade_date = self._clock.now_str()

        # 1. Intelligence analysis
        intel_result = intelligence_graph.invoke({
            "ticker": symbol,
            "trade_date": trade_date,
            "messages": [HumanMessage(content=f"Analyze {symbol}")],
        })

        report = intel_result.get("intelligence_report")
        if not report:
            return

        # 2. Simple signal extraction from report
        # In full mode, we use the market_environment and technical signals
        # to generate basic trading signals
        action = self._extract_signal(report)
        if not action:
            return

        # 3. Execute through execution graph
        bar = self._data_store.get_bar(symbol)
        if not bar:
            return

        price = float(bar.get("Close", 0))
        quantity = self._calculate_position_size(symbol, price, action)
        if quantity <= 0:
            return

        execution_graph.invoke({
            "ticker": symbol,
            "order_params": {
                "ticker": symbol,
                "side": action,
                "quantity": quantity,
                "price": price,
            },
            "messages": [HumanMessage(content=f"{action} {symbol}")],
        })

    def _extract_signal(self, report: Any) -> str | None:
        """Extract a buy/sell signal from an intelligence report.

        Simple heuristic for full mode — can be replaced with more
        sophisticated logic or an additional LLM call.
        """
        try:
            signals = report.technical_signals
            zone = report.current_zone

            # Simple mean-reversion signal for range-bound markets
            if report.market_environment == "range_bound":
                if zone == "near_support" and signals.rsi < 35:
                    return "buy"
                if zone == "near_resistance" and signals.rsi > 65:
                    return "sell"

            # Trend-following for trending markets
            if report.market_environment == "trending_up" and signals.rsi < 45:
                return "buy"
            if report.market_environment == "trending_down" and signals.rsi > 55:
                return "sell"

        except Exception:
            pass
        return None

    def _calculate_position_size(self, symbol: str, price: float, action: str) -> int:
        """Calculate number of shares to trade."""
        if price <= 0:
            return 0

        if action == "buy":
            # Use 10% of available cash
            available = self._broker._cash * 0.10
            qty = int(available / price)
            return max(qty, 0)
        elif action == "sell":
            pos = self._broker._positions.get(symbol.upper())
            if pos and pos.quantity > 0:
                return pos.quantity  # sell all
        return 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _gather_bars(self) -> dict[str, dict]:
        """Get current bar data for all symbols."""
        bars = {}
        for sym in self._config.symbols:
            bar = self._data_store.get_bar(sym.upper())
            if bar:
                bars[sym.upper()] = bar
        return bars

    def _save_report(self, report: BacktestReport) -> None:
        """Save report JSON to data/backtest/reports/."""
        try:
            _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            symbols_slug = "_".join(s[:4] for s in self._config.symbols[:3])
            filename = f"bt_{symbols_slug}_{ts}.json"
            filepath = _REPORTS_DIR / filename
            filepath.write_text(
                report.model_dump_json(indent=2),
                encoding="utf-8",
            )
            logger.info("[BacktestRuntime] Report saved to %s", filepath)
        except Exception as e:
            logger.warning("[BacktestRuntime] Failed to save report: %s", e)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def clock(self) -> BacktestClock | None:
        return self._clock

    @property
    def broker(self) -> BacktestBroker | None:
        return self._broker

    @property
    def data_store(self) -> HistoricalDataStore | None:
        return self._data_store
