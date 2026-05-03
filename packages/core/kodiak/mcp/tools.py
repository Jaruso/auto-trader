"""Kodiak MCP tool definitions (transport-agnostic).

All MCP tools are defined here as plain functions. The register_tools()
function wires them onto any FastMCP server instance. Transport selection
(stdio vs streamable-http) is handled by the CLI and server packages.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Literal, cast

from mcp.server.fastmcp import FastMCP

from kodiak.errors import AppError, ValidationError

# =============================================================================
# Helpers
# =============================================================================


def _config() -> Any:
    """Load config lazily (avoids import-time side effects)."""
    from kodiak.utils.config import load_config

    return load_config()


def _ok(data: object) -> str:
    """Serialize a Pydantic model or dict/list to JSON."""
    if hasattr(data, "model_dump_json"):
        return str(data.model_dump_json(indent=2))
    return json.dumps(data, indent=2, default=str)


def _err(e: AppError) -> str:
    """Serialize an AppError to JSON."""
    return json.dumps(e.to_dict(), indent=2)


# =============================================================================
# Engine Tools
# =============================================================================


def get_status() -> str:
    """Get current Kodiak engine status.

    Returns engine running state, environment (paper/prod),
    broker service, API key configuration, active strategy count,
    and process ID if running. Check the 'hint' field for actionable
    guidance when the engine is not running or misconfigured.
    """
    from kodiak.app.engine import get_engine_status

    try:
        return _ok(get_engine_status(_config()))
    except AppError as e:
        return _err(e)


def start_engine(
    dry_run: bool = False,
    interval: int = 60,
    confirm_execution: bool = False,
) -> str:
    """Start the trading engine as a background process.

    Spawns the engine detached so this call returns immediately.
    The engine will run until stopped with stop_engine().
    Only paper trading is supported via MCP (use CLI --prod for production).

    Args:
        dry_run:  If true, evaluate strategies but do not place real orders.
        interval: Strategy poll interval in seconds (default: 60).
        confirm_execution: Must be true to start the engine process.
    """
    from kodiak.app.engine import start_engine as _start_engine

    try:
        return _ok(
            _start_engine(
                dry_run=dry_run,
                interval=interval,
                confirm_execution=confirm_execution,
            )
        )
    except AppError as e:
        return _err(e)


def stop_engine(force: bool = False, confirm_execution: bool = False) -> str:
    """Stop the running trading engine.

    Args:
        force: If true, send SIGKILL instead of SIGTERM.
        confirm_execution: Must be true to stop the engine process.
    """
    from kodiak.app.engine import stop_engine as _stop_engine

    try:
        return _ok(_stop_engine(force=force, confirm_execution=confirm_execution))
    except AppError as e:
        return _err(e)


# =============================================================================
# Portfolio & Market Data Tools
# =============================================================================


def get_balance() -> str:
    """Get account balance, equity, buying power, and daily P/L."""
    from kodiak.app.portfolio import get_balance as _get_balance

    try:
        return _ok(_get_balance(_config()))
    except AppError as e:
        return _err(e)


def get_positions() -> str:
    """List all open positions with current prices and unrealized P/L."""
    from kodiak.app.portfolio import get_positions as _get_positions

    try:
        result = _get_positions(_config())
        return json.dumps(
            [p.model_dump() for p in result], indent=2, default=str
        )
    except AppError as e:
        return _err(e)


def get_portfolio() -> str:
    """Get detailed portfolio summary with position weights and P/L breakdown."""
    from kodiak.app.portfolio import get_portfolio_summary

    try:
        return _ok(get_portfolio_summary(_config()))
    except AppError as e:
        return _err(e)


def get_portfolio_analytics(
    lookback_days: int = 252,
    benchmark_symbol: str = "SPY",
    end_date: str | None = None,
) -> str:
    """Get snapshot-based portfolio analytics versus a benchmark.

    Args:
        lookback_days: Target trailing window in trading days (default: 252).
        benchmark_symbol: Benchmark ticker for comparison (default: SPY).
        end_date: Optional YYYY-MM-DD history end date, useful for CSV datasets.
    """
    from datetime import date

    from kodiak.app.portfolio import get_portfolio_analytics as _get_portfolio_analytics

    parsed_end_date: date | None = None
    if end_date:
        parsed_end_date = date.fromisoformat(end_date)

    try:
        return _ok(
            _get_portfolio_analytics(
                _config(),
                lookback_days=lookback_days,
                benchmark_symbol=benchmark_symbol,
                end_date=parsed_end_date,
            )
        )
    except ValueError:
        return _err(
            ValidationError(
                message="end_date must be in YYYY-MM-DD format",
                details={"end_date": end_date},
            )
        )
    except AppError as e:
        return _err(e)


def calculate_position_size(
    symbol: str,
    method: str,
    price: float | None = None,
    target_value: float | None = None,
    target_weight_pct: float | None = None,
    risk_budget: float | None = None,
    stop_loss_pct: float | None = None,
    available_capital: float | None = None,
    max_position_value: float | None = None,
    max_position_weight_pct: float | None = None,
    lot_size: int = 1,
) -> str:
    """Calculate a recommended target position size.

    Args:
        symbol: Stock ticker (e.g. "AAPL").
        method: One of target_value, target_weight, or risk_budget.
        price: Optional explicit price override.
        target_value: Desired total dollar exposure for target_value sizing.
        target_weight_pct: Desired portfolio weight (%) for target_weight sizing.
        risk_budget: Dollar risk budget for risk_budget sizing.
        stop_loss_pct: Stop-loss percentage used with risk_budget sizing.
        available_capital: Optional override for capital available to deploy.
        max_position_value: Optional hard cap for total position value.
        max_position_weight_pct: Optional hard cap for total portfolio weight.
        lot_size: Round target quantity down to this lot size.
    """
    from kodiak.app.portfolio import calculate_position_size_app
    from kodiak.schemas.portfolio import PositionSizingRequest

    try:
        return _ok(
            calculate_position_size_app(
                _config(),
                PositionSizingRequest(
                    symbol=symbol.upper(),
                    method=method,
                    price=Decimal(str(price)) if price is not None else None,
                    target_value=Decimal(str(target_value)) if target_value is not None else None,
                    target_weight_pct=(
                        Decimal(str(target_weight_pct)) if target_weight_pct is not None else None
                    ),
                    risk_budget=Decimal(str(risk_budget)) if risk_budget is not None else None,
                    stop_loss_pct=Decimal(str(stop_loss_pct)) if stop_loss_pct is not None else None,
                    available_capital=(
                        Decimal(str(available_capital)) if available_capital is not None else None
                    ),
                    max_position_value=(
                        Decimal(str(max_position_value)) if max_position_value is not None else None
                    ),
                    max_position_weight_pct=(
                        Decimal(str(max_position_weight_pct))
                        if max_position_weight_pct is not None
                        else None
                    ),
                    lot_size=lot_size,
                ),
            )
        )
    except AppError as e:
        return _err(e)


def get_rebalance_plan(
    target_weights: dict[str, float],
    drift_threshold_pct: float = 1,
    cash_buffer_pct: float = 0,
    liquidate_unmentioned: bool = False,
    lot_size: int = 1,
    max_position_weight_pct: float | None = None,
) -> str:
    """Generate a dry-run rebalance plan from target portfolio weights.

    Args:
        target_weights: Mapping of symbol -> target portfolio weight percent.
        drift_threshold_pct: Minimum drift (%) before proposing a rebalance trade.
        cash_buffer_pct: Minimum cash to retain after rebalancing.
        liquidate_unmentioned: If true, positions not in target_weights are targeted to 0%.
        lot_size: Round target quantities down to this lot size.
        max_position_weight_pct: Optional max allowed target weight per symbol.
    """
    from kodiak.app.portfolio import get_rebalance_plan_app
    from kodiak.schemas.portfolio import RebalanceRequest

    try:
        return _ok(
            get_rebalance_plan_app(
                _config(),
                RebalanceRequest(
                    target_weights={
                        symbol.upper(): Decimal(str(weight))
                        for symbol, weight in target_weights.items()
                    },
                    drift_threshold_pct=Decimal(str(drift_threshold_pct)),
                    cash_buffer_pct=Decimal(str(cash_buffer_pct)),
                    liquidate_unmentioned=liquidate_unmentioned,
                    lot_size=lot_size,
                    max_position_weight_pct=(
                        Decimal(str(max_position_weight_pct))
                        if max_position_weight_pct is not None
                        else None
                    ),
                ),
            )
        )
    except AppError as e:
        return _err(e)


def get_quote(symbol: str) -> str:
    """Get current bid/ask/last quote for a symbol.

    Args:
        symbol: Stock ticker (e.g. "AAPL", "MSFT").
    """
    from kodiak.app.portfolio import get_quote as _get_quote

    try:
        return _ok(_get_quote(_config(), symbol.upper()))
    except AppError as e:
        return _err(e)


def get_top_movers(market_type: str = "stocks", limit: int = 10) -> str:
    """Get top market movers (gainers and losers).

    Args:
        market_type: Market type ('stocks' or 'crypto'). Defaults to 'stocks'.
        limit: Maximum number of gainers/losers to return. Defaults to 10.
    """
    from kodiak.app.portfolio import get_top_movers as _get_top_movers

    try:
        result = _get_top_movers(_config(), market_type=market_type, limit=limit)
        return json.dumps(result, indent=2, default=str)
    except AppError as e:
        return _err(e)


# =============================================================================
# Research Data Tools
# =============================================================================


def get_fundamentals(symbol: str) -> str:
    """Get file-backed company fundamentals for a symbol.

    Args:
        symbol: Stock ticker (e.g. "AAPL").
    """
    from kodiak.app.research import get_fundamentals as _get_fundamentals

    try:
        return _ok(_get_fundamentals(_config(), symbol.upper()))
    except AppError as e:
        return _err(e)


def get_benchmark_history(
    symbol: str,
    start: str,
    end: str,
    data_source: str | None = None,
    timeframe: str = "1Day",
) -> str:
    """Get historical bars and return stats for a benchmark symbol.

    Args:
        symbol: Benchmark ticker (e.g. "SPY").
        start: Start date in YYYY-MM-DD format.
        end: End date in YYYY-MM-DD format.
        data_source: Optional data source override ("csv", "alpaca", or "cached").
        timeframe: Bar timeframe (default: "1Day").
    """
    from datetime import date

    from kodiak.app.research import get_benchmark_history as _get_benchmark_history
    from kodiak.data.providers.base import TimeFrame

    try:
        return _ok(
            _get_benchmark_history(
                _config(),
                symbol.upper(),
                start=date.fromisoformat(start),
                end=date.fromisoformat(end),
                data_source=data_source,
                timeframe=TimeFrame(timeframe),
            )
        )
    except ValueError as e:
        return _err(
            ValidationError(
                message="start/end must be YYYY-MM-DD and timeframe must be a supported value.",
                details={
                    "start": start,
                    "end": end,
                    "timeframe": timeframe,
                    "reason": str(e),
                },
            )
        )
    except AppError as e:
        return _err(e)


# =============================================================================
# Order Tools
# =============================================================================


def place_order(
    symbol: str,
    qty: int,
    side: str,
    price: float,
    confirm_execution: bool = False,
) -> str:
    """Place a limit order (with safety checks).

    Args:
        symbol: Stock ticker (e.g. "AAPL").
        qty: Number of shares (must be >= 1).
        side: "buy" or "sell".
        price: Limit price per share.
        confirm_execution: Must be true to place an order.
    """
    from kodiak.app.orders import place_order as _place_order
    from kodiak.schemas.orders import OrderRequest

    try:
        request = OrderRequest(
            symbol=symbol.upper(),
            qty=qty,
            side=side.lower(),
            price=Decimal(str(price)),
        )
        return _ok(_place_order(_config(), request, confirm_execution=confirm_execution))
    except AppError as e:
        return _err(e)


def list_orders(show_all: bool = False) -> str:
    """List orders. By default shows only open/pending orders.

    Args:
        show_all: If true, include filled, cancelled, and expired orders.
    """
    from kodiak.app.orders import list_orders as _list_orders

    try:
        result = _list_orders(_config(), show_all=show_all)
        return json.dumps(
            [o.model_dump() for o in result], indent=2, default=str
        )
    except AppError as e:
        return _err(e)


def cancel_order(order_id: str, confirm_execution: bool = False) -> str:
    """Cancel an open order by ID.

    Args:
        order_id: The order ID to cancel.
        confirm_execution: Must be true to cancel an order.
    """
    from kodiak.app.orders import cancel_order as _cancel_order

    try:
        return _ok(_cancel_order(_config(), order_id, confirm_execution=confirm_execution))
    except AppError as e:
        return _err(e)


# =============================================================================
# Strategy Tools
# =============================================================================


def list_strategies() -> str:
    """List all configured trading strategies."""
    from kodiak.app.strategies import list_strategies as _list_strategies

    try:
        return _ok(_list_strategies())
    except AppError as e:
        return _err(e)


def get_strategy(strategy_id: str) -> str:
    """Get detailed information about a specific strategy.

    Args:
        strategy_id: The strategy ID.
    """
    from kodiak.app.strategies import get_strategy_detail

    try:
        return _ok(get_strategy_detail(strategy_id))
    except AppError as e:
        return _err(e)


def create_strategy(
    strategy_type: str,
    symbol: str,
    qty: int = 1,
    trailing_pct: float | None = None,
    pullback_pct: float | None = None,
    take_profit: float | None = None,
    stop_loss: float | None = None,
    entry_price: float | None = None,
    levels: int | None = None,
) -> str:
    """Create a new trading strategy.

    Args:
        strategy_type: One of "trailing-stop", "bracket", "scale-out", "grid", "pullback-trailing".
        symbol: Stock ticker (e.g. "AAPL").
        qty: Number of shares per trade.
        trailing_pct: Trailing stop percentage (for trailing-stop and pullback-trailing).
        pullback_pct: Pullback % from high to trigger buy (for pullback-trailing, default 5).
        take_profit: Take profit percentage (for bracket strategy).
        stop_loss: Stop loss percentage (for bracket strategy).
        entry_price: Limit entry price. If omitted, uses market order.
        levels: Number of grid levels (for grid strategy).
    """
    from kodiak.app.strategies import create_strategy as _create_strategy
    from kodiak.schemas.strategies import StrategyCreate

    try:
        request = StrategyCreate(
            strategy_type=strategy_type,
            symbol=symbol.upper(),
            qty=qty,
            trailing_pct=trailing_pct,
            pullback_pct=pullback_pct,
            take_profit=take_profit,
            stop_loss=stop_loss,
            entry_price=entry_price,
            levels=levels,
        )
        return _ok(_create_strategy(_config(), request))
    except AppError as e:
        return _err(e)


def remove_strategy(strategy_id: str) -> str:
    """Delete a strategy by ID.

    Args:
        strategy_id: The strategy ID to remove.
    """
    from kodiak.app.strategies import remove_strategy as _remove_strategy

    try:
        return _ok(_remove_strategy(strategy_id))
    except AppError as e:
        return _err(e)


def pause_strategy(strategy_id: str) -> str:
    """Pause an active strategy.

    Args:
        strategy_id: The strategy ID to pause.
    """
    from kodiak.app.strategies import pause_strategy as _pause_strategy

    try:
        return _ok(_pause_strategy(strategy_id))
    except AppError as e:
        return _err(e)


def resume_strategy(strategy_id: str) -> str:
    """Resume a paused strategy.

    Args:
        strategy_id: The strategy ID to resume.
    """
    from kodiak.app.strategies import resume_strategy as _resume_strategy

    try:
        return _ok(_resume_strategy(strategy_id))
    except AppError as e:
        return _err(e)


def set_strategy_enabled(strategy_id: str, enabled: bool) -> str:
    """Enable or disable a strategy.

    Args:
        strategy_id: The strategy ID.
        enabled: True to enable, False to disable.
    """
    from kodiak.app.strategies import set_strategy_enabled as _set_enabled

    try:
        return _ok(_set_enabled(strategy_id, enabled))
    except AppError as e:
        return _err(e)


def schedule_strategy(strategy_id: str, schedule_at: str) -> str:
    """Schedule a strategy to start at a specific time.

    The strategy will be disabled until the schedule time arrives.
    Once the time arrives, the engine will automatically enable it.

    Args:
        strategy_id: The strategy ID to schedule.
        schedule_at: ISO datetime string (e.g., "2026-02-13T09:30:00").
    """
    from datetime import datetime

    from kodiak.app.strategies import schedule_strategy as _schedule_strategy

    try:
        # Parse ISO datetime string
        schedule_dt = datetime.fromisoformat(schedule_at)
        return _ok(_schedule_strategy(strategy_id, schedule_dt))
    except ValueError:
        return _err(
            ValidationError(
                message=f"Invalid datetime format: {schedule_at}. Use ISO format: '2026-02-13T09:30:00'",
                code="INVALID_DATETIME_FORMAT",
            )
        )
    except AppError as e:
        return _err(e)


def cancel_schedule(strategy_id: str) -> str:
    """Cancel a scheduled strategy.

    This clears the schedule and leaves the strategy in its current state.

    Args:
        strategy_id: The strategy ID to cancel schedule for.
    """
    from kodiak.app.strategies import cancel_schedule as _cancel_schedule

    try:
        return _ok(_cancel_schedule(strategy_id))
    except AppError as e:
        return _err(e)


def list_scheduled_strategies() -> str:
    """List all strategies with active schedules.

    Returns a list of strategies that are scheduled to start at a future time.
    """
    from kodiak.app.strategies import list_scheduled_strategies as _list_scheduled

    try:
        return _ok(_list_scheduled())
    except AppError as e:
        return _err(e)


# =============================================================================
# Backtest Tools
# =============================================================================


def run_backtest(
    strategy_type: str,
    start: str,
    end: str,
    symbol: str | None = None,
    symbols: list[str] | None = None,
    qty: int = 10,
    trailing_pct: float | None = None,
    take_profit: float | None = None,
    stop_loss: float | None = None,
    data_source: str = "csv",
    initial_capital: float = 100000.0,
    save: bool = True,
    fee_type: str = "fixed",
    fee_value: float = 0.0,
    slippage_type: str = "fixed_bps",
    slippage_bps: float = 0.0,
    fill_type: str = "full",
    fill_partial_pct: float = 1.0,
) -> str:
    """Run a backtest on historical data.

    Accepts a single symbol (via `symbol`) or multiple symbols (via `symbols`).
    When multiple symbols are provided, capital is split equally and a
    PortfolioBacktestResponse is returned with per-symbol attribution.

    Subject to MCP rate limits and timeout (see MCP_BACKTEST_TIMEOUT_SECONDS).

    Args:
        strategy_type: "trailing-stop" or "bracket".
        symbol: Single stock ticker (e.g. "AAPL"). Use symbols for multi-symbol.
        symbols: List of tickers for portfolio backtest (e.g. ["AAPL", "MSFT"]).
        start: Start date (YYYY-MM-DD).
        end: End date (YYYY-MM-DD).
        qty: Shares per trade (applied to each symbol).
        trailing_pct: Trailing stop percentage (trailing-stop strategy).
        take_profit: Take profit percentage (bracket strategy).
        stop_loss: Stop loss percentage (bracket strategy).
        data_source: "csv" or "alpaca".
        initial_capital: Total starting capital (split equally when using symbols).
        save: Whether to save results to disk.
        fee_type: "fixed" (dollars per order) or "percentage" (fraction of notional).
        fee_value: Fee amount. For fixed: dollars per order. For percentage: fraction (e.g. 0.001 = 0.1%).
        slippage_type: "fixed_bps" or "volatility_bps" (scales with bar range).
        slippage_bps: Slippage in basis points (e.g. 5.0 = 5 bps).
        fill_type: "full" (default) or "partial" (simulate partial fills).
        fill_partial_pct: Fraction of order filled when fill_type is "partial" (e.g. 0.5 = 50%).
    """
    from kodiak.app.backtests import run_backtest as _run_backtest
    from kodiak.mcp.limits import (
        check_rate_limit,
        get_backtest_timeout_seconds,
        run_with_timeout,
    )
    from kodiak.schemas.backtests import (
        BacktestRequest,
        ExecutionConfig,
        FeeModel,
        FillModel,
        SlippageModel,
    )

    try:
        check_rate_limit("long_running")
        execution = ExecutionConfig(
            fee=FeeModel(type=fee_type, value=fee_value),
            slippage=SlippageModel(type=slippage_type, bps=slippage_bps),
            fill=FillModel(type=fill_type, partial_pct=fill_partial_pct),
        )
        request = BacktestRequest(
            strategy_type=strategy_type,
            symbol=symbol.upper() if symbol else None,
            symbols=[s.upper() for s in symbols] if symbols else None,
            start=start,
            end=end,
            qty=qty,
            trailing_pct=trailing_pct,
            take_profit=take_profit,
            stop_loss=stop_loss,
            data_source=data_source,
            initial_capital=initial_capital,
            save=save,
            execution=execution,
        )
        timeout = get_backtest_timeout_seconds()
        result = run_with_timeout(
            lambda: _run_backtest(_config(), request),
            timeout_seconds=timeout,
            task_name="run_backtest",
        )
        return _ok(result)
    except AppError as e:
        return _err(e)


def list_backtests() -> str:
    """List all saved backtest results."""
    from kodiak.app.backtests import list_backtests_app

    try:
        result = list_backtests_app()
        return json.dumps(
            [b.model_dump() for b in result], indent=2, default=str
        )
    except AppError as e:
        return _err(e)


def show_backtest(backtest_id: str) -> str:
    """Get full results for a specific backtest.

    Args:
        backtest_id: The backtest ID.
    """
    from kodiak.app.backtests import show_backtest as _show_backtest

    try:
        return _ok(_show_backtest(backtest_id))
    except AppError as e:
        return _err(e)


def compare_backtests(backtest_ids: list[str]) -> str:
    """Compare multiple backtests side by side.

    Args:
        backtest_ids: List of backtest IDs to compare.
    """
    from kodiak.app.backtests import compare_backtests as _compare

    try:
        results = _compare(backtest_ids)
        return json.dumps(
            [r.model_dump() for r in results], indent=2, default=str
        )
    except AppError as e:
        return _err(e)


def delete_backtest(backtest_id: str) -> str:
    """Delete a saved backtest result.

    Args:
        backtest_id: The backtest ID to delete.
    """
    from kodiak.app.backtests import delete_backtest_app

    try:
        return _ok(delete_backtest_app(backtest_id))
    except AppError as e:
        return _err(e)


# =============================================================================
# Analysis Tools
# =============================================================================


def analyze_performance(
    symbol: str | None = None,
    days: int = 30,
    limit: int = 1000,
) -> str:
    """Analyze realized trade performance (win rate, profit factor, etc.).

    Args:
        symbol: Filter by ticker. If omitted, analyzes all trades.
        days: Number of days to look back.
        limit: Maximum number of trades to analyze.
    """
    from kodiak.app.analysis import analyze_trade_performance

    try:
        result = analyze_trade_performance(
            symbol=symbol.upper() if symbol else None,
            days=days,
            limit=limit,
        )
        if result is None:
            return json.dumps({"message": "No trades found for analysis."})
        return _ok(result)
    except AppError as e:
        return _err(e)


def get_trade_history(symbol: str | None = None, limit: int = 20) -> str:
    """Get recent trade records.

    Args:
        symbol: Filter by ticker. If omitted, returns all symbols.
        limit: Maximum number of trades to return.
    """
    from kodiak.app.analysis import get_trade_history as _get_history

    try:
        result = _get_history(
            symbol=symbol.upper() if symbol else None, limit=limit
        )
        return json.dumps(result, indent=2, default=str)
    except AppError as e:
        return _err(e)


def get_today_pnl() -> str:
    """Get today's realized profit/loss."""
    from kodiak.app.analysis import get_today_pnl as _get_today_pnl

    try:
        pnl = _get_today_pnl()
        return json.dumps({"today_pnl": str(pnl)}, indent=2)
    except AppError as e:
        return _err(e)


