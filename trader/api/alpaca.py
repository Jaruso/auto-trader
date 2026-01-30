"""Alpaca broker implementation."""

from decimal import Decimal
from typing import Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide as AlpacaOrderSide
from alpaca.trading.enums import OrderStatus as AlpacaOrderStatus
from alpaca.trading.enums import OrderType as AlpacaOrderType
from alpaca.trading.enums import TimeInForce
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
    StopLimitOrderRequest,
    StopOrderRequest,
)
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

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


class AlpacaBroker(Broker):
    """Alpaca broker implementation."""

    def __init__(self, api_key: str, secret_key: str, paper: bool = True) -> None:
        """Initialize Alpaca broker.

        Args:
            api_key: Alpaca API key.
            secret_key: Alpaca secret key.
            paper: Use paper trading (default True).
        """
        self.paper = paper
        self.trading_client = TradingClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=paper,
        )
        self.data_client = StockHistoricalDataClient(
            api_key=api_key,
            secret_key=secret_key,
        )

    def get_account(self) -> Account:
        """Get account information."""
        account = self.trading_client.get_account()
        return Account(
            cash=Decimal(str(account.cash)),
            buying_power=Decimal(str(account.buying_power)),
            equity=Decimal(str(account.equity)),
            currency=account.currency or "USD",
        )

    def get_positions(self) -> list[Position]:
        """Get all open positions."""
        positions = self.trading_client.get_all_positions()
        return [self._convert_position(p) for p in positions]

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol."""
        try:
            position = self.trading_client.get_open_position(symbol)
            return self._convert_position(position)
        except Exception:
            return None

    def get_quote(self, symbol: str) -> Quote:
        """Get current quote for a symbol."""
        request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        quotes = self.data_client.get_stock_latest_quote(request)
        quote = quotes[symbol]

        return Quote(
            symbol=symbol,
            bid=Decimal(str(quote.bid_price)),
            ask=Decimal(str(quote.ask_price)),
            last=Decimal(str(quote.ask_price)),  # Use ask as proxy for last
            volume=0,  # Not available in latest quote
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
        """Place a trade order."""
        alpaca_side = (
            AlpacaOrderSide.BUY if side == OrderSide.BUY else AlpacaOrderSide.SELL
        )

        if order_type == OrderType.MARKET:
            request = MarketOrderRequest(
                symbol=symbol,
                qty=float(qty),
                side=alpaca_side,
                time_in_force=TimeInForce.DAY,
            )
        elif order_type == OrderType.LIMIT:
            if limit_price is None:
                raise ValueError("Limit price required for limit orders")
            request = LimitOrderRequest(
                symbol=symbol,
                qty=float(qty),
                side=alpaca_side,
                time_in_force=TimeInForce.DAY,
                limit_price=float(limit_price),
            )
        elif order_type == OrderType.STOP:
            if stop_price is None:
                raise ValueError("Stop price required for stop orders")
            request = StopOrderRequest(
                symbol=symbol,
                qty=float(qty),
                side=alpaca_side,
                time_in_force=TimeInForce.DAY,
                stop_price=float(stop_price),
            )
        elif order_type == OrderType.STOP_LIMIT:
            if limit_price is None or stop_price is None:
                raise ValueError("Limit and stop price required for stop-limit orders")
            request = StopLimitOrderRequest(
                symbol=symbol,
                qty=float(qty),
                side=alpaca_side,
                time_in_force=TimeInForce.DAY,
                limit_price=float(limit_price),
                stop_price=float(stop_price),
            )
        else:
            raise ValueError(f"Unsupported order type: {order_type}")

        order = self.trading_client.submit_order(request)
        return self._convert_order(order)

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        try:
            self.trading_client.cancel_order_by_id(order_id)
            return True
        except Exception:
            return False

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID."""
        try:
            order = self.trading_client.get_order_by_id(order_id)
            return self._convert_order(order)
        except Exception:
            return None

    def get_orders(self, status: Optional[OrderStatus] = None) -> list[Order]:
        """Get orders, optionally filtered by status."""
        request = GetOrdersRequest()
        if status:
            request.status = self._convert_order_status_to_alpaca(status)

        orders = self.trading_client.get_orders(request)
        return [self._convert_order(o) for o in orders]

    def is_market_open(self) -> bool:
        """Check if market is currently open."""
        clock = self.trading_client.get_clock()
        return clock.is_open

    def _convert_position(self, position: object) -> Position:
        """Convert Alpaca position to our Position model."""
        return Position(
            symbol=position.symbol,  # type: ignore
            qty=Decimal(str(position.qty)),  # type: ignore
            avg_entry_price=Decimal(str(position.avg_entry_price)),  # type: ignore
            current_price=Decimal(str(position.current_price)),  # type: ignore
            market_value=Decimal(str(position.market_value)),  # type: ignore
            unrealized_pl=Decimal(str(position.unrealized_pl)),  # type: ignore
            unrealized_pl_pct=Decimal(str(position.unrealized_plpc)),  # type: ignore
        )

    def _convert_order(self, order: object) -> Order:
        """Convert Alpaca order to our Order model."""
        return Order(
            id=str(order.id),  # type: ignore
            symbol=order.symbol,  # type: ignore
            side=OrderSide.BUY if order.side == AlpacaOrderSide.BUY else OrderSide.SELL,  # type: ignore
            order_type=self._convert_order_type(order.order_type),  # type: ignore
            qty=Decimal(str(order.qty)),  # type: ignore
            status=self._convert_order_status(order.status),  # type: ignore
            filled_qty=Decimal(str(order.filled_qty or 0)),  # type: ignore
            filled_avg_price=(
                Decimal(str(order.filled_avg_price))  # type: ignore
                if order.filled_avg_price  # type: ignore
                else None
            ),
            limit_price=(
                Decimal(str(order.limit_price)) if order.limit_price else None  # type: ignore
            ),
            stop_price=(
                Decimal(str(order.stop_price)) if order.stop_price else None  # type: ignore
            ),
            created_at=str(order.created_at) if order.created_at else None,  # type: ignore
        )

    def _convert_order_type(self, order_type: AlpacaOrderType) -> OrderType:
        """Convert Alpaca order type to our OrderType."""
        mapping = {
            AlpacaOrderType.MARKET: OrderType.MARKET,
            AlpacaOrderType.LIMIT: OrderType.LIMIT,
            AlpacaOrderType.STOP: OrderType.STOP,
            AlpacaOrderType.STOP_LIMIT: OrderType.STOP_LIMIT,
        }
        return mapping.get(order_type, OrderType.MARKET)

    def _convert_order_status(self, status: AlpacaOrderStatus) -> OrderStatus:
        """Convert Alpaca order status to our OrderStatus."""
        mapping = {
            AlpacaOrderStatus.NEW: OrderStatus.NEW,
            AlpacaOrderStatus.PENDING_NEW: OrderStatus.PENDING,
            AlpacaOrderStatus.ACCEPTED: OrderStatus.ACCEPTED,
            AlpacaOrderStatus.FILLED: OrderStatus.FILLED,
            AlpacaOrderStatus.PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
            AlpacaOrderStatus.CANCELED: OrderStatus.CANCELED,
            AlpacaOrderStatus.REJECTED: OrderStatus.REJECTED,
            AlpacaOrderStatus.EXPIRED: OrderStatus.EXPIRED,
        }
        return mapping.get(status, OrderStatus.NEW)

    def _convert_order_status_to_alpaca(
        self, status: OrderStatus
    ) -> AlpacaOrderStatus:
        """Convert our OrderStatus to Alpaca status."""
        mapping = {
            OrderStatus.NEW: AlpacaOrderStatus.NEW,
            OrderStatus.PENDING: AlpacaOrderStatus.PENDING_NEW,
            OrderStatus.ACCEPTED: AlpacaOrderStatus.ACCEPTED,
            OrderStatus.FILLED: AlpacaOrderStatus.FILLED,
            OrderStatus.PARTIALLY_FILLED: AlpacaOrderStatus.PARTIALLY_FILLED,
            OrderStatus.CANCELED: AlpacaOrderStatus.CANCELED,
            OrderStatus.REJECTED: AlpacaOrderStatus.REJECTED,
            OrderStatus.EXPIRED: AlpacaOrderStatus.EXPIRED,
        }
        return mapping.get(status, AlpacaOrderStatus.NEW)
