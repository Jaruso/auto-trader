"""Mock broker for testing."""

from decimal import Decimal
from typing import Optional

from trader.api.broker import (
    Account,
    Broker,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Quote,
)


class MockBroker(Broker):
    """Mock broker for testing."""

    def __init__(self) -> None:
        """Initialize mock broker with test data."""
        self._account = Account(
            cash=Decimal("100000.00"),
            buying_power=Decimal("200000.00"),
            equity=Decimal("100000.00"),
            currency="USD",
        )
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, Order] = {}
        self._quotes: dict[str, Quote] = {
            "AAPL": Quote(
                symbol="AAPL",
                bid=Decimal("174.50"),
                ask=Decimal("175.00"),
                last=Decimal("174.75"),
                volume=50000000,
            ),
            "GOOGL": Quote(
                symbol="GOOGL",
                bid=Decimal("140.00"),
                ask=Decimal("140.50"),
                last=Decimal("140.25"),
                volume=20000000,
            ),
        }
        self._market_open = True
        self._next_order_id = 1

    def get_account(self) -> Account:
        """Get mock account."""
        return self._account

    def get_positions(self) -> list[Position]:
        """Get all mock positions."""
        return list(self._positions.values())

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get mock position for symbol."""
        return self._positions.get(symbol)

    def get_quote(self, symbol: str) -> Quote:
        """Get mock quote."""
        if symbol in self._quotes:
            return self._quotes[symbol]
        # Return a default quote for unknown symbols
        return Quote(
            symbol=symbol,
            bid=Decimal("100.00"),
            ask=Decimal("100.50"),
            last=Decimal("100.25"),
            volume=1000000,
        )

    def place_order(
        self,
        symbol: str,
        qty: Decimal,
        side: OrderSide,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
    ) -> Order:
        """Place a mock order."""
        order_id = f"mock-{self._next_order_id}"
        self._next_order_id += 1

        order = Order(
            id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            qty=qty,
            status=OrderStatus.FILLED if order_type == OrderType.MARKET else OrderStatus.NEW,
            filled_qty=qty if order_type == OrderType.MARKET else Decimal("0"),
            limit_price=limit_price,
            stop_price=stop_price,
        )
        self._orders[order_id] = order

        # Update positions for filled orders
        if order.status == OrderStatus.FILLED:
            self._update_position(order)

        return order

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a mock order."""
        if order_id in self._orders:
            self._orders[order_id].status = OrderStatus.CANCELED
            return True
        return False

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get mock order by ID."""
        return self._orders.get(order_id)

    def get_orders(self, status: Optional[OrderStatus] = None) -> list[Order]:
        """Get mock orders."""
        orders = list(self._orders.values())
        if status:
            orders = [o for o in orders if o.status == status]
        return orders

    def is_market_open(self) -> bool:
        """Check if mock market is open."""
        return self._market_open

    def set_market_open(self, is_open: bool) -> None:
        """Set mock market open status."""
        self._market_open = is_open

    def add_position(self, position: Position) -> None:
        """Add a mock position."""
        self._positions[position.symbol] = position

    def _update_position(self, order: Order) -> None:
        """Update positions based on filled order."""
        quote = self.get_quote(order.symbol)
        current_price = quote.last

        if order.symbol in self._positions:
            pos = self._positions[order.symbol]
            if order.side == OrderSide.BUY:
                new_qty = pos.qty + order.filled_qty
                new_avg = (pos.avg_entry_price * pos.qty + current_price * order.filled_qty) / new_qty
            else:
                new_qty = pos.qty - order.filled_qty
                new_avg = pos.avg_entry_price

            if new_qty > 0:
                self._positions[order.symbol] = Position(
                    symbol=order.symbol,
                    qty=new_qty,
                    avg_entry_price=new_avg,
                    current_price=current_price,
                    market_value=new_qty * current_price,
                    unrealized_pl=(current_price - new_avg) * new_qty,
                    unrealized_pl_pct=(current_price - new_avg) / new_avg,
                )
            else:
                del self._positions[order.symbol]
        else:
            if order.side == OrderSide.BUY:
                self._positions[order.symbol] = Position(
                    symbol=order.symbol,
                    qty=order.filled_qty,
                    avg_entry_price=current_price,
                    current_price=current_price,
                    market_value=order.filled_qty * current_price,
                    unrealized_pl=Decimal("0"),
                    unrealized_pl_pct=Decimal("0"),
                )
