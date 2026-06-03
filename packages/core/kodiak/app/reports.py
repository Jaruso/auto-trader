"""Headless analysis report generation."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from kodiak.data.ledger import TradeLedger, TradeRecord
from kodiak.errors import AppError, ValidationError
from kodiak.utils.config import Config

ReportFormat = Literal["json", "markdown"]


def build_analysis_report(
    config: Config | None = None,
    *,
    symbol: str | None = None,
    days: int = 30,
    limit: int = 1000,
    include_portfolio: bool = False,
    portfolio_lookback_days: int = 252,
    benchmark_symbol: str = "SPY",
    ledger: TradeLedger | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable analysis report.

    The report intentionally remains data-only so it can be consumed by CLI,
    REST, MCP, schedulers, or any other headless integration.
    """
    _validate_report_inputs(
        days=days,
        limit=limit,
        portfolio_lookback_days=portfolio_lookback_days,
    )

    normalized_symbol = symbol.upper() if symbol else None
    trade_ledger = ledger or TradeLedger()
    since = datetime.now() - timedelta(days=days)
    trades = trade_ledger.get_trades(
        symbol=normalized_symbol,
        since=since,
        limit=limit,
    )

    report: dict[str, Any] = {
        "report_type": "analysis",
        "generated_at": datetime.now(UTC).isoformat(),
        "parameters": {
            "symbol": normalized_symbol,
            "days": days,
            "limit": limit,
            "include_portfolio": include_portfolio,
            "portfolio_lookback_days": portfolio_lookback_days,
            "benchmark_symbol": benchmark_symbol.upper(),
        },
        "trade_count": len(trades),
        "today_pnl": _today_pnl_payload(trade_ledger, normalized_symbol),
        "trade_performance": _trade_performance_payload(trades),
        "trade_history": [_trade_record_payload(trade) for trade in trades],
    }

    if config is not None:
        report["strategy_snapshot"] = _strategy_snapshot_payload()
        report["portfolio_snapshot"] = _portfolio_snapshot_payload(config)
        report["backtest_snapshot"] = _backtest_snapshot_payload(config)

    if include_portfolio:
        report["portfolio_analytics"] = _portfolio_payload(
            config,
            lookback_days=portfolio_lookback_days,
            benchmark_symbol=benchmark_symbol,
        )

    report["diagnostics"] = _diagnostics_payload(report)

    return report


def render_analysis_report(
    report: dict[str, Any],
    *,
    format: ReportFormat,
) -> str:
    """Render an analysis report as JSON or Markdown."""
    if format == "json":
        return json.dumps(report, indent=2, default=str)
    if format == "markdown":
        return _render_markdown(report)
    raise ValidationError(
        f"Unsupported report format: {format}",
        details={"format": format, "supported": ["json", "markdown"]},
    )


def export_analysis_report(
    config: Config | None = None,
    *,
    output_path: Path | str | None = None,
    format: ReportFormat = "json",
    symbol: str | None = None,
    days: int = 30,
    limit: int = 1000,
    include_portfolio: bool = False,
    portfolio_lookback_days: int = 252,
    benchmark_symbol: str = "SPY",
) -> dict[str, Any]:
    """Generate and optionally write a headless analysis report."""
    report = build_analysis_report(
        config,
        symbol=symbol,
        days=days,
        limit=limit,
        include_portfolio=include_portfolio,
        portfolio_lookback_days=portfolio_lookback_days,
        benchmark_symbol=benchmark_symbol,
    )
    content = render_analysis_report(report, format=format)

    result: dict[str, Any] = {
        "format": format,
        "bytes": len(content.encode("utf-8")),
        "path": None,
        "report": report if format == "json" else None,
        "content": content if output_path is None else None,
    }

    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        result["path"] = str(path)
        result["content"] = None

    return result


def _validate_report_inputs(
    *,
    days: int,
    limit: int,
    portfolio_lookback_days: int,
) -> None:
    if days < 1:
        raise ValidationError("days must be at least 1", details={"days": days})
    if limit < 1:
        raise ValidationError("limit must be at least 1", details={"limit": limit})
    if portfolio_lookback_days < 1:
        raise ValidationError(
            "portfolio_lookback_days must be at least 1",
            details={"portfolio_lookback_days": portfolio_lookback_days},
        )


def _trade_performance_payload(trades: list[TradeRecord]) -> dict[str, Any] | None:
    if not trades:
        return None

    from kodiak.analysis.trades import analyze_trades
    from kodiak.schemas.analysis import AnalysisResponse

    return AnalysisResponse.from_domain(analyze_trades(trades)).model_dump(mode="json")


