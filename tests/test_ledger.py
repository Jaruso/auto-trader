"""Tests for trade ledger."""

import tempfile
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trader.api.broker import OrderSide, OrderStatus
from trader.data.ledger import TradeLedger, TradeRecord


@pytest.fixture
def temp_db():
    """Create temporary database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_trades.db"


@pytest.fixture
def ledger(temp_db: Path) -> TradeLedger:
    """Create ledger with temporary database."""
    return TradeLedger(db_path=temp_db)


def test_ledger_init(temp_db: Path) -> None:
    """Test ledger initialization creates database."""
    ledger = TradeLedger(db_path=temp_db)
    assert temp_db.exists()


def test_record_trade(ledger: TradeLedger) -> None:
    """Test recording a trade."""
    trade_id = ledger.record_trade(
        order_id="order-123",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("150.00"),
        status=OrderStatus.FILLED,
    )
    assert trade_id > 0


def test_get_trades(ledger: TradeLedger) -> None:
    """Test getting trades."""
    # Record some trades
    ledger.record_trade(
        order_id="order-1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("150.00"),
        status=OrderStatus.FILLED,
    )
    ledger.record_trade(
        order_id="order-2",
        symbol="TSLA",
        side=OrderSide.BUY,
        quantity=Decimal("5"),
        price=Decimal("200.00"),
        status=OrderStatus.FILLED,
    )

    trades = ledger.get_trades()
    assert len(trades) == 2


def test_get_trades_filter_by_symbol(ledger: TradeLedger) -> None:
    """Test filtering trades by symbol."""
    ledger.record_trade(
        order_id="order-1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("150.00"),
        status=OrderStatus.FILLED,
    )
    ledger.record_trade(
        order_id="order-2",
        symbol="TSLA",
        side=OrderSide.BUY,
        quantity=Decimal("5"),
        price=Decimal("200.00"),
        status=OrderStatus.FILLED,
    )

    aapl_trades = ledger.get_trades(symbol="AAPL")
    assert len(aapl_trades) == 1
    assert aapl_trades[0].symbol == "AAPL"


def test_get_trades_filter_by_date(ledger: TradeLedger) -> None:
    """Test filtering trades by date."""
    # Record a trade from yesterday
    yesterday = datetime.now() - timedelta(days=1)
    ledger.record_trade(
        order_id="order-1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("150.00"),
        status=OrderStatus.FILLED,
        timestamp=yesterday,
    )

    # Record a trade from today
    ledger.record_trade(
        order_id="order-2",
        symbol="TSLA",
        side=OrderSide.BUY,
        quantity=Decimal("5"),
        price=Decimal("200.00"),
        status=OrderStatus.FILLED,
    )

    # Get trades from today only
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_trades = ledger.get_trades(since=today)
    assert len(today_trades) == 1
    assert today_trades[0].symbol == "TSLA"


def test_trade_record_properties() -> None:
    """Test TradeRecord properties."""
    record = TradeRecord(
        id=1,
        order_id="order-123",
        symbol="AAPL",
        side="buy",
        quantity=Decimal("10"),
        price=Decimal("150.00"),
        total=Decimal("1500.00"),
        status="filled",
        rule_id=None,
        timestamp=datetime.now(),
    )
    assert record.is_buy is True
    assert record.is_sell is False

    sell_record = TradeRecord(
        id=2,
        order_id="order-456",
        symbol="AAPL",
        side="sell",
        quantity=Decimal("10"),
        price=Decimal("160.00"),
        total=Decimal("1600.00"),
        status="filled",
        rule_id=None,
        timestamp=datetime.now(),
    )
    assert sell_record.is_buy is False
    assert sell_record.is_sell is True


def test_get_today_trades(ledger: TradeLedger) -> None:
    """Test getting today's trades."""
    # Record a trade
    ledger.record_trade(
        order_id="order-1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("150.00"),
        status=OrderStatus.FILLED,
    )

    today_trades = ledger.get_today_trades()
    assert len(today_trades) == 1


def test_get_trade_count_today(ledger: TradeLedger) -> None:
    """Test counting today's trades."""
    assert ledger.get_trade_count_today() == 0

    ledger.record_trade(
        order_id="order-1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("150.00"),
        status=OrderStatus.FILLED,
    )

    assert ledger.get_trade_count_today() == 1


def test_get_today_pnl_no_trades(ledger: TradeLedger) -> None:
    """Test P/L with no trades."""
    pnl = ledger.get_today_pnl()
    assert pnl == {}


def test_get_total_today_pnl(ledger: TradeLedger) -> None:
    """Test total P/L calculation."""
    # Buy then sell for profit
    ledger.record_trade(
        order_id="order-1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("150.00"),
        status=OrderStatus.FILLED,
    )
    ledger.record_trade(
        order_id="order-2",
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=Decimal("10"),
        price=Decimal("160.00"),
        status=OrderStatus.FILLED,
    )

    total_pnl = ledger.get_total_today_pnl()
    assert total_pnl == Decimal("100.00")  # 10 * (160 - 150)


def test_export_csv(ledger: TradeLedger, temp_db: Path) -> None:
    """Test CSV export."""
    ledger.record_trade(
        order_id="order-1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("150.00"),
        status=OrderStatus.FILLED,
    )

    csv_path = temp_db.parent / "export.csv"
    count = ledger.export_csv(csv_path)

    assert count == 1
    assert csv_path.exists()

    content = csv_path.read_text()
    assert "AAPL" in content
    assert "150" in content


def test_record_trade_with_rule_id(ledger: TradeLedger) -> None:
    """Test recording trade with rule ID."""
    trade_id = ledger.record_trade(
        order_id="order-123",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("150.00"),
        status=OrderStatus.FILLED,
        rule_id="rule-abc",
    )

    trades = ledger.get_trades()
    assert trades[0].rule_id == "rule-abc"
