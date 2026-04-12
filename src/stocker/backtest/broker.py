"""BacktestBroker: historical-price-based order execution engine.

Inherits ``BaseBroker`` and implements all 5 abstract methods.
Orders are matched against the current bar's OHLCV data with configurable
commission and slippage models.  Pending limit orders are checked and
filled on each ``update_market_prices()`` call.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from stocker.backtest.clock import BacktestClock
from stocker.backtest.data_store import HistoricalDataStore
from stocker.backtest.models import BacktestConfig, BacktestTrade, DailySnapshot
from stocker.broker.base import BaseBroker
from stocker.broker.models import (
    AccountInfo,
    Order,
    OrderResult,
    OrderSide,
    OrderStatus,
    Position,
    PositionSource,
)

logger = logging.getLogger(__name__)


class BacktestBroker(BaseBroker):
    """Broker that executes orders against historical bar data."""

    def __init__(
        self,
        config: BacktestConfig,
        data_store: HistoricalDataStore,
        clock: BacktestClock,
    ) -> None:
        self._config = config
        self._data_store = data_store
        self._clock = clock

        self._cash: float = config.initial_cash
        self._initial_cash: float = config.initial_cash
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, OrderResult] = {}
        self._pending_orders: dict[str, Order] = {}  # limit orders waiting to fill

        # Logging
        self._trade_log: list[BacktestTrade] = []
        self._snapshots: list[DailySnapshot] = []
        self._peak_nav: float = config.initial_cash

    @property
    def broker_name(self) -> str:
        return "backtest"

    # ------------------------------------------------------------------
    # BaseBroker interface
    # ------------------------------------------------------------------

    async def place_order(self, order: Order) -> OrderResult:
        """Execute or queue an order.

        Market orders are filled immediately at the current bar's close
        (plus slippage).  Limit orders are queued and checked each bar.
        """
        order_id = f"BT-{uuid.uuid4().hex[:8]}"
        ticker = order.ticker.upper()

        # Resolve execution price
        bar = self._data_store.get_bar(ticker)
        if bar is None:
            return self._reject(order_id, order, "No market data for this bar")

        close_price = float(bar.get("Close", 0))
        if close_price <= 0:
            return self._reject(order_id, order, "Invalid bar price")

        # Market order → immediate fill
        if order.order_type == "market" or order.price is None:
            exec_price = self._apply_slippage(close_price, order.side)
            return self._fill(order_id, order, exec_price)

        # Limit order → check if fillable now, else queue
        if order.side == OrderSide.BUY and close_price <= order.price:
            return self._fill(order_id, order, self._apply_slippage(order.price, order.side))
        if order.side == OrderSide.SELL and close_price >= order.price:
            return self._fill(order_id, order, self._apply_slippage(order.price, order.side))

        # Queue as pending
        self._pending_orders[order_id] = order
        result = OrderResult(
            order_id=order_id,
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            status=OrderStatus.PENDING,
            broker=self.broker_name,
        )
        self._orders[order_id] = result
        return result

    async def cancel_order(self, order_id: str) -> bool:
        if order_id in self._pending_orders:
            del self._pending_orders[order_id]
            if order_id in self._orders:
                self._orders[order_id].status = OrderStatus.CANCELLED
            return True
        return False

    async def get_order_status(self, order_id: str) -> OrderResult:
        return self._orders.get(
            order_id,
            OrderResult(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                error="Order not found",
                broker=self.broker_name,
            ),
        )

    async def sync_positions(self) -> list[Position]:
        # Update current prices
        prices = self._data_store.get_current_prices()
        for sym, pos in self._positions.items():
            if sym in prices:
                pos.update_price(prices[sym])
            pos.last_synced_at = self._clock.now()
        return list(self._positions.values())

    async def get_account_info(self) -> AccountInfo:
        positions_value = sum(
            p.current_price * p.quantity for p in self._positions.values()
        )
        return AccountInfo(
            account_id="BT-001",
            total_value=self._cash + positions_value,
            cash=self._cash,
            buying_power=self._cash,
            broker=self.broker_name,
        )

    # ------------------------------------------------------------------
    # Backtest-specific methods
    # ------------------------------------------------------------------

    def update_market_prices(self, bars: dict[str, dict]) -> list[OrderResult]:
        """Called each bar to update positions and try to fill pending orders.

        Args:
            bars: ``{symbol: bar_dict}`` for the current bar.

        Returns:
            List of newly filled order results (from pending orders).
        """
        # Update position prices
        for sym, bar in bars.items():
            close = float(bar.get("Close", 0))
            if close > 0 and sym in self._positions:
                self._positions[sym].update_price(close)

        # Try to fill pending limit orders
        filled: list[OrderResult] = []
        to_remove = []
        for oid, order in self._pending_orders.items():
            ticker = order.ticker.upper()
            bar = bars.get(ticker)
            if bar is None:
                continue

            high = float(bar.get("High", 0))
            low = float(bar.get("Low", 0))

            if order.side == OrderSide.BUY and order.price is not None and low <= order.price:
                result = self._fill(oid, order, self._apply_slippage(order.price, order.side))
                filled.append(result)
                to_remove.append(oid)
            elif order.side == OrderSide.SELL and order.price is not None and high >= order.price:
                result = self._fill(oid, order, self._apply_slippage(order.price, order.side))
                filled.append(result)
                to_remove.append(oid)

        for oid in to_remove:
            self._pending_orders.pop(oid, None)

        return filled

    def take_snapshot(self) -> DailySnapshot:
        """Record end-of-bar portfolio snapshot."""
        positions_value = sum(
            p.current_price * p.quantity for p in self._positions.values()
        )
        nav = self._cash + positions_value
        self._peak_nav = max(self._peak_nav, nav)
        drawdown = (self._peak_nav - nav) / self._peak_nav * 100 if self._peak_nav > 0 else 0.0

        snap = DailySnapshot(
            dt=self._clock.now(),
            bar_index=self._clock.bar_index,
            cash=self._cash,
            positions_value=positions_value,
            nav=nav,
            drawdown_pct=drawdown,
        )
        self._snapshots.append(snap)
        return snap

    def get_trade_log(self) -> list[BacktestTrade]:
        return list(self._trade_log)

    def get_snapshots(self) -> list[DailySnapshot]:
        return list(self._snapshots)

    def get_nav(self) -> float:
        """Current net asset value."""
        positions_value = sum(
            p.current_price * p.quantity for p in self._positions.values()
        )
        return self._cash + positions_value

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fill(self, order_id: str, order: Order, exec_price: float) -> OrderResult:
        """Execute an order fill: update cash, positions, log trade."""
        ticker = order.ticker.upper()
        quantity = order.quantity
        total_cost = exec_price * quantity
        commission = total_cost * self._config.commission_rate
        slippage_per_share = abs(exec_price - (order.price or exec_price))

        # Validate
        if order.side == OrderSide.BUY:
            if total_cost + commission > self._cash:
                return self._reject(order_id, order, "Insufficient cash")
        elif order.side == OrderSide.SELL:
            pos = self._positions.get(ticker)
            if not pos or pos.quantity < quantity:
                return self._reject(order_id, order, "Insufficient shares")

        # Execute
        pnl = None
        if order.side == OrderSide.BUY:
            self._cash -= (total_cost + commission)
            pos = self._positions.get(ticker)
            if pos:
                new_qty = pos.quantity + quantity
                pos.avg_cost = (pos.avg_cost * pos.quantity + exec_price * quantity) / new_qty
                pos.quantity = new_qty
                pos.update_price(exec_price)
            else:
                self._positions[ticker] = Position(
                    ticker=ticker,
                    quantity=quantity,
                    avg_cost=exec_price,
                    current_price=exec_price,
                    source=PositionSource.BROKER_SYNCED,
                    broker_account="backtest",
                )
        else:  # SELL
            self._cash += (total_cost - commission)
            pos = self._positions[ticker]
            pnl = (exec_price - pos.avg_cost) * quantity - commission
            pos.quantity -= quantity
            if pos.quantity <= 0:
                del self._positions[ticker]

        # Record
        result = OrderResult(
            order_id=order_id,
            ticker=order.ticker,
            side=order.side,
            quantity=quantity,
            filled_price=exec_price,
            status=OrderStatus.FILLED,
            timestamp=self._clock.now(),
            broker=self.broker_name,
        )
        self._orders[order_id] = result

        trade = BacktestTrade(
            trade_id=order_id,
            bar_index=self._clock.bar_index,
            timestamp=self._clock.now(),
            ticker=ticker,
            side=order.side.value,
            quantity=quantity,
            price=exec_price,
            slippage=slippage_per_share,
            commission=commission,
            pnl=pnl,
        )
        self._trade_log.append(trade)

        logger.debug(
            "[BacktestBroker] %s %s x%d @ %.2f (comm=%.2f, slip=%.4f)",
            order.side.value, ticker, quantity, exec_price, commission, slippage_per_share,
        )
        return result

    def _reject(self, order_id: str, order: Order, reason: str) -> OrderResult:
        result = OrderResult(
            order_id=order_id,
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            status=OrderStatus.REJECTED,
            broker=self.broker_name,
            error=reason,
        )
        self._orders[order_id] = result
        return result

    def _apply_slippage(self, price: float, side: OrderSide) -> float:
        """Apply slippage to execution price."""
        slip = price * self._config.slippage_pct
        if side == OrderSide.BUY:
            return round(price + slip, 4)  # buy higher
        return round(price - slip, 4)  # sell lower