def _trade_record_payload(trade: TradeRecord) -> dict[str, Any]:
    return {
        "id": trade.id,
        "order_id": trade.order_id,
        "symbol": trade.symbol,
        "side": trade.side,
        "quantity": str(trade.quantity),
        "price": str(trade.price),
        "total": str(trade.total),
        "status": trade.status,
        "rule_id": trade.rule_id,
        "timestamp": trade.timestamp.isoformat(),
    }


def _today_pnl_payload(ledger: TradeLedger, symbol: str | None) -> str:
    if symbol is None:
        return str(ledger.get_total_today_pnl())
    return str(ledger.get_today_pnl().get(symbol, 0))


def _portfolio_payload(
    config: Config | None,
    *,
    lookback_days: int,
    benchmark_symbol: str,
) -> dict[str, Any]:
    if config is None:
        return {
            "available": False,
            "error": "CONFIGURATION_REQUIRED",
            "message": "Portfolio analytics require a loaded Kodiak config.",
        }

    from kodiak.app.portfolio import get_portfolio_analytics

    try:
        result = get_portfolio_analytics(
            config,
            lookback_days=lookback_days,
            benchmark_symbol=benchmark_symbol.upper(),
        )
        return {"available": True, "data": result.model_dump(mode="json")}
    except AppError as exc:
        return {
            "available": False,
            "error": exc.code,
            "message": exc.message,
            "details": exc.details,
            "suggestion": exc.suggestion,
        }


def _strategy_snapshot_payload() -> dict[str, Any]:
    from kodiak.strategies.loader import load_strategies

    strategies = load_strategies()
    active = 0
    scheduled = 0
    by_type: dict[str, int] = {}
    by_phase: dict[str, int] = {}
    now = datetime.now()

    for strategy in strategies:
        by_type[strategy.strategy_type.value] = by_type.get(strategy.strategy_type.value, 0) + 1
        by_phase[strategy.phase.value] = by_phase.get(strategy.phase.value, 0) + 1
        if strategy.enabled and strategy.is_active():
            if strategy.schedule_enabled and strategy.schedule_at and strategy.schedule_at > now:
                scheduled += 1
            else:
                active += 1

    return {
        "count": len(strategies),
        "active_count": active,
        "scheduled_count": scheduled,
        "by_type": by_type,
        "by_phase": by_phase,
        "strategies": [
            {
                "id": strategy.id,
                "symbol": strategy.symbol,
                "strategy_type": strategy.strategy_type.value,
                "phase": strategy.phase.value,
                "enabled": strategy.enabled,
                "schedule_at": strategy.schedule_at.isoformat() if strategy.schedule_at else None,
            }
            for strategy in strategies
        ],
    }


def _portfolio_snapshot_payload(config: Config) -> dict[str, Any]:
    from kodiak.app.portfolio import get_balance

    try:
        balance = get_balance(config)
    except AppError as exc:
        return {
            "available": False,
            "error": exc.code,
            "message": exc.message,
            "suggestion": exc.suggestion,
        }

    return {
        "available": True,
        "market_open": balance.market_open,
        "account": balance.account.model_dump(mode="json"),
        "total_positions_value": str(balance.total_positions_value),
        "total_unrealized_pl": str(balance.total_unrealized_pl),
        "day_change": str(balance.day_change) if balance.day_change is not None else None,
        "day_change_pct": str(balance.day_change_pct) if balance.day_change_pct is not None else None,
        "positions": [position.model_dump(mode="json") for position in balance.positions],
    }


def _backtest_snapshot_payload(config: Config) -> dict[str, Any]:
    from kodiak.app.backtests import list_backtests_app

    backtests = list_backtests_app(data_dir=str(config.data_dir))
    duplicates = [bt for bt in backtests if bt.duplicate_group_size > 1 and bt.duplicate_rank == 1]
    open_runs = [bt for bt in backtests if bt.position_state == "open"]

    return {
        "count": len(backtests),
        "duplicate_group_count": len(duplicates),
        "open_position_count": len(open_runs),
        "recent": [bt.model_dump(mode="json") for bt in backtests[:5]],
    }


def _diagnostics_payload(report: dict[str, Any]) -> list[str]:
    diagnostics: list[str] = []
    if report.get("trade_count", 0) == 0:
        diagnostics.append(
            "No realized trades were found in the selected window; rely on portfolio and backtest sections for context."
        )

    strategy_snapshot = report.get("strategy_snapshot")
    if isinstance(strategy_snapshot, dict):
        if strategy_snapshot.get("count", 0) and strategy_snapshot.get("active_count", 0) == 0:
            diagnostics.append("Strategies exist, but none are currently active.")

    backtest_snapshot = report.get("backtest_snapshot")
    if isinstance(backtest_snapshot, dict):
        duplicate_groups = backtest_snapshot.get("duplicate_group_count", 0)
        if duplicate_groups:
            diagnostics.append(
                f"{duplicate_groups} saved backtest setup groups have duplicates; compare the newest run first."
            )
        open_position_count = backtest_snapshot.get("open_position_count", 0)
        if open_position_count:
            diagnostics.append(
                f"{open_position_count} saved backtests ended with an open position, so win-rate and trade-count metrics may look sparse."
            )

    portfolio_analytics = report.get("portfolio_analytics")
    if isinstance(portfolio_analytics, dict) and not portfolio_analytics.get("available", True):
        diagnostics.append(portfolio_analytics.get("message", "Portfolio analytics were unavailable."))

    return diagnostics


