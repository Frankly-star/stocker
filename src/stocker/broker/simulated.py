"""SimulatedBroker: paper trading implementation."""

from __future__ import annotations

import uuid
from datetime import datetime

from stocker.broker.base import BaseBroker
from stocker.broker.models import (
    AccountInfo, Order, OrderResult, OrderSide, OrderStatus, Position, PositionSource,
)


class SimulatedBroker(BaseBroker):
    """In-memory paper trading broker."""

    def __init__(self, initial_cash: float = 100_000.0) -> None:
        self._cash = initial_cash
        self._initial_cash = initial_cash
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, OrderResult] = {}

    @property
    def broker_name(self) -> str:
        return "simulated"

    async def place_order(self, order: Order) -> OrderResult:
        price = order.price or 0.0  # In real sim, would fetch market price
        total_cost = price * order.quantity
        order_id = f"SIM-{uuid.uuid4().hex[:8]}"

        # Basic validation
        if order.side == OrderSide.BUY and total_cost > self._cash:
            return OrderResult(
                order_id=order_id, ticker=order.ticker, side=order.side,
                quantity=order.quantity, status=OrderStatus.REJECTED,
                broker=self.broker_name, error="Insufficient cash",
            )

        if order.side == OrderSide.SELL:
            pos = self._positions.get(order.ticker)
            if not pos or pos.quantity < order.quantity:
                return OrderResult(
                    order_id=order_id, ticker=order.ticker, side=order.side,
                    quantity=order.quantity, status=OrderStatus.REJECTED,
                    broker=self.broker_name, error="Insufficient shares",
                )

        # Execute
        if order.side == OrderSide.BUY:
            self._cash -= total_cost
            pos = self._positions.get(order.ticker)
            if pos:
                new_qty = pos.quantity + order.quantity
                pos.avg_cost = (pos.avg_cost * pos.quantity + price * order.quantity) / new_qty
                pos.quantity = new_qty
            else:
                self._positions[order.ticker] = Position(
                    ticker=order.ticker, quantity=order.quantity,
                    avg_cost=price, current_price=price,
                    source=PositionSource.BROKER_SYNCED, broker_account="simulated",
                )
        else:
            self._cash += total_cost
            pos = self._positions[order.ticker]
            pos.quantity -= order.quantity
            if pos.quantity <= 0:
                del self._positions[order.ticker]

        result = OrderResult(
            order_id=order_id, ticker=order.ticker, side=order.side,
            quantity=order.quantity, filled_price=price,
            status=OrderStatus.FILLED, broker=self.broker_name,
        )
        self._orders[order_id] = result
        return result

    async def cancel_order(self, order_id: str) -> bool:
        # Simulated orders are instant, nothing to cancel
        return False

    async def get_order_status(self, order_id: str) -> OrderResult:
        return self._orders.get(order_id, OrderResult(
            order_id=order_id, status=OrderStatus.REJECTED,
            error="Order not found", broker=self.broker_name,
        ))

    async def sync_positions(self) -> list[Position]:
        now = datetime.now()
        for pos in self._positions.values():
            pos.last_synced_at = now
        return list(self._positions.values())

    async def get_account_info(self) -> AccountInfo:
        positions_value = sum(p.current_price * p.quantity for p in self._positions.values())
        return AccountInfo(
            account_id="SIM-001",
            total_value=self._cash + positions_value,
            cash=self._cash,
            buying_power=self._cash,
            broker=self.broker_name,
        )
