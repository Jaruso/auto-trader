"""Tests for broker module."""

from decimal import Decimal

import pytest

from trader.api.broker import (
    Account,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Quote,
)


def test_account_model() -> None:
    """Test Account dataclass."""
    account = Account(
        cash=Decimal("10000.00"),
        buying_power=Decimal("20000.00"),
        equity=Decimal("15000.00"),
        currency="USD",
    )
    assert account.cash == Decimal("10000.00")
    assert account.buying_power == Decimal("20000.00")
    assert account.equity == Decimal("15000.00")
    assert account.currency == "USD"


def test_position_model() -> None:
    """Test Position dataclass."""
    position = Position(
        symbol="AAPL",
        qty=Decimal("10"),
        avg_entry_price=Decimal("150.00"),
        current_price=Decimal("155.00"),
        market_value=Decimal("1550.00"),
        unrealized_pl=Decimal("50.00"),
        unrealized_pl_pct=Decimal("0.0333"),
    )
    assert position.symbol == "AAPL"
    assert position.qty == Decimal("10")
    assert position.unrealized_pl == Decimal("50.00")


def test_order_model() -> None:
    """Test Order dataclass."""
    order = Order(
        id="abc123",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        qty=Decimal("10"),
        status=OrderStatus.NEW,
        limit_price=Decimal("150.00"),
    )
    assert order.id == "abc123"
    assert order.side == OrderSide.BUY
    assert order.order_type == OrderType.LIMIT
    assert order.status == OrderStatus.NEW


def test_quote_model() -> None:
    """Test Quote dataclass."""
    quote = Quote(
        symbol="AAPL",
        bid=Decimal("154.50"),
        ask=Decimal("155.00"),
        last=Decimal("154.75"),
        volume=1000000,
    )
    assert quote.symbol == "AAPL"
    assert quote.ask - quote.bid == Decimal("0.50")


def test_order_side_enum() -> None:
    """Test OrderSide enum."""
    assert OrderSide.BUY.value == "buy"
    assert OrderSide.SELL.value == "sell"


def test_order_type_enum() -> None:
    """Test OrderType enum."""
    assert OrderType.MARKET.value == "market"
    assert OrderType.LIMIT.value == "limit"
    assert OrderType.STOP.value == "stop"
    assert OrderType.STOP_LIMIT.value == "stop_limit"


def test_order_status_enum() -> None:
    """Test OrderStatus enum."""
    assert OrderStatus.NEW.value == "new"
    assert OrderStatus.FILLED.value == "filled"
    assert OrderStatus.CANCELED.value == "canceled"