def export_analysis_report(
    output_path: str | None = None,
    format: Literal["json", "markdown"] = "json",
    symbol: str | None = None,
    days: int = 30,
    limit: int = 1000,
    include_portfolio: bool = False,
    portfolio_lookback_days: int = 252,
    benchmark_symbol: str = "SPY",
) -> str:
    """Generate a headless analysis report and optionally write it to disk.

    Args:
        output_path: Optional local file path. If omitted, returns report content.
        format: Report format: "json" or "markdown".
        symbol: Filter trades by ticker. If omitted, includes all symbols.
        days: Number of days to look back.
        limit: Maximum number of trades to include.
        include_portfolio: Include portfolio analytics when config/data is available.
        portfolio_lookback_days: Lookback window for portfolio analytics.
        benchmark_symbol: Benchmark symbol for portfolio analytics.
    """
    from kodiak.app.reports import export_analysis_report as _export_analysis_report

    try:
        return _ok(
            _export_analysis_report(
                _config(),
                output_path=output_path,
                format=format,
                symbol=symbol.upper() if symbol else None,
                days=days,
                limit=limit,
                include_portfolio=include_portfolio,
                portfolio_lookback_days=portfolio_lookback_days,
                benchmark_symbol=benchmark_symbol.upper(),
            )
        )
    except AppError as e:
        return _err(e)


