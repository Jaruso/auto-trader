"""Simple backtesting engine."""

from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional
import random

from trader.rules.models import Rule, RuleAction, RuleCondition
from trader.utils.logging import get_logger


@dataclass
class BacktestTrade:
    """Simulated trade during backtest."""

    timestamp: datetime
    symbol: str
    side: str
    quantity: int
    price: Decimal
    rule_id: str


@dataclass
class BacktestResult:
    """Results from a backtest run."""

    start_date: datetime
    end_date: datetime
    initial_capital: Decimal
    final_capital: Decimal
    total_return: Decimal
    total_return_pct: Decimal
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal
    max_drawdown: Decimal
    trades: list[BacktestTrade] = field(default_factory=list)

    @property
    def profit(self) -> Decimal:
        return self.final_capital - self.initial_capital


class Backtester:
    """Simple backtesting engine using simulated price data."""

    def __init__(self, initial_capital: Decimal = Decimal("100000")) -> None:
        """Initialize backtester.

        Args:
            initial_capital: Starting capital for simulation.
        """
        self.initial_capital = initial_capital
        self.logger = get_logger("autotrader.backtest")

    def run(
        self,
        rules: list[Rule],
        days: int = 30,
        volatility: Decimal = Decimal("0.02"),
    ) -> BacktestResult:
        """Run backtest simulation.

        Args:
            rules: Trading rules to test.
            days: Number of days to simulate.
            volatility: Daily price volatility (default 2%).

        Returns:
            Backtest results.
        """
        if not rules:
            raise ValueError("No rules to backtest")

        # Initialize state
        cash = self.initial_capital
        positions: dict[str, tuple[int, Decimal]] = {}  # symbol -> (qty, avg_price)
        trades: list[BacktestTrade] = []
        equity_curve: list[Decimal] = [self.initial_capital]

        # Generate simulated prices starting from rule targets
        symbols = list(set(r.symbol for r in rules))
        prices: dict[str, Decimal] = {}
        for rule in rules:
            if rule.symbol not in prices:
                # Start price near the target
                offset = Decimal(str(random.uniform(-0.1, 0.1)))
                prices[rule.symbol] = rule.target_price * (1 + offset)

        start_date = datetime.now() - timedelta(days=days)
        end_date = datetime.now()

        # Simulate each day
        for day in range(days):
            current_date = start_date + timedelta(days=day)

            # Update prices with random walk
            for symbol in symbols:
                change = Decimal(str(random.gauss(0, float(volatility))))
                prices[symbol] = prices[symbol] * (1 + change)
                prices[symbol] = max(prices[symbol], Decimal("1"))  # Floor at $1

            # Check rules
            for rule in rules:
                if not rule.enabled:
                    continue

                current_price = prices[rule.symbol]

                # Check if rule triggers
                triggered = False
                if rule.condition == RuleCondition.BELOW and current_price <= rule.target_price:
                    triggered = True
                elif rule.condition == RuleCondition.ABOVE and current_price >= rule.target_price:
                    triggered = True

                if triggered:
                    if rule.action == RuleAction.BUY:
                        # Buy if we have enough cash
                        cost = current_price * rule.quantity
                        if cash >= cost:
                            cash -= cost
                            if rule.symbol in positions:
                                old_qty, old_price = positions[rule.symbol]
                                new_qty = old_qty + rule.quantity
                                new_avg = (old_price * old_qty + current_price * rule.quantity) / new_qty
                                positions[rule.symbol] = (new_qty, new_avg)
                            else:
                                positions[rule.symbol] = (rule.quantity, current_price)

                            trades.append(BacktestTrade(
                                timestamp=current_date,
                                symbol=rule.symbol,
                                side="buy",
                                quantity=rule.quantity,
                                price=current_price,
                                rule_id=rule.id,
                            ))

                    elif rule.action == RuleAction.SELL:
                        # Sell if we have position
                        if rule.symbol in positions:
                            qty, avg_price = positions[rule.symbol]
                            sell_qty = min(qty, rule.quantity)
                            cash += current_price * sell_qty

                            if sell_qty >= qty:
                                del positions[rule.symbol]
                            else:
                                positions[rule.symbol] = (qty - sell_qty, avg_price)

                            trades.append(BacktestTrade(
                                timestamp=current_date,
                                symbol=rule.symbol,
                                side="sell",
                                quantity=sell_qty,
                                price=current_price,
                                rule_id=rule.id,
                            ))

            # Calculate equity
            positions_value = sum(
                prices[s] * Decimal(str(q)) for s, (q, _) in positions.items()
            )
            equity = cash + positions_value
            equity_curve.append(equity)

        # Calculate final metrics
        final_capital = equity_curve[-1]
        total_return = final_capital - self.initial_capital
        total_return_pct = total_return / self.initial_capital

        # Calculate win/loss
        winning = 0
        losing = 0
        # Pair up buys and sells
        buy_prices: dict[str, list[Decimal]] = {}
        for trade in trades:
            if trade.side == "buy":
                if trade.symbol not in buy_prices:
                    buy_prices[trade.symbol] = []
                buy_prices[trade.symbol].append(trade.price)
            elif trade.side == "sell" and trade.symbol in buy_prices and buy_prices[trade.symbol]:
                buy_price = buy_prices[trade.symbol].pop(0)
                if trade.price > buy_price:
                    winning += 1
                else:
                    losing += 1

        total_completed = winning + losing
        win_rate = Decimal(str(winning / total_completed)) if total_completed > 0 else Decimal("0")

        # Calculate max drawdown
        peak = equity_curve[0]
        max_drawdown = Decimal("0")
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        return BacktestResult(
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            total_return=total_return,
            total_return_pct=total_return_pct,
            total_trades=len(trades),
            winning_trades=winning,
            losing_trades=losing,
            win_rate=win_rate,
            max_drawdown=max_drawdown,
            trades=trades,
        )
