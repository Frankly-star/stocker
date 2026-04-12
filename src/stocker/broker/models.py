"""Broker data models: Order, Position, TradeRecord."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PositionSource(str, Enum):
    BROKER_SYNCED = "broker_synced"
    MANUAL_IMPORT = "manual_import"
    CSV_IMPORT = "csv_import"


class Order(BaseModel):
    """A trade order.

    Attributes:
        order_type: Order execution type. Base types: ``"market"`` / ``"limit"``.
            When using FutuBroker, the following additional types are available:
            ``"enhanced_limit"`` — Enhanced limit order (港股增强限价盘)
            ``"auction"``        — Auction order (竞价盘)
            ``"auction_limit"``  — Auction limit order (竞价限价盘)
            These map to ``futu.OrderType`` via ``mappers.map_order_type_to_futu()``.
    """
    ticker: str
    side: OrderSide
    quantity: int
    price: float | None = None  # None = market order
    order_type: str = "market"  # "market" / "limit" / "enhanced_limit" / "auction" / "auction_limit"
    stop_loss: float | None = None
    take_profit: float | None = None


class OrderResult(BaseModel):
    """Result of an order execution."""
    order_id: str = ""
    ticker: str = ""
    side: OrderSide = OrderSide.BUY
    quantity: int = 0
    filled_price: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    timestamp: datetime = Field(default_factory=datetime.now)
    broker: str = ""
    error: str | None = None


class Position(BaseModel):
    """A stock position (holding)."""
    ticker: str
    name: str = ""
    quantity: int = 0
    avg_cost: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    source: PositionSource = PositionSource.MANUAL_IMPORT
    broker_account: str = ""
    market_type: str = ""  # "us" / "cn" / "hk" / "crypto"
    last_synced_at: datetime | None = None
    added_at: datetime = Field(default_factory=datetime.now)

    def update_price(self, price: float) -> None:
        self.current_price = price
        self.unrealized_pnl = (price - self.avg_cost) * self.quantity


class TradeRecord(BaseModel):
    """Historical trade record."""
    trade_id: str = ""
    ticker: str = ""
    side: str = ""
    quantity: int = 0
    price: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.now)
    broker: str = ""
    pnl: float | None = None
    notes: str = ""


class AccountInfo(BaseModel):
    """Broker account information."""
    account_id: str = ""
    total_value: float = 0.0
    cash: float = 0.0
    buying_power: float = 0.0
    broker: str = ""
