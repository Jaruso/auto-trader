"""Tests using mock broker."""

from decimal import Decimal

import pytest

from trader.api.broker import OrderSide, OrderStatus, OrderType, Position
from tests.mocks import MockBroker


@pytest.fixture
def broker() -> MockBroker:
    """Create a mock broker instance."""
    return MockBroker()


def test_get_account(broker: MockBroker) -> None:
    """Test getting mock account."""
    account = broker.get_account()
    assert account.cash == Decimal("100000.00")
    assert account.buying_power == Decimal("200000.00")
    assert account.equity == Decimal("100000.00")


def test_get_quote(broker: MockBroker) -> None:
    """Test getting mock quote."""
    quote = broker.get_quote("AAPL")
    assert quote.symbol == "AAPL"
    assert quote.bid == Decimal("174.50")
    assert quote.ask == Decimal("175.00")


def test_get_quote_unknown_symbol(broker: MockBroker) -> None:
    """Test getting quote for unknown symbol returns default."""
    quote = broker.get_quote("UNKNOWN")
    assert quote.symbol == "UNKNOWN"
    assert quote.bid == Decimal("100.00")


def test_place_market_order(broker: MockBroker) -> None:
    """Test placing a market order."""
    order = broker.place_order(
        symbol="AAPL",
        qty=Decimal("10"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
    )
    assert order.symbol == "AAPL"
    assert order.qty == Decimal("10")
    assert order.status == OrderStatus.FILLED
    assert order.filled_qty == Decimal("10")


def test_place_limit_order(broker: MockBroker) -> None:
    """Test placing a limit order."""
    order = broker.place_order(
        symbol="AAPL",
        qty=Decimal("10"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("170.00"),
    )
    assert order.status == OrderStatus.NEW
    assert order.filled_qty == Decimal("0")
    assert order.limit_price == Decimal("170.00")


def test_cancel_order(broker: MockBroker) -> None:
    """Test canceling an order."""
    order = broker.place_order(
        symbol="AAPL",
        qty=Decimal("10"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("170.00"),
    )
    assert broker.cancel_order(order.id) is True
    canceled = broker.get_order(order.id)
    assert canceled is not None
    assert canceled.status == OrderStatus.CANCELED


def test_cancel_nonexistent_order(broker: MockBroker) -> None:
    """Test canceling non-existent order returns False."""
    assert broker.cancel_order("fake-id") is False


def test_get_positions_empty(broker: MockBroker) -> None:
    """Test getting positions when none exist."""
    positions = broker.get_positions()
    assert positions == []


def test_market_order_creates_position(broker: MockBroker) -> None:
    """Test that market order creates a position."""
    broker.place_order(
        symbol="AAPL",
        qty=Decimal("10"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
    )
    positions = broker.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert positions[0].qty == Decimal("10")


def test_is_market_open(broker: MockBroker) -> None:
    """Test market open status."""
    assert broker.is_market_open() is True
    broker.set_market_open(False)
    assert broker.is_market_open() is False


def test_add_position(broker: MockBroker) -> None:
    """Test adding a position directly."""
    position = Position(
        symbol="TSLA",
        qty=Decimal("5"),
        avg_entry_price=Decimal("200.00"),
        current_price=Decimal("210.00"),
        market_value=Decimal("1050.00"),
        unrealized_pl=Decimal("50.00"),
        unrealized_pl_pct=Decimal("0.05"),
    )
    broker.add_position(position)
    pos = broker.get_position("TSLA")
    assert pos is not None
    assert pos.symbol == "TSLA"
    assert pos.qty == Decimal("5")


def test_get_orders(broker: MockBroker) -> None:
    """Test getting all orders."""
    broker.place_order("AAPL", Decimal("10"), OrderSide.BUY)
    broker.place_order("GOOGL", Decimal("5"), OrderSide.BUY)

    orders = broker.get_orders()
    assert len(orders) == 2


def test_get_orders_filtered(broker: MockBroker) -> None:
    """Test getting orders filtered by status."""
    broker.place_order("AAPL", Decimal("10"), OrderSide.BUY, OrderType.MARKET)
    broker.place_order("GOOGL", Decimal("5"), OrderSide.BUY, OrderType.LIMIT, Decimal("130.00"))

    filled = broker.get_orders(status=OrderStatus.FILLED)
    assert len(filled) == 1
    assert filled[0].symbol == "AAPL"

    pending = broker.get_orders(status=OrderStatus.NEW)
    assert len(pending) == 1
    assert pending[0].symbol == "GOOGL"
