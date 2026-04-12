"""FutuBroker: real broker implementation backed by Futu Open API.

Delegates all operations to ``FutuRuntime``'s trade client and uses
``mappers`` to convert between Futu DataFrames and Stocker broker models.
"""

from __future__ import annotations

import logging
from typing import Any

from stocker.broker.base import BaseBroker
from stocker.broker.models import AccountInfo, Order, OrderResult, OrderSide, OrderStatus, Position
from stocker.integrations.futu.mappers import (
    convert_ticker_to_futu,
    map_account_info,
    map_futu_order_status,
    map_order_result,
    map_order_side_to_futu,
    map_order_type_to_futu,
    map_positions,
)

logger = logging.getLogger(__name__)


class FutuBroker(BaseBroker):
    """Broker adapter that routes orders through the Futu Open API."""

    def __init__(self, runtime: Any, config: dict) -> None:
        """
        Args:
            runtime: A started ``FutuRuntime`` instance.
            config: The main stocker config dict (for execution_mode, etc.).
        """
        self._runtime = runtime
        self._config = config

    @property
    def broker_name(self) -> str:
        return "futu"

    # ------------------------------------------------------------------
    # BaseBroker interface
    # ------------------------------------------------------------------

    async def place_order(self, order: Order) -> OrderResult:
        """Place an order through the Futu trade client.

        Implements a two-layer safety mechanism:

        **Layer 1 — System execution mode** (``execution_mode``):
            ``observe`` → order rejected immediately, regardless of Futu trd_env.
            ``active``  → order proceeds to Layer 2 check.

        **Layer 2 — Futu trading environment** (``trd_env``):
            ``simulate`` → order goes to Futu paper trading.
            ``real``     → order goes to live market (extra warning logged).

        This ensures that even if the Supervisor prompt guard is bypassed,
        no real trade can happen while the system is in observe mode.
        """
        # --- Layer 1: system execution mode guard ---
        from stocker.engine.runtime_state import get_execution_mode
        exec_mode = get_execution_mode()
        if exec_mode != "active":
            logger.warning(
                "FutuBroker.place_order BLOCKED: execution_mode=%s (must be 'active'). "
                "ticker=%s side=%s qty=%d",
                exec_mode, order.ticker, order.side.value, order.quantity,
            )
            return OrderResult(
                ticker=order.ticker,
                side=order.side,
                quantity=order.quantity,
                status=OrderStatus.REJECTED,
                broker=self.broker_name,
                error=f"Order rejected: system is in '{exec_mode}' mode (must be 'active')",
            )

        # --- Layer 2: Futu environment awareness ---
        trd_env = self._runtime.config.trd_env.lower()
        if trd_env == "real":
            logger.warning(
                "FutuBroker.place_order proceeding in REAL environment! "
                "ticker=%s side=%s qty=%d price=%s",
                order.ticker, order.side.value, order.quantity, order.price,
            )

        # --- Pre-flight checks ---
        tc = self._runtime.trade_client
        if tc is None or not tc.connected:
            return OrderResult(
                ticker=order.ticker, side=order.side, quantity=order.quantity,
                status=OrderStatus.REJECTED, broker=self.broker_name,
                error="Trade client not connected",
            )

        if not tc.unlocked and self._runtime.config.trd_env.lower() == "real":
            return OrderResult(
                ticker=order.ticker, side=order.side, quantity=order.quantity,
                status=OrderStatus.REJECTED, broker=self.broker_name,
                error="实盘交易未解锁 — 请在 OpenD 界面解锁或检查 STOCKER_FUTU_TRADE_PWD",
            )

        futu_code = convert_ticker_to_futu(order.ticker, self._runtime.config.market)
        futu_side = map_order_side_to_futu(order.side)
        futu_otype = map_order_type_to_futu(order.order_type)
        price = order.price if order.price is not None else 0.0

        ret, data = tc.place_order(
            code=futu_code,
            price=price,
            qty=order.quantity,
            trd_side=futu_side,
            order_type=futu_otype,
        )

        if ret != 0:
            error_msg = str(data)[:200] if data else f"place_order ret={ret}"
            return OrderResult(
                ticker=order.ticker,
                side=order.side,
                quantity=order.quantity,
                status=OrderStatus.REJECTED,
                broker=self.broker_name,
                error=error_msg,
            )

        # Parse the returned DataFrame (usually 1 row)
        if hasattr(data, "iloc") and len(data) > 0:
            return map_order_result(data.iloc[0], broker=self.broker_name)

        return OrderResult(
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            status=OrderStatus.PENDING,
            broker=self.broker_name,
        )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order via modify_order with CANCEL op."""
        tc = self._runtime.trade_client
        if tc is None or not tc.connected:
            logger.warning("cancel_order: trade client not connected")
            return False

        ret, _ = tc.cancel_order(order_id)
        return ret == 0

    async def get_order_status(self, order_id: str) -> OrderResult:
        """Query current status of a specific order."""
        tc = self._runtime.trade_client
        if tc is None or not tc.connected:
            return OrderResult(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                broker=self.broker_name,
                error="Trade client not connected",
            )

        df = tc.query_orders()
        if df is not None and not df.empty:
            match = df[df["order_id"].astype(str) == str(order_id)]
            if not match.empty:
                return map_order_result(match.iloc[0], broker=self.broker_name)

        return OrderResult(
            order_id=order_id,
            status=OrderStatus.REJECTED,
            broker=self.broker_name,
            error=f"Order {order_id} not found",
        )

    async def sync_positions(self) -> list[Position]:
        """Query all positions from the Futu account."""
        tc = self._runtime.trade_client
        if tc is None or not tc.connected:
            logger.warning("sync_positions: trade client not connected")
            return []

        df = tc.query_positions()
        return map_positions(df, broker=self.broker_name)

    async def get_account_info(self) -> AccountInfo:
        """Query account info (balance, buying power, etc.)."""
        tc = self._runtime.trade_client
        if tc is None or not tc.connected:
            return AccountInfo(broker=self.broker_name)

        df = tc.query_account_info()
        if df is not None and not df.empty:
            return map_account_info(df.iloc[0], broker=self.broker_name)

        return AccountInfo(broker=self.broker_name)
