"""Portfolio, account, positions, and quote service functions."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, cast

from kodiak.app import get_broker
from kodiak.backtest.data import load_data_for_backtest
from kodiak.errors import BrokerError
from kodiak.errors import ValidationError as AppValidationError
from kodiak.schemas.portfolio import (
    AccountInfo,
    BalanceResponse,
    PortfolioAnalyticsResponse,
    PortfolioResponse,
    PositionInfo,
    PositionSizingRequest,
    PositionSizingResponse,
    QuoteResponse,
    RebalancePlanResponse,
    RebalanceRequest,
)
from kodiak.strategies.loader import load_strategies
from kodiak.utils.config import Config


def _wrap_broker_error(action: str, exc: Exception) -> BrokerError:
    """Normalize broker/network failures into app-layer errors."""
    return BrokerError(
        message=f"Failed to {action}: {exc}",
        code="BROKER_FETCH_FAILED",
    )


def get_balance(config: Config) -> BalanceResponse:
    """Get account balance overview.

    Args:
        config: Application configuration.

    Returns:
        Balance response with account, positions, and market status.

    Raises:
        ConfigurationError: If API keys not configured.
        BrokerError: If broker call fails.
    """
    try:
        broker = get_broker(config)
        account = broker.get_account()
        positions_list = broker.get_positions()
        market_open = broker.is_market_open()
    except Exception as e:
        if "ConfigurationError" in type(e).__name__:
            raise
        raise BrokerError(
            message=f"Failed to fetch account data: {e}",
            code="BROKER_FETCH_FAILED",
        )

    total_value = sum((p.market_value for p in positions_list), Decimal("0"))
    total_pl = sum((p.unrealized_pl for p in positions_list), Decimal("0"))

    day_change = None
    day_change_pct = None
    if account.last_equity:
        day_change = account.equity - account.last_equity
        day_change_pct = (
            (day_change / account.last_equity) * 100 if account.last_equity else Decimal("0")
        )

    return BalanceResponse(
        account=AccountInfo.from_domain(account),
        positions=[PositionInfo.from_domain(p) for p in positions_list],
        market_open=market_open,
        total_positions_value=total_value,
        total_unrealized_pl=total_pl,
        day_change=day_change,
        day_change_pct=day_change_pct,
    )


def get_positions(config: Config) -> list[PositionInfo]:
    """Get open positions.

    Args:
        config: Application configuration.

    Returns:
        List of position info schemas.
    """
    broker = get_broker(config)
    try:
        positions_list = broker.get_positions()
    except Exception as e:
        if "ConfigurationError" in type(e).__name__:
            raise
        raise _wrap_broker_error("fetch positions", e)
    return [PositionInfo.from_domain(p) for p in positions_list]


def get_portfolio_summary(config: Config) -> PortfolioResponse:
    """Get portfolio summary with detailed position breakdown.

    Args:
        config: Application configuration.

    Returns:
        Portfolio response schema.
    """
    from kodiak.core.portfolio import Portfolio
    from kodiak.data.ledger import TradeLedger

    broker = get_broker(config)
    ledger = TradeLedger()
    pf = Portfolio(broker, ledger)

    try:
        summary = pf.get_summary()
        positions = pf.get_positions_detail()
    except Exception as e:
        if "ConfigurationError" in type(e).__name__:
            raise
        raise _wrap_broker_error("fetch portfolio summary", e)

    return PortfolioResponse.from_domain(summary, positions)


def get_quote(config: Config, symbol: str) -> QuoteResponse:
    """Get current market quote.

    Args:
        config: Application configuration.
        symbol: Stock symbol.

    Returns:
        Quote response schema.
    """
    broker = get_broker(config)
    try:
        q = broker.get_quote(symbol.upper())
    except Exception as e:
        if "ConfigurationError" in type(e).__name__:
            raise
        raise _wrap_broker_error(f"fetch quote for {symbol.upper()}", e)
    return QuoteResponse.from_domain(q)


def get_portfolio_analytics(
    config: Config,
    lookback_days: int = 252,
    benchmark_symbol: str = "SPY",
    end_date: date | None = None,
) -> PortfolioAnalyticsResponse:
    """Get portfolio analytics versus a benchmark."""
    from kodiak.analysis.portfolio import (
        compute_portfolio_analytics,
        compute_transaction_portfolio_analytics,
    )
    from kodiak.data.ledger import TradeLedger

    if lookback_days < 1:
        raise AppValidationError(
            message="lookback_days must be at least 1",
            details={"lookback_days": lookback_days},
            suggestion="Use a positive number of trading days such as 30, 63, or 252.",
        )

    broker = get_broker(config)
    try:
        account = broker.get_account()
        positions = broker.get_positions()
    except Exception as e:
        if "ConfigurationError" in type(e).__name__:
            raise
        raise _wrap_broker_error("fetch account and positions for portfolio analytics", e)

    history_end = datetime.combine(end_date, time.max) if end_date else datetime.now()
    # Over-fetch calendar days so we can still get enough trading sessions.
    history_start = history_end - timedelta(days=max(lookback_days * 2, 30))

    ledger = TradeLedger()
    trades = ledger.get_trades(since=history_start, limit=100000)
    symbols = sorted(
        {position.symbol.upper() for position in positions}
        | {trade.symbol.upper() for trade in trades}
    )
    benchmark_symbol = benchmark_symbol.upper()
    history_symbols = list(dict.fromkeys([*symbols, benchmark_symbol]))

    try:
        history, selected_source, load_attempts = _load_portfolio_history(
            config=config,
            symbols=history_symbols,
            start_date=history_start,
            end_date=history_end,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise AppValidationError(
            message="Portfolio analytics requires historical price data for the current holdings and benchmark.",
            code="PORTFOLIO_ANALYTICS_DATA_UNAVAILABLE",
            details={
                "symbols": history_symbols,
                "benchmark_symbol": benchmark_symbol,
                "data_source": config.data.source,
                "load_attempts": getattr(exc, "attempts", []),
                "reason": str(exc),
            },
            suggestion=(
                "Provide matching historical data, enable Alpaca market data credentials, "
                "or pass an end_date that matches the available dataset."
            ),
        )

    try:
        if trades:
            analytics = compute_transaction_portfolio_analytics(
                account=account,
                positions=positions,
                trades=trades,
                price_history=history,
                benchmark_symbol=benchmark_symbol,
                data_source=selected_source,
                lookback_days=lookback_days,
            )
        else:
            analytics = compute_portfolio_analytics(
                account=account,
                positions=positions,
                price_history=history,
                benchmark_symbol=benchmark_symbol,
                data_source=selected_source,
                lookback_days=lookback_days,
            )
    except ValueError as exc:
        raise AppValidationError(
            message=str(exc),
            code="PORTFOLIO_ANALYTICS_INVALID_HISTORY",
            details={
                "symbols": history_symbols,
                "benchmark_symbol": benchmark_symbol,
                "data_source": selected_source,
                "load_attempts": load_attempts,
            },
            suggestion="Use a longer dataset or shorten lookback_days so at least two aligned observations remain.",
        )

    return PortfolioAnalyticsResponse.from_domain(analytics)


def _load_portfolio_history(
    *,
    config: Config,
    symbols: Sequence[str],
    start_date: datetime,
    end_date: datetime,
) -> tuple[dict[str, Any], str, list[dict[str, str]]]:
    attempts: list[dict[str, str]] = []
    sources: list[tuple[str, dict[str, Any]]] = [
        (
            config.data.source,
            {
                "data_dir": config.data.csv_dir if config.data.source.lower() == "csv" else None,
            },
        )
    ]

    if config.data.source.lower() != "alpaca" and config.alpaca_api_key and config.alpaca_secret_key:
        sources.append(("alpaca", {"data_dir": None}))

    last_error: Exception | None = None
    for source_name, source_kwargs in sources:
        try:
            history = load_data_for_backtest(
                symbols=list(symbols),
                start_date=start_date,
                end_date=end_date,
                data_source=source_name,
                data_dir=source_kwargs["data_dir"],
                config=config,
            )
            return history, source_name, attempts
        except (FileNotFoundError, ValueError) as exc:
            last_error = exc
            attempts.append({"source": source_name, "reason": str(exc)})

    if last_error is None:
        last_error = ValueError("No historical data source candidates were available.")
    setattr(last_error, "attempts", attempts)
    raise last_error


def calculate_position_size_app(
    config: Config,
    request: PositionSizingRequest,
) -> PositionSizingResponse:
    """Calculate a recommended target size for a symbol."""
    from kodiak.analysis.allocation import calculate_position_size

    broker = get_broker(config)
    symbol = request.symbol.upper()
    try:
        account = broker.get_account()
        current_position = broker.get_position(symbol)
        if request.price is not None:
            reference_price = request.price
        elif current_position:
            reference_price = current_position.current_price
        else:
            reference_price = broker.get_quote(symbol).last
    except Exception as e:
        if "ConfigurationError" in type(e).__name__:
            raise
        raise _wrap_broker_error(f"fetch sizing inputs for {symbol}", e)

    try:
        result = calculate_position_size(
            symbol=symbol,
            method=request.method,
            reference_price=reference_price,
            account=account,
            current_qty=current_position.qty if current_position else Decimal("0"),
            target_value=request.target_value,
            target_weight_pct=request.target_weight_pct,
            risk_budget=request.risk_budget,
            stop_loss_pct=request.stop_loss_pct,
            available_capital=request.available_capital,
            max_position_value=request.max_position_value,
            max_position_weight_pct=request.max_position_weight_pct,
            lot_size=request.lot_size,
        )
    except ValueError as exc:
        raise AppValidationError(
            message=str(exc),
            code="POSITION_SIZING_INVALID",
        )

    return PositionSizingResponse.from_domain(result)


def get_rebalance_plan_app(
    config: Config,
    request: RebalanceRequest,
) -> RebalancePlanResponse:
    """Generate a dry-run rebalance plan."""
    from kodiak.analysis.allocation import generate_rebalance_plan

    broker = get_broker(config)
    try:
        account = broker.get_account()
        positions = broker.get_positions()
    except Exception as e:
        if "ConfigurationError" in type(e).__name__:
            raise
        raise _wrap_broker_error("fetch account and positions for rebalance planning", e)

    target_symbols = {symbol.upper() for symbol in request.target_weights}
    missing_symbols = sorted(target_symbols - {position.symbol.upper() for position in positions})
    reference_prices: dict[str, Decimal] = {}
    try:
        for symbol in missing_symbols:
            reference_prices[symbol] = broker.get_quote(symbol).last
    except Exception as e:
        if "ConfigurationError" in type(e).__name__:
            raise
        raise _wrap_broker_error("fetch quotes for rebalance planning", e)

    try:
        plan = generate_rebalance_plan(
            account=account,
            current_positions=positions,
            target_weights={symbol.upper(): weight for symbol, weight in request.target_weights.items()},
            reference_prices=reference_prices,
            drift_threshold_pct=request.drift_threshold_pct,
            cash_buffer_pct=request.cash_buffer_pct,
            liquidate_unmentioned=request.liquidate_unmentioned,
            lot_size=request.lot_size,
            max_position_weight_pct=request.max_position_weight_pct,
        )
    except ValueError as exc:
        raise AppValidationError(
            message=str(exc),
            code="REBALANCE_PLAN_INVALID",
        )

    return RebalancePlanResponse.from_domain(plan)


def scan_symbols(
    config: Config,
    symbols: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Scan symbols for current prices and strategy info.

    Args:
        config: Application configuration.
        symbols: List of symbols to scan. If None, uses strategy symbols.

    Returns:
        List of dicts with symbol scan data.
    """
    broker = get_broker(config)
    strategies = load_strategies()

    if not symbols:
        symbols = list(set(s.symbol for s in strategies))

    if not symbols:
        return []

    results = []
    for symbol in symbols:
        symbol = symbol.upper()
        try:
            q = broker.get_quote(symbol)
            mid = (q.bid + q.ask) / 2
            spread = q.ask - q.bid
            spread_pct = (spread / mid * 100) if mid > 0 else Decimal("0")

            symbol_strategies = [s for s in strategies if s.symbol == symbol]
            strat_strs = [
                f"{s.strategy_type.value}: {s.phase.value}"
                for s in symbol_strategies
            ]

            results.append({
                "symbol": symbol,
                "bid": str(q.bid),
                "ask": str(q.ask),
                "spread": str(spread),
                "spread_pct": str(spread_pct),
                "strategies": strat_strs,
            })
        except Exception as e:
            results.append({
                "symbol": symbol,
                "error": str(e),
            })

    return results