# =============================================================================
# Indicator Tools
# =============================================================================


def list_indicators() -> str:
    """List all available technical indicators (SMA, RSI, MACD, etc.)."""
    from kodiak.app.indicators import list_all_indicators

    try:
        result = list_all_indicators()
        return json.dumps(
            [i.model_dump() for i in result], indent=2, default=str
        )
    except AppError as e:
        return _err(e)


def describe_indicator(name: str) -> str:
    """Get detailed information about a specific technical indicator.

    Args:
        name: Indicator name (e.g. "sma", "rsi", "macd").
    """
    from kodiak.app.indicators import describe_indicator as _describe

    try:
        return _ok(_describe(name.lower()))
    except AppError as e:
        return _err(e)


# =============================================================================
# Optimization Tools
# =============================================================================


def run_optimization(
    strategy_type: str,
    symbol: str,
    start: str,
    end: str,
    params: dict[str, list[Any]],
    objective: str = "total_return_pct",
    method: str = "grid",
    num_samples: int | None = None,
    data_source: str = "csv",
    initial_capital: float = 100000.0,
    save: bool = True,
    fee_type: str = "fixed",
    fee_value: float = 0.0,
    slippage_type: str = "fixed_bps",
    slippage_bps: float = 0.0,
    fill_type: str = "full",
    fill_partial_pct: float = 1.0,
) -> str:
    """Run parameter optimization over a grid of strategy parameters.

    Subject to MCP rate limits and timeout (see MCP_OPTIMIZATION_TIMEOUT_SECONDS).

    Args:
        strategy_type: "trailing-stop" or "bracket".
        symbol: Stock ticker (e.g. "AAPL").
        start: Start date (YYYY-MM-DD).
        end: End date (YYYY-MM-DD).
        params: Parameter grid. Accepts both short and canonical names:
            - For trailing-stop: "trailing_pct" or "trailing_stop_pct"
            - For bracket: "take_profit"/"take_profit_pct" and "stop_loss"/"stop_loss_pct"
            Example: {"take_profit": [0.02, 0.05], "stop_loss": [0.01, 0.02]}
        objective: Metric to optimize ("total_return_pct", "sharpe_ratio", "win_rate", etc.).
        method: "grid" for exhaustive search or "random" for sampling.
        num_samples: Number of random samples (only for method="random").
        data_source: "csv" or "alpaca".
        initial_capital: Starting capital for simulation.
        save: Whether to save results to disk.
        fee_type: "fixed" (dollars per order) or "percentage" (fraction of notional).
        fee_value: Fee amount. For fixed: dollars per order. For percentage: fraction (e.g. 0.001 = 0.1%).
        slippage_type: "fixed_bps" or "volatility_bps" (scales with bar range).
        slippage_bps: Slippage in basis points (e.g. 5.0 = 5 bps).
        fill_type: "full" (default) or "partial" (simulate partial fills).
        fill_partial_pct: Fraction of order filled when fill_type is "partial" (e.g. 0.5 = 50%).
    """
    from kodiak.app.optimization import run_optimization as _run_opt
    from kodiak.mcp.limits import (
        check_rate_limit,
        get_optimization_timeout_seconds,
        run_with_timeout,
    )
    from kodiak.schemas.backtests import ExecutionConfig, FeeModel, FillModel, SlippageModel
    from kodiak.schemas.optimization import OptimizeRequest

    try:
        check_rate_limit("long_running")
        execution = ExecutionConfig(
            fee=FeeModel(type=fee_type, value=fee_value),
            slippage=SlippageModel(type=slippage_type, bps=slippage_bps),
            fill=FillModel(type=fill_type, partial_pct=fill_partial_pct),
        )
        request = OptimizeRequest(
            strategy_type=strategy_type,
            symbol=symbol.upper(),
            start=start,
            end=end,
            params=params,
            objective=objective,
            method=method,
            num_samples=num_samples,
            data_source=data_source,
            initial_capital=initial_capital,
            save=save,
            execution=execution,
        )
        timeout = get_optimization_timeout_seconds()
        result = run_with_timeout(
            lambda: _run_opt(_config(), request),
            timeout_seconds=timeout,
            task_name="run_optimization",
        )
        return _ok(result)
    except AppError as e:
        return _err(e)


