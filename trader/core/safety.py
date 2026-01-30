"""Safety controls for trading."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from trader.api.broker import Broker
from trader.data.ledger import TradeLedger
from trader.utils.logging import get_logger


@dataclass
class SafetyLimits:
    """Safety limit configuration."""

    max_position_size: int = 100  # Max shares per position
    max_position_value: Decimal = Decimal("10000")  # Max $ per position
    max_daily_loss: Decimal = Decimal("500")  # Max daily loss before stopping
    max_daily_trades: int = 50  # Max trades per day
    max_order_value: Decimal = Decimal("5000")  # Max $ per single order


class SafetyCheck:
    """Safety control checks before executing trades."""

    def __init__(
        self,
        broker: Broker,
        ledger: TradeLedger,
        limits: Optional[SafetyLimits] = None,
    ) -> None:
        """Initialize safety checker.

        Args:
            broker: Broker instance.
            ledger: Trade ledger.
            limits: Safety limits (uses defaults if None).
        """
        self.broker = broker
        self.ledger = ledger
        self.limits = limits or SafetyLimits()
        self.logger = get_logger("autotrader.safety")
        self._killed = False

    def kill(self) -> None:
        """Activate kill switch - stops all trading."""
        self._killed = True
        self.logger.warning("KILL SWITCH ACTIVATED - all trading stopped")

    def reset(self) -> None:
        """Reset kill switch."""
        self._killed = False
        self.logger.info("Kill switch reset")

    @property
    def is_killed(self) -> bool:
        """Check if kill switch is active."""
        return self._killed

    def check_can_trade(self) -> tuple[bool, str]:
        """Check if trading is allowed.

        Returns:
            Tuple of (can_trade, reason).
        """
        if self._killed:
            return False, "Kill switch is active"

        # Check daily loss limit
        daily_pnl = self.ledger.get_total_today_pnl()
        if daily_pnl < -self.limits.max_daily_loss:
            self.logger.warning(
                f"Daily loss limit reached: ${daily_pnl:.2f} (limit: -${self.limits.max_daily_loss})"
            )
            return False, f"Daily loss limit reached: ${daily_pnl:.2f}"

        # Check daily trade count
        trade_count = self.ledger.get_trade_count_today()
        if trade_count >= self.limits.max_daily_trades:
            self.logger.warning(
                f"Daily trade limit reached: {trade_count} (limit: {self.limits.max_daily_trades})"
            )
            return False, f"Daily trade limit reached: {trade_count} trades"

        return True, "OK"

    def check_order(
        self,
        symbol: str,
        quantity: int,
        price: Decimal,
        is_buy: bool,
    ) -> tuple[bool, str]:
        """Check if a specific order is allowed.

        Args:
            symbol: Stock symbol.
            quantity: Number of shares.
            price: Order price.
            is_buy: True if buy order.

        Returns:
            Tuple of (allowed, reason).
        """
        # First check general trading permission
        can_trade, reason = self.check_can_trade()
        if not can_trade:
            return False, reason

        order_value = Decimal(str(quantity)) * price

        # Check order value limit
        if order_value > self.limits.max_order_value:
            return False, f"Order value ${order_value:.2f} exceeds limit ${self.limits.max_order_value}"

        # Check quantity limit
        if quantity > self.limits.max_position_size:
            return False, f"Quantity {quantity} exceeds position size limit {self.limits.max_position_size}"

        # For buys, check position limits
        if is_buy:
            # Check if this would exceed position value limit
            current_position = self.broker.get_position(symbol)
            current_value = Decimal("0")
            if current_position:
                current_value = current_position.market_value

            new_value = current_value + order_value
            if new_value > self.limits.max_position_value:
                return (
                    False,
                    f"Position value ${new_value:.2f} would exceed limit ${self.limits.max_position_value}",
                )

            # Check account has sufficient buying power
            account = self.broker.get_account()
            if order_value > account.buying_power:
                return False, f"Insufficient buying power: need ${order_value:.2f}, have ${account.buying_power:.2f}"

        return True, "OK"

    def get_status(self) -> dict:
        """Get current safety status.

        Returns:
            Dict with safety metrics.
        """
        daily_pnl = self.ledger.get_total_today_pnl()
        trade_count = self.ledger.get_trade_count_today()

        return {
            "kill_switch": self._killed,
            "daily_pnl": daily_pnl,
            "daily_pnl_limit": -self.limits.max_daily_loss,
            "daily_pnl_remaining": self.limits.max_daily_loss + daily_pnl,
            "trade_count": trade_count,
            "trade_limit": self.limits.max_daily_trades,
            "trades_remaining": self.limits.max_daily_trades - trade_count,
            "can_trade": self.check_can_trade()[0],
        }
