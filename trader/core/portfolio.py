"""Portfolio tracking and analysis."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from trader.api.broker import Broker, Position
from trader.data.ledger import TradeLedger


@dataclass
class PortfolioSummary:
    """Summary of portfolio performance."""

    total_equity: Decimal
    cash: Decimal
    positions_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    realized_pnl_today: Decimal
    total_pnl_today: Decimal
    position_count: int


@dataclass
class PositionDetail:
    """Detailed position information."""

    symbol: str
    quantity: Decimal
    avg_cost: Decimal
    current_price: Decimal
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    weight_pct: Decimal  # % of portfolio


class Portfolio:
    """Portfolio tracking and analysis."""

    def __init__(self, broker: Broker, ledger: TradeLedger) -> None:
        """Initialize portfolio tracker.

        Args:
            broker: Broker instance.
            ledger: Trade ledger for P/L calculations.
        """
        self.broker = broker
        self.ledger = ledger

    def get_summary(self) -> PortfolioSummary:
        """Get portfolio summary.

        Returns:
            Portfolio summary with key metrics.
        """
        account = self.broker.get_account()
        positions = self.broker.get_positions()

        positions_value = sum(p.market_value for p in positions)
        unrealized_pnl = sum(p.unrealized_pl for p in positions)

        # Calculate unrealized P/L percentage
        total_cost = sum(p.avg_entry_price * p.qty for p in positions)
        if total_cost > 0:
            unrealized_pnl_pct = unrealized_pnl / total_cost
        else:
            unrealized_pnl_pct = Decimal("0")

        realized_pnl_today = self.ledger.get_total_today_pnl()
        total_pnl_today = unrealized_pnl + realized_pnl_today

        return PortfolioSummary(
            total_equity=account.equity,
            cash=account.cash,
            positions_value=positions_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            realized_pnl_today=realized_pnl_today,
            total_pnl_today=total_pnl_today,
            position_count=len(positions),
        )

    def get_positions_detail(self) -> list[PositionDetail]:
        """Get detailed position breakdown.

        Returns:
            List of position details.
        """
        positions = self.broker.get_positions()
        account = self.broker.get_account()
        total_equity = account.equity

        details = []
        for pos in positions:
            cost_basis = pos.avg_entry_price * pos.qty
            weight = (pos.market_value / total_equity * 100) if total_equity > 0 else Decimal("0")

            details.append(
                PositionDetail(
                    symbol=pos.symbol,
                    quantity=pos.qty,
                    avg_cost=pos.avg_entry_price,
                    current_price=pos.current_price,
                    market_value=pos.market_value,
                    cost_basis=cost_basis,
                    unrealized_pnl=pos.unrealized_pl,
                    unrealized_pnl_pct=pos.unrealized_pl_pct,
                    weight_pct=weight,
                )
            )

        # Sort by market value descending
        details.sort(key=lambda x: x.market_value, reverse=True)
        return details

    def get_allocation(self) -> dict[str, Decimal]:
        """Get portfolio allocation by symbol.

        Returns:
            Dict mapping symbol to percentage of portfolio.
        """
        positions = self.get_positions_detail()
        return {p.symbol: p.weight_pct for p in positions}

    def get_top_gainers(self, limit: int = 5) -> list[PositionDetail]:
        """Get top gaining positions.

        Args:
            limit: Number of positions to return.

        Returns:
            List of top gaining positions.
        """
        positions = self.get_positions_detail()
        gainers = [p for p in positions if p.unrealized_pnl > 0]
        gainers.sort(key=lambda x: x.unrealized_pnl, reverse=True)
        return gainers[:limit]

    def get_top_losers(self, limit: int = 5) -> list[PositionDetail]:
        """Get top losing positions.

        Args:
            limit: Number of positions to return.

        Returns:
            List of top losing positions.
        """
        positions = self.get_positions_detail()
        losers = [p for p in positions if p.unrealized_pnl < 0]
        losers.sort(key=lambda x: x.unrealized_pnl)
        return losers[:limit]