def _render_markdown(report: dict[str, Any]) -> str:
    params = report["parameters"]
    lines = [
        "# Kodiak Analysis Report",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Symbol: {params['symbol'] or 'ALL'}",
        f"- Lookback: {params['days']} days",
        f"- Trades: {report['trade_count']}",
        f"- Today's realized P/L: ${report['today_pnl']}",
        "",
    ]

    performance = report.get("trade_performance")
    if performance:
        summary = performance["summary"]
        lines.extend(
            [
                "## Trade Performance",
                "",
                f"- Win rate: {summary['win_rate']}%",
                f"- Net P/L: ${summary['net_profit']}",
                f"- Gross profit: ${summary['gross_profit']}",
                f"- Gross loss: ${summary['gross_loss']}",
                f"- Profit factor: {summary['profit_factor']}",
                "",
            ]
        )
    else:
        lines.extend(["## Trade Performance", "", "No trades found for the selected window.", ""])

    portfolio = report.get("portfolio_analytics")
    if portfolio:
        lines.extend(["## Portfolio Analytics", ""])
        if portfolio.get("available"):
            data = portfolio["data"]
            lines.extend(
                [
                    f"- Benchmark: {data['benchmark_symbol']}",
                    f"- Return: {data['cumulative_return_pct']}%",
                    f"- Benchmark return: {data['benchmark_return_pct']}%",
                    f"- Sharpe ratio: {data['sharpe_ratio']}",
                    f"- Max drawdown: {data['max_drawdown_pct']}%",
                    f"- Data source: {data['data_source']}",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    f"- Unavailable: {portfolio['error']}",
                    f"- Message: {portfolio['message']}",
                    "",
                ]
            )

    portfolio_snapshot = report.get("portfolio_snapshot")
    if portfolio_snapshot:
        lines.extend(["## Portfolio Snapshot", ""])
        if portfolio_snapshot.get("available"):
            account = portfolio_snapshot["account"]
            lines.extend(
                [
                    f"- Equity: ${account['equity']}",
                    f"- Cash: ${account['cash']}",
                    f"- Buying power: ${account['buying_power']}",
                    f"- Unrealized P/L: ${portfolio_snapshot['total_unrealized_pl']}",
                    f"- Open positions: {len(portfolio_snapshot['positions'])}",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    f"- Unavailable: {portfolio_snapshot['error']}",
                    f"- Message: {portfolio_snapshot['message']}",
                    "",
                ]
            )

    strategy_snapshot = report.get("strategy_snapshot")
    if strategy_snapshot:
        lines.extend(
            [
                "## Strategy Snapshot",
                "",
                f"- Configured strategies: {strategy_snapshot['count']}",
                f"- Active strategies: {strategy_snapshot['active_count']}",
                f"- Scheduled strategies: {strategy_snapshot['scheduled_count']}",
                "",
            ]
        )

    backtest_snapshot = report.get("backtest_snapshot")
    if backtest_snapshot:
        lines.extend(
            [
                "## Backtest Snapshot",
                "",
                f"- Saved backtests: {backtest_snapshot['count']}",
                f"- Duplicate setup groups: {backtest_snapshot['duplicate_group_count']}",
                f"- Runs with open positions: {backtest_snapshot['open_position_count']}",
                "",
            ]
        )

    lines.extend(["## Recent Trades", ""])
    trades = report.get("trade_history", [])
    if trades:
        lines.extend(
            [
                "| Time | Symbol | Side | Qty | Price | Total | Status |",
                "| --- | --- | --- | ---: | ---: | ---: | --- |",
            ]
        )
        for trade in trades:
            lines.append(
                "| {timestamp} | {symbol} | {side} | {quantity} | ${price} | ${total} | {status} |".format(
                    **trade
                )
            )
    else:
        lines.append("No trades found.")

    diagnostics = report.get("diagnostics", [])
    if diagnostics:
        lines.extend(["", "## Diagnostics", ""])
        lines.extend([f"- {item}" for item in diagnostics])

    return "\n".join(lines) + "\n"
