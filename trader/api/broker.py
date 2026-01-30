"""Abstract broker interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional


class OrderSide(Enum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order type."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    """Order status."""

    NEW = "new"
    PENDING = "pending"
    ACCEPTED = "accepted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class Account:
    """Trading account information."""

    cash: Decimal
    buying_power: Decimal
    equity: Decimal
    currency: str = "USD"


@dataclass
class Position:
    """Open position."""

    symbol: str
    qty: Decimal
    avg_entry_price: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pl: Decimal
    unrealized_pl_pct: Decimal


@dataclass
class Order:
    """Trade order."""

    id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    qty: Decimal
    status: OrderStatus
    filled_qty: Decimal = Decimal("0")
    filled_avg_price: Optional[Decimal] = None
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    created_at: Optional[str] = None


@dataclass
class Quote:
    """Market quote."""

    symbol: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    volume: int


class Broker(ABC):
    """Abstract broker interface.

    All broker implementations must implement these methods.
    """

    @abstractmethod
    def get_account(self) -> Account:
        """Get account information.

        Returns:
            Account with balance and equity info.
        """
        pass

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """Get all open positions.

        Returns:
            List of open positions.
        """
        pass

    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol.

        Args:
            symbol: Stock symbol.

        Returns:
            Position if exists, None otherwise.
        """
        pass

    @abstractmethod
    def get_quote(self, symbol: str) -> Quote:
        """Get current quote for a symbol.

        Args:
            symbol: Stock symbol.

        Returns:
            Current market quote.
        """
        pass

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        qty: Decimal,
        side: OrderSide,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
    ) -> Order:
        """Place a trade order.

        Args:
            symbol: Stock symbol.
            qty: Number of shares.
            side: Buy or sell.
            order_type: Market, limit, etc.
            limit_price: Limit price for limit orders.
            stop_price: Stop price for stop orders.

        Returns:
            Created order.
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order.

        Args:
            order_id: Order ID to cancel.

        Returns:
            True if canceled, False otherwise.
        """
        pass

    @abstractmethod
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID.

        Args:
            order_id: Order ID.

        Returns:
            Order if found, None otherwise.
        """
        pass

    @abstractmethod
    def get_orders(self, status: Optional[OrderStatus] = None) -> list[Order]:
        """Get orders, optionally filtered by status.

        Args:
            status: Filter by status.

        Returns:
            List of orders.
        """
        pass

    @abstractmethod
    def is_market_open(self) -> bool:
        """Check if market is currently open.

        Returns:
            True if market is open.
        """
        pass