# =============================================================================
# Safety Tools
# =============================================================================


def get_safety_status() -> str:
    """Get current safety check status and limits.

    Returns position size limits, daily loss limits, and trade count limits.
    """
    from kodiak.app.data import get_safety_status as _get_safety

    try:
        return _ok(_get_safety(_config()))
    except AppError as e:
        return _err(e)


# =============================================================================
# Tool Registration
# =============================================================================


def _with_mcp_audit(fn: Any) -> Any:
    """Wrap a tool so audit source is set to 'mcp' for the duration of the call."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        from kodiak.audit import set_audit_source

        set_audit_source("mcp")
        return fn(*args, **kwargs)

    return wrapper


# =============================================================================
# Orchestration Tools
# =============================================================================


def run_workflow(
    plan_name: str,
    steps: list[dict[str, Any]],
    deterministic: bool = True,
) -> str:
    """Execute a multi-step workflow by sequencing registered primitives.

    AI selects and sequences primitives; Kodiak executes them deterministically.
    Each step references a registered primitive by name with its input arguments.
    Steps run in order; failure on any step halts the workflow.

    Args:
        plan_name: Human-readable name for this workflow execution.
        steps: Ordered list of step descriptors. Each step is a dict with:
            - primitive (str, required): Registered primitive name.
            - inputs (dict, optional): Keyword args forwarded to the primitive.
            - version (str, optional): Semver or "latest" (default: "latest").
            - retry_count (int, optional): Extra attempts on transient failure.
        deterministic: When true, validates all primitives are registered before
            execution begins (recommended). Default: true.

    Example step list::

        [
            {"primitive": "get_quote", "inputs": {"symbol": "AAPL"}},
            {"primitive": "calculate_position_size",
             "inputs": {"symbol": "AAPL", "target_value": 5000.0},
             "retry_count": 1},
        ]
    """
    from kodiak.orchestration import WorkflowExecutor, WorkflowPlan, WorkflowStep  # noqa: PLC0415

    plan = WorkflowPlan(
        name=plan_name,
        steps=[WorkflowStep.from_dict(s) for s in steps],
        deterministic=deterministic,
    )
    result = WorkflowExecutor().execute(plan)
    return _ok(result.to_dict())


def validate_workflow_spec(spec: str) -> str:
    """Validate a YAML or JSON workflow spec without executing it.

    Returns a validation report listing any errors found in the spec.
    An empty errors list means the spec is ready to run.

    Args:
        spec: YAML or JSON string containing the workflow spec.

    Spec formats accepted:

        Full form (named steps with inputs)::

            name: my-workflow
            steps:
              - primitive: get_quote
                inputs:
                  symbol: AAPL
              - primitive: get_balance

        Short form (bare primitive names)::

            name: portfolio-check
            steps:
              - get_balance
              - get_positions

        Compact form (workflow name as top-level key)::

            portfolio_check:
              - get_balance
              - get_positions
    """
    from kodiak.orchestration import WorkflowSpec, WorkflowSpecError  # noqa: PLC0415

    try:
        workflow_spec = WorkflowSpec.from_yaml(spec)
    except WorkflowSpecError:
        try:
            workflow_spec = WorkflowSpec.from_json(spec)
        except WorkflowSpecError as exc:
            return _ok({"valid": False, "errors": [str(exc)]})

    errors = workflow_spec.validate()
    return _ok({"valid": len(errors) == 0, "errors": errors})


def run_workflow_spec(spec: str) -> str:
    """Parse, validate, and execute a YAML or JSON workflow spec.

    Combines spec parsing, validation, plan compilation, and execution
    into a single call. If validation fails, returns errors without executing.

    Args:
        spec: YAML or JSON workflow spec string (same format as validate_workflow_spec).
    """
    from kodiak.orchestration import WorkflowExecutor, WorkflowSpec, WorkflowSpecError  # noqa: PLC0415

    try:
        workflow_spec = WorkflowSpec.from_yaml(spec)
    except WorkflowSpecError:
        try:
            workflow_spec = WorkflowSpec.from_json(spec)
        except WorkflowSpecError as exc:
            return _ok({"valid": False, "errors": [str(exc)], "result": None})

    errors = workflow_spec.validate()
    if errors:
        return _ok({"valid": False, "errors": errors, "result": None})

    plan = workflow_spec.compile()
    result = WorkflowExecutor().execute(plan)
    return _ok({"valid": True, "errors": [], "result": result.to_dict()})


# =============================================================================
# Primitives Discovery Tools
# =============================================================================


def list_primitives(include_deprecated: bool = False) -> str:
    """List all registered financial action primitives (latest version of each).

    Args:
        include_deprecated: When true, includes deprecated primitive versions
            in the results. Defaults to false.

    Returns name, version, description, risk level, permissions, latency class,
    and execution mode for each primitive in the registry.
    """
    from kodiak.primitives import list_all  # noqa: PLC0415

    primitives = list_all()
    if not include_deprecated:
        primitives = [p for p in primitives if not p.deprecated]
    return _ok([p.to_dict() for p in primitives])


def describe_primitive(name: str, version: str = "latest") -> str:
    """Get the full descriptor for a single financial action primitive.

    Args:
        name: Primitive name (e.g. "get_quote", "place_order", "run_backtest").
        version: Semver string (e.g. "1.0.0") or "latest" (default).
    """
    from kodiak.primitives import get  # noqa: PLC0415

    primitive = get(name, version=version)
    if primitive is None:
        from kodiak.errors import NotFoundError  # noqa: PLC0415

        return _err(NotFoundError(f"Primitive '{name}' version '{version}' not found."))
    return _ok(primitive.to_dict())


_ALL_TOOLS = [
    # Engine
    get_status,
    start_engine,
    stop_engine,
    # Portfolio & Market Data
    get_balance,
    get_positions,
    get_portfolio,
    get_portfolio_analytics,
    calculate_position_size,
    get_rebalance_plan,
    get_quote,
    get_top_movers,
    # Research Data
    get_fundamentals,
    get_benchmark_history,
    # Orders
    place_order,
    list_orders,
    cancel_order,
    # Strategies
    list_strategies,
    get_strategy,
    create_strategy,
    remove_strategy,
    pause_strategy,
    resume_strategy,
    set_strategy_enabled,
    schedule_strategy,
    cancel_schedule,
    list_scheduled_strategies,
    # Backtests
    run_backtest,
    list_backtests,
    show_backtest,
    compare_backtests,
    delete_backtest,
    # Analysis
    analyze_performance,
    get_trade_history,
    get_today_pnl,
    export_analysis_report,
    # Indicators
    list_indicators,
    describe_indicator,
    # Optimization
    run_optimization,
    # Safety
    get_safety_status,
    # Primitives discovery
    list_primitives,
    describe_primitive,
    # Orchestration
    run_workflow,
    validate_workflow_spec,
    run_workflow_spec,
]


def register_tools(server: FastMCP) -> None:
    """Register all MCP tools on the provided server."""
    tool_decorator = cast(Any, server.tool())
    for tool_fn in _ALL_TOOLS:
        tool_decorator(_with_mcp_audit(tool_fn))


def build_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO",
) -> FastMCP:
    """Create a FastMCP server with all Kodiak tools registered.

    Transport selection (stdio vs streamable-http) is handled by the caller.
    """
    server = FastMCP("kodiak", host=host, port=port, log_level=log_level)
    register_tools(server)
    return server