def watch_strategies(config: Config) -> list[dict[str, Any]]:
    """Watch prices for symbols in configured strategies.

    Args:
        config: Application configuration.

    Returns:
        List of dicts with watch data per symbol.
    """
    broker = get_broker(config)
    strategies = load_strategies()

    if not strategies:
        return []

    symbols = list(set(s.symbol for s in strategies))
    results = []

    for symbol in symbols:
        try:
            q = broker.get_quote(symbol)
            symbol_strategies = [s for s in strategies if s.symbol == symbol]
            strat_strs = [
                f"{s.strategy_type.value}: {s.phase.value.replace('_', ' ')}"
                for s in symbol_strategies
            ]
            results.append({
                "symbol": symbol,
                "bid": str(q.bid),
                "ask": str(q.ask),
                "strategies": strat_strs,
            })
        except Exception as e:
            results.append({
                "symbol": symbol,
                "error": str(e),
            })

    return results


def get_top_movers(config: Config, market_type: str = "stocks", limit: int = 10) -> dict[str, Any]:
    """Get top market movers (gainers and losers).

    Args:
        config: Application configuration.
        market_type: Market type ('stocks' or 'crypto'). Defaults to 'stocks'.
        limit: Maximum number of gainers/losers to return. Defaults to 10.

    Returns:
        Dictionary with 'gainers' and 'losers' lists.
    """
    broker = get_broker(config)
    # Type check: ensure broker has get_top_movers method
    if not hasattr(broker, "get_top_movers"):
        raise BrokerError(
            message="Top movers not supported by this broker",
            code="FEATURE_NOT_SUPPORTED",
        )
    try:
        return cast(dict[str, Any], broker.get_top_movers(market_type=market_type, limit=limit))
    except Exception as e:
        if "ConfigurationError" in type(e).__name__:
            raise
        raise _wrap_broker_error("fetch top movers", e)
