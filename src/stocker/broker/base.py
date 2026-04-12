"""BaseBroker: abstract interface for all broker implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod

from stocker.broker.models import AccountInfo, Order, OrderResult, Position


class BaseBroker(ABC):
    """Abstract base class for broker adapters."""

    @abstractmethod
    async def place_order(self, order: Order) -> OrderResult:
        """Submit an order for execution."""

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order. Returns True if successful."""

    @abstractmethod
    async def get_order_status(self, order_id: str) -> OrderResult:
        """Get the current status of an order."""

    @abstractmethod
    async def sync_positions(self) -> list[Position]:
        """Sync and return all current positions from the broker."""

    @abstractmethod
    async def get_account_info(self) -> AccountInfo:
        """Get account information (balance, buying power, etc.)."""

    @property
    @abstractmethod
    def broker_name(self) -> str:
        """Human-readable broker name."""
