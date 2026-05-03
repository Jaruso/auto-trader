"""CLI entry point for Kodiak.

All business logic is delegated to the kodiak.app service layer.
This module handles:
- Click argument parsing
- Rich table formatting for human output
- JSON output when --json flag is used
- Error rendering (Rich or JSON based on mode)
"""

import json as json_lib
import os
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import click
from kodiak import __version__
from kodiak.audit import set_audit_source
from kodiak.errors import AppError
from kodiak.utils.config import Environment, load_config
from kodiak.utils.logging import setup_logging
from rich.console import Console
from rich.table import Table

console = Console()


# =============================================================================
# Helpers
# =============================================================================


def _handle_error(error: AppError, as_json: bool = False) -> None:
    """Render an AppError as Rich text or JSON."""
    if as_json:
        console.print(json_lib.dumps(error.to_dict(), indent=2))
    else:
        console.print(f"[red]Error: {error.message}[/red]")
        if error.suggestion:
            console.print(f"[dim]{error.suggestion}[/dim]")


def _json_output(data: object) -> None:
    """Print a Pydantic model or dict as JSON."""
    if hasattr(data, "model_dump_json"):
        console.print(data.model_dump_json(indent=2))  # type: ignore[union-attr]
    else:
        console.print(json_lib.dumps(data, indent=2, default=str))


def _get_json_flag(ctx: click.Context) -> bool:
    """Get the --json flag from context."""
    return ctx.obj.get("json", False)


def _append_bootstrap_debug_log(message: str) -> None:
    """Best-effort bootstrap logging that never blocks CLI startup."""
    log_path = os.getenv("KODIAK_CLI_DEBUG_LOG")
    debug_log = Path(log_path) if log_path else Path(tempfile.gettempdir()) / "kodiak_mcp_debug.log"

    try:
        debug_log.parent.mkdir(parents=True, exist_ok=True)
        with open(debug_log, "a") as f:
            f.write(f"{datetime.now().isoformat()} | {message}\n")
    except OSError:
        pass


# =============================================================================
# CLI Group
# =============================================================================


@click.group()
@click.version_option(version=__version__, prog_name="kodiak")
@click.option("--prod", is_flag=True, help="Use production environment (default: paper)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cli(ctx: click.Context, prod: bool, as_json: bool) -> None:
    """Kodiak - CLI-based automated trading system."""
    import sys
    import traceback

    try:
        _append_bootstrap_debug_log("CLI entry point called")

        ctx.ensure_object(dict)
        set_audit_source("cli")
        config = load_config(prod=prod)
        ctx.obj["config"] = config
        ctx.obj["json"] = as_json

        # Set up logging
        logger = setup_logging(log_dir=config.log_dir, log_to_file=True)
        ctx.obj["logger"] = logger

        _append_bootstrap_debug_log("CLI setup complete")
    except Exception as e:
        _append_bootstrap_debug_log(f"CLI error: {e}")
        _append_bootstrap_debug_log(traceback.format_exc())
        print(f"CLI initialization error: {e}", file=sys.stderr, flush=True)
        print(traceback.format_exc(), file=sys.stderr, flush=True)
        raise


# =============================================================================
# Status & Account Commands
# =============================================================================


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show current system status including engine state."""
    from kodiak.app.engine import get_engine_status

    config = ctx.obj["config"]
    as_json = _get_json_flag(ctx)

    try:
        result = get_engine_status(config)
        if as_json:
            _json_output(result)
        else:
            table = Table(title="Kodiak Status")
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")

            env_style = "yellow" if config.env == Environment.PAPER else "red bold"
            table.add_row("Environment", f"[{env_style}]{result.environment}[/{env_style}]")
            table.add_row("Service", result.service)
            table.add_row("Base URL", result.base_url)

            key_status = "Configured" if result.api_key_configured else "[red]Not Set[/red]"
            table.add_row("API Key", key_status)

            if result.running:
                table.add_row("Engine", f"[green]RUNNING[/green] (PID {result.pid})")
            else:
                table.add_row("Engine", "[yellow]NOT RUNNING[/yellow]")

            console.print(table)
    except AppError as e:
        _handle_error(e, as_json)


@cli.command()
@click.pass_context
def balance(ctx: click.Context) -> None:
    """Show account balance and portfolio summary."""
    from kodiak.app.portfolio import get_balance

    config = ctx.obj["config"]
    as_json = _get_json_flag(ctx)

    try:
        result = get_balance(config)
        if as_json:
            _json_output(result)
        else:
            table = Table(title="Account Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green", justify="right")

            acct = result.account
            table.add_row("Portfolio Value", f"${acct.portfolio_value:,.2f}")
            table.add_row("Equity", f"${acct.equity:,.2f}")
            table.add_row("Cash", f"${acct.cash:,.2f}")
            table.add_row("Buying Power", f"${acct.buying_power:,.2f}")

            if result.day_change is not None:
                change_style = "green" if result.day_change >= 0 else "red"
                sign = "+" if result.day_change >= 0 else ""
                table.add_row(
                    "Day's Change",
                    f"[{change_style}]{sign}${result.day_change:,.2f} "
                    f"({sign}{result.day_change_pct:.2f}%)[/{change_style}]",
                )

            if result.positions:
                pl_style = "green" if result.total_unrealized_pl >= 0 else "red"
                sign = "+" if result.total_unrealized_pl >= 0 else ""
                upl = f"[{pl_style}]{sign}${result.total_unrealized_pl:,.2f}[/{pl_style}]"
                table.add_row("Unrealized P/L", upl)
                table.add_row("Open Positions", str(len(result.positions)))

            table.add_row("", "")
            market_status = (
                "[green]OPEN[/green]" if result.market_open
                else "[yellow]CLOSED[/yellow]"
            )
            table.add_row("Market", market_status)
            table.add_row("Day Trades (5d)", str(acct.daytrade_count))
            if acct.pattern_day_trader:
                table.add_row("PDT Status", "[red]FLAGGED[/red]")

            console.print(table)
    except AppError as e:
        _handle_error(e, as_json)
    except Exception as e:
        if as_json:
            console.print(json_lib.dumps({"error": "UNEXPECTED", "message": str(e)}, indent=2))
        else:
            console.print(f"[red]Error fetching balance: {e}[/red]")


@cli.command()
@click.pass_context
def positions(ctx: click.Context) -> None:
    """Show current positions."""
    from kodiak.app.portfolio import get_positions

    config = ctx.obj["config"]
    as_json = _get_json_flag(ctx)

    try:
        positions_list = get_positions(config)
        if as_json:
            _json_output([p.model_dump() for p in positions_list])
        else:
            if not positions_list:
                console.print("[yellow]No open positions[/yellow]")
                return

            table = Table(title="Open Positions")
            table.add_column("Symbol", style="cyan")
            table.add_column("Qty", justify="right")
            table.add_column("Avg Price", justify="right")
            table.add_column("Current", justify="right")
            table.add_column("Market Value", justify="right")
            table.add_column("P/L", justify="right")
            table.add_column("P/L %", justify="right")

            for pos in positions_list:
                pl_style = "green" if pos.unrealized_pl >= 0 else "red"
                table.add_row(
                    pos.symbol,
                    str(pos.qty),
                    f"${pos.avg_entry_price:,.2f}",
                    f"${pos.current_price:,.2f}",
                    f"${pos.market_value:,.2f}",
                    f"[{pl_style}]${pos.unrealized_pl:,.2f}[/{pl_style}]",
                    f"[{pl_style}]{pos.unrealized_pl_pct:.2%}[/{pl_style}]",
                )

            console.print(table)
    except AppError as e:
        _handle_error(e, as_json)
    except Exception as e:
        if as_json:
            console.print(json_lib.dumps({"error": "UNEXPECTED", "message": str(e)}, indent=2))
        else:
            console.print(f"[red]Error fetching positions: {e}[/red]")


@cli.command()
@click.option("--all", "show_all", is_flag=True, help="Show all orders (including filled/canceled)")
@click.pass_context
def orders(ctx: click.Context, show_all: bool) -> None:
    """Show open orders."""
    from kodiak.app.orders import list_orders

    config = ctx.obj["config"]
    as_json = _get_json_flag(ctx)

    try:
        orders_list = list_orders(config, show_all=show_all)
        if as_json:
            _json_output([o.model_dump() for o in orders_list])
        else:
            if not orders_list:
                console.print("[yellow]No open orders[/yellow]")
                return

            table = Table(title="Orders" if show_all else "Open Orders")
            table.add_column("ID", style="dim", max_width=8)
            table.add_column("Symbol", style="cyan")
            table.add_column("Side", justify="center")
            table.add_column("Type", justify="center")
            table.add_column("Qty", justify="right")
            table.add_column("Price", justify="right")
            table.add_column("Status", justify="center")

            for order in orders_list:
                side_style = "green" if order.side == "buy" else "red"
                side_text = f"[{side_style}]{order.side.upper()}[/{side_style}]"

                if order.order_type == "market":
                    price_text = "MARKET"
                elif order.limit_price:
                    price_text = f"${order.limit_price:,.2f}"
                elif order.stop_price:
                    price_text = f"${order.stop_price:,.2f}"
                elif order.trail_percent:
                    price_text = f"{order.trail_percent}%"
                else:
                    price_text = "-"

                table.add_row(
                    order.id[:8],
                    order.symbol,
                    side_text,
                    order.order_type.upper(),
                    str(order.qty),
                    price_text,
                    order.status.upper(),
                )

            console.print(table)
    except AppError as e:
        _handle_error(e, as_json)
    except Exception as e:
        if as_json:
            console.print(json_lib.dumps({"error": "UNEXPECTED", "message": str(e)}, indent=2))
        else:
            console.print(f"[red]Error fetching orders: {e}[/red]")


@cli.command()
@click.pass_context
def portfolio(ctx: click.Context) -> None:
    """Show portfolio summary and performance."""
    from kodiak.app.portfolio import get_portfolio_summary

    config = ctx.obj["config"]
    as_json = _get_json_flag(ctx)

    try:
        result = get_portfolio_summary(config)
        if as_json:
            _json_output(result)
        else:
            # Summary table
            table = Table(title="Portfolio Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green", justify="right")

            table.add_row("Total Equity", f"${result.total_equity:,.2f}")
            table.add_row("Cash", f"${result.cash:,.2f}")
            table.add_row("Positions Value", f"${result.positions_value:,.2f}")
            table.add_row("Position Count", str(result.position_count))

            unreal_style = "green" if result.unrealized_pnl >= 0 else "red"
            real_style = "green" if result.realized_pnl_today >= 0 else "red"
            total_style = "green" if result.total_pnl_today >= 0 else "red"

            table.add_row(
                "Unrealized P/L",
                f"[{unreal_style}]${result.unrealized_pnl:,.2f} "
                f"({result.unrealized_pnl_pct:.2%})[/{unreal_style}]",
            )
            table.add_row(
                "Realized P/L (Today)",
                f"[{real_style}]${result.realized_pnl_today:,.2f}[/{real_style}]",
            )
            table.add_row(
                "Total P/L (Today)",
                f"[{total_style}]${result.total_pnl_today:,.2f}[/{total_style}]",
            )

            console.print(table)

            # Positions breakdown
            if result.positions:
                console.print()
                pos_table = Table(title="Position Breakdown")
                pos_table.add_column("Symbol", style="cyan")
                pos_table.add_column("Qty", justify="right")
                pos_table.add_column("Avg Cost", justify="right")
                pos_table.add_column("Current", justify="right")
                pos_table.add_column("Value", justify="right")
                pos_table.add_column("P/L", justify="right")
                pos_table.add_column("Weight", justify="right")

                for pos in result.positions:
                    pl_style = "green" if pos.unrealized_pnl >= 0 else "red"
                    pos_table.add_row(
                        pos.symbol,
                        str(pos.quantity),
                        f"${pos.avg_cost:,.2f}",
                        f"${pos.current_price:,.2f}",
                        f"${pos.market_value:,.2f}",
                        f"[{pl_style}]${pos.unrealized_pnl:,.2f}[/{pl_style}]",
                        f"{pos.weight_pct:.1f}%",
                    )

                console.print(pos_table)

    except AppError as e:
        _handle_error(e, as_json)
    except Exception as e:
        if as_json:
            console.print(json_lib.dumps({"error": "UNEXPECTED", "message": str(e)}, indent=2))
        else:
            console.print(f"[red]Error: {e}[/red]")


@cli.command()
@click.argument("symbol")
@click.pass_context
def quote(ctx: click.Context, symbol: str) -> None:
    """Get current quote for a symbol."""
    from kodiak.app.portfolio import get_quote

    config = ctx.obj["config"]
    as_json = _get_json_flag(ctx)

    try:
        result = get_quote(config, symbol)
        if as_json:
            _json_output(result)
        else:
            table = Table(title=f"Quote: {symbol.upper()}")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green", justify="right")

            table.add_row("Bid", f"${result.bid:,.2f}")
            table.add_row("Ask", f"${result.ask:,.2f}")
            table.add_row("Spread", f"${result.spread:,.2f}")

            console.print(table)
    except AppError as e:
        _handle_error(e, as_json)
    except Exception as e:
        if as_json:
            console.print(json_lib.dumps({"error": "UNEXPECTED", "message": str(e)}, indent=2))
        else:
            console.print(f"[red]Error fetching quote: {e}[/red]")


# =============================================================================
# Order Commands
# =============================================================================


@cli.command()
@click.argument("symbol")
@click.argument("price", type=float)
@click.option("--qty", type=int, default=1, help="Number of shares (default: 1)")
@click.pass_context
def buy(ctx: click.Context, symbol: str, price: float, qty: int) -> None:
    """Place a limit buy order.

    Example: trader buy TSLA 399.00 --qty 1
    """
    from kodiak.app.orders import place_order
    from kodiak.schemas.orders import OrderRequest

    config = ctx.obj["config"]
    as_json = _get_json_flag(ctx)

    try:
        request = OrderRequest(
            symbol=symbol, qty=qty,
            price=Decimal(str(price)), side="buy",
        )
        if not as_json:
            msg = f"Placing LIMIT BUY: {qty} {symbol.upper()} @ ${price:.2f}"
            console.print(f"[yellow]{msg}[/yellow]")

        result = place_order(config, request, confirm_execution=True)

        if as_json:
            _json_output(result)
        else:
            table = Table(title="Order Placed")
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Order ID", result.id)
            table.add_row("Symbol", result.symbol)
            table.add_row("Side", "BUY")
            table.add_row("Quantity", str(result.qty))
            table.add_row("Type", result.order_type.upper())
            if result.limit_price:
                table.add_row("Limit Price", f"${result.limit_price:,.2f}")
            table.add_row("Status", result.status.upper())

            console.print(table)
    except AppError as e:
        _handle_error(e, as_json)
    except Exception as e:
        if as_json:
            console.print(json_lib.dumps({"error": "UNEXPECTED", "message": str(e)}, indent=2))
        else:
            console.print(f"[red]Error placing order: {e}[/red]")


@cli.command()
@click.argument("symbol")
@click.argument("price", type=float)
@click.option("--qty", type=int, default=1, help="Number of shares (default: 1)")
@click.pass_context
def sell(ctx: click.Context, symbol: str, price: float, qty: int) -> None:
    """Place a limit sell order.

    Example: trader sell TSLA 420.00 --qty 1
    """
    from kodiak.app.orders import place_order
    from kodiak.schemas.orders import OrderRequest

    config = ctx.obj["config"]
    as_json = _get_json_flag(ctx)

    try:
        request = OrderRequest(
            symbol=symbol, qty=qty,
            price=Decimal(str(price)), side="sell",
        )
        if not as_json:
            msg = f"Placing LIMIT SELL: {qty} {symbol.upper()} @ ${price:.2f}"
            console.print(f"[yellow]{msg}[/yellow]")

        result = place_order(config, request, confirm_execution=True)

        if as_json:
            _json_output(result)
        else:
            table = Table(title="Order Placed")
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Order ID", result.id)
            table.add_row("Symbol", result.symbol)
            table.add_row("Side", "SELL")
            table.add_row("Quantity", str(result.qty))
            table.add_row("Type", result.order_type.upper())
            if result.limit_price:
                table.add_row("Limit Price", f"${result.limit_price:,.2f}")
            table.add_row("Status", result.status.upper())

            console.print(table)
    except AppError as e:
        _handle_error(e, as_json)
    except Exception as e:
        if as_json:
            console.print(json_lib.dumps({"error": "UNEXPECTED", "message": str(e)}, indent=2))
        else:
            console.print(f"[red]Error placing order: {e}[/red]")


@cli.command(name="reconcile-orders")
@click.option(
    "--orders-dir", type=click.Path(),
    help="Path to config directory containing orders.yaml",
)
@click.pass_context
def reconcile_orders(ctx: click.Context, orders_dir: str | None) -> None:
    """Reconcile locally persisted orders with broker state."""
    from kodiak.core.engine import TradingEngine

    config = ctx.obj["config"]
    as_json = _get_json_flag(ctx)

    try:
        from kodiak.app import get_broker
        broker = get_broker(config)
        orders_path = Path(orders_dir) if orders_dir else None
        engine = TradingEngine(broker, orders_dir=orders_path)

        if not as_json:
            console.print("Running reconciliation...")
        engine._reconcile_orders()
        if as_json:
            _json_output({"status": "completed"})
        else:
            console.print("[green]Reconciliation completed.[/green]")
    except AppError as e:
        _handle_error(e, as_json)
    except Exception as e:
        if as_json:
            console.print(json_lib.dumps({"error": "UNEXPECTED", "message": str(e)}, indent=2))
        else:
            console.print(f"[red]Reconciliation failed: {e}[/red]")


@cli.command()
@click.argument("order_id")
@click.pass_context
def cancel(ctx: click.Context, order_id: str) -> None:
    """Cancel an open order."""
    from kodiak.app.orders import cancel_order

    config = ctx.obj["config"]
    as_json = _get_json_flag(ctx)

    try:
        result = cancel_order(config, order_id, confirm_execution=True)
        if as_json:
            _json_output(result)
        else:
            console.print(f"[green]Order {order_id} canceled[/green]")
    except AppError as e:
        _handle_error(e, as_json)
    except Exception as e:
        if as_json:
            console.print(json_lib.dumps({"error": "UNEXPECTED", "message": str(e)}, indent=2))
        else:
            console.print(f"[red]Error canceling order: {e}[/red]")


# =============================================================================
# Engine Commands
# =============================================================================


@cli.command()
@click.option("--dry-run", is_flag=True, help="Evaluate strategies but don't execute trades")
@click.option("--interval", type=int, default=60, help="Poll interval in seconds")
@click.option("--once", is_flag=True, help="Run once and exit")
@click.option("--force", is_flag=True, help="Force start even if another engine might be running")
@click.pass_context
def start(ctx: click.Context, dry_run: bool, interval: int, once: bool, force: bool) -> None:
    """Start the trading engine.

    The engine will continuously monitor prices and execute trades
    based on your configured strategies.

    Only one engine can run at a time to prevent duplicate orders.

    Examples:

        Run in paper mode:
        trader start

        Dry run (no actual trades):
        trader start --dry-run

        Run once and exit:
        trader start --once

        Custom poll interval:
        trader start --interval 30

        Force start (use with caution):
        trader start --force

        Production mode:
        trader --prod start
    """
    from kodiak.app import get_broker
    from kodiak.audit import log_action as audit_log
    from kodiak.core.engine import EngineAlreadyRunningError, TradingEngine, get_lock_file_path
    from kodiak.policy import ActionType, add_policy_details, evaluate_execution_policy
    from kodiak.strategies.loader import load_strategies

    config = ctx.obj["config"]

    if not config.alpaca_api_key:
        env_var = "ALPACA_PROD_API_KEY" if config.is_prod else "ALPACA_API_KEY"
        console.print(f"[red]Error: {env_var} not configured[/red]")
        return

    # Interactive confirmation for production
    if config.is_prod:
        console.print("[red bold]\u26a0\ufe0f  PRODUCTION MODE \u26a0\ufe0f[/red bold]")
        svc = config.service.value
        console.print(f"[red]You are about to trade with REAL MONEY on {svc}[/red]")
        console.print(f"[dim]Using: {config.base_url}[/dim]")
        console.print()
        if not click.confirm("Are you sure you want to continue?", default=False):
            console.print("[yellow]Aborted.[/yellow]")
            return

    # Check for strategies
    active_strategies = load_strategies()
    active_strategies = [s for s in active_strategies if s.enabled and s.is_active()]

    if not active_strategies:
        console.print("[yellow]Warning: No active strategies configured[/yellow]")
        console.print("Add a strategy: trader strategy add trailing-stop AAPL --qty 10")
        if not once:
            return

    # Handle --force flag by removing stale lock file
    if force:
        lock_path = get_lock_file_path()
        if lock_path.exists():
            console.print("[yellow]Forcing start - removing existing lock file[/yellow]")
            try:
                lock_path.unlink()
            except Exception as e:
                console.print(f"[red]Error removing lock file: {e}[/red]")
                return

    broker = get_broker(config)
    engine = TradingEngine(
        broker,
        poll_interval=interval,
        dry_run=dry_run,
        strategy_defaults=config.strategy_defaults,
    )

    mode = "[yellow]DRY RUN[/yellow]" if dry_run else f"[green]{config.env.value.upper()}[/green]"
    console.print(f"Starting trading engine in {mode} mode...")
    console.print(f"Active strategies: {len(active_strategies)}")
    console.print(f"Poll interval: {interval}s")
    console.print("[dim]Press Ctrl+C to stop[/dim]")
    console.print()

    try:
        policy_decision = evaluate_execution_policy(
            "start_engine",
            action_type=ActionType.EXECUTE,
            execution_intent=True,
        )
        audit_log(
            "start_engine",
            add_policy_details(
                {
                    "dry_run": dry_run,
                    "interval": interval,
                    "once": once,
                    "force": force,
                },
                policy_decision,
            ),
            log_dir=config.log_dir,
        )
        if once:
            order_ids = engine.run_once(acquire_lock=True)
            if order_ids:
                console.print(f"[green]Executed {len(order_ids)} strategy actions[/green]")
            else:
                console.print("[yellow]No strategies triggered[/yellow]")
        else:
            engine.start()
    except EngineAlreadyRunningError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("[dim]Use --force to override (use with caution)[/dim]")


@cli.command("run-once")
@click.option("--dry-run", is_flag=True, help="Evaluate strategies but don't execute trades")
@click.option("--force", is_flag=True, help="Force run even if another engine might be running")
@click.pass_context
def run_once_cmd(ctx: click.Context, dry_run: bool, force: bool) -> None:
    """Run one evaluation cycle and exit (for schedule/cron).

    Does the same work as one loop iteration: scheduled strategy checks,
    market open check, then evaluate all active strategies. Use with
    'kodiak schedule enable' so cron runs this on a schedule.

    Examples:

        Single cycle (paper):
        trader run-once

        Dry run:
        trader run-once --dry-run

        In crontab (every 5 minutes):
        */5 * * * * trader run-once
    """
    from kodiak.app import get_broker
    from kodiak.audit import log_action as audit_log
    from kodiak.core.engine import EngineAlreadyRunningError, TradingEngine, get_lock_file_path
    from kodiak.policy import ActionType, add_policy_details, evaluate_execution_policy

    config = ctx.obj["config"]

    if not config.alpaca_api_key:
        env_var = "ALPACA_PROD_API_KEY" if config.is_prod else "ALPACA_API_KEY"
        console.print(f"[red]Error: {env_var} not configured[/red]")
        return

    if force:
        lock_path = get_lock_file_path()
        if lock_path.exists():
            try:
                lock_path.unlink()
            except Exception as e:
                console.print(f"[red]Error removing lock file: {e}[/red]")
                return

    broker = get_broker(config)
    engine = TradingEngine(
        broker,
        poll_interval=60,
        dry_run=dry_run,
        strategy_defaults=config.strategy_defaults,
    )

    try:
        policy_decision = evaluate_execution_policy(
            "run_once",
            action_type=ActionType.EXECUTE,
            execution_intent=True,
        )
        audit_log(
            "run_once",
            add_policy_details(
                {"dry_run": dry_run, "force": force},
                policy_decision,
            ),
            log_dir=config.log_dir,
        )
        order_ids = engine.run_once(acquire_lock=True)
        if order_ids:
            console.print(f"[green]Executed {len(order_ids)} strategy actions[/green]")
        else:
            console.print("[dim]No strategies triggered[/dim]")
    except EngineAlreadyRunningError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("[dim]Another cycle is running or the daemon is active. Use --force to override.[/dim]")


# =============================================================================
# Schedule (cron) Commands
# =============================================================================


@cli.group("schedule")
def schedule_group() -> None:
    """Enable or disable a cron job that runs one trading cycle on a schedule.

    When enabled, the system runs 'kodiak run-once' at the interval you choose
    (e.g. every 5 minutes). No long-running daemon is needed.

    Supported on macOS and Linux only.
    """
    pass


@schedule_group.command("enable")
@click.option("--every", type=int, default=5, help="Run every N minutes (1-60, default 5)")
def schedule_enable(every: int) -> None:
    """Install a cron job that runs 'kodiak run-once' on a schedule.

    The job is added to your user crontab. Use 'kodiak schedule disable' to remove it.

    Examples:

        Every 5 minutes (default):
        kodiak schedule enable

        Every minute:
        kodiak schedule enable --every 1

        Every 15 minutes:
        kodiak schedule enable --every 15
    """
    from kodiak_cli.schedule_cron import enable_schedule, get_kodiak_path

    try:
        enable_schedule(every_minutes=every)
        path = get_kodiak_path() or "kodiak"
        console.print(f"[green]Schedule enabled.[/green] Cron will run [bold]{path} run-once[/bold] every {every} minute(s).")
        console.print("[dim]View with: crontab -l. Remove with: kodiak schedule disable[/dim]")
    except (RuntimeError, ValueError) as e:
        console.print(f"[red]Error: {e}[/red]")


@schedule_group.command("disable")
def schedule_disable() -> None:
    """Remove the Kodiak cron job from your crontab."""
    from kodiak_cli.schedule_cron import disable_schedule, is_schedule_enabled

    if not is_schedule_enabled():
        console.print("[yellow]Schedule was not enabled (no Kodiak cron job found).[/yellow]")
        return
    try:
        disable_schedule()
        console.print("[green]Schedule disabled.[/green] Cron job removed.")
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/red]")


@schedule_group.command("status")
def schedule_status() -> None:
    """Show whether the schedule is enabled and the current cron line."""
    from kodiak_cli.schedule_cron import get_schedule_status

    status = get_schedule_status()
    if not status["supported"]:
        console.print("[yellow]Schedule (cron) is only supported on macOS and Linux.[/yellow]")
        return
    if status["enabled"]:
        console.print("[green]Schedule: enabled[/green]")
        console.print(f"  [dim]{status['line']}[/dim]")
    else:
        console.print("[dim]Schedule: disabled[/dim]")
        if status["kodiak_path"]:
            console.print("  Enable with: [bold]kodiak schedule enable[/bold] (default: every 5 minutes)")
        else:
            console.print("  [yellow]'kodiak' not on PATH; install with pipx so 'kodiak schedule enable' can add the cron job.[/yellow]")


@cli.command()
@click.option("--force", "-f", is_flag=True, help="Force immediate shutdown (SIGKILL)")
@click.pass_context
def stop(ctx: click.Context, force: bool) -> None:
    """Stop the running trading engine.

    By default, sends SIGTERM and waits for the current cycle to complete.
    Use --force/-f to immediately kill the engine.

    Examples:

        Graceful stop (waits for cycle):
        trader stop

        Force immediate shutdown:
        trader stop --force
        trader stop -f
    """
    from kodiak.app.engine import stop_engine

    as_json = _get_json_flag(ctx)

    try:
        result = stop_engine(force=force, confirm_execution=True)
        if as_json:
            _json_output(result)
        else:
            if result["status"] == "killed":
                console.print(f"[yellow]Force killed trading engine (PID {result['pid']})[/yellow]")
            elif result["status"] == "stopping":
                pid = result['pid']
                console.print(f"[green]Sent shutdown signal to trading engine (PID {pid})[/green]")
                console.print("[dim]Engine will stop after current cycle completes[/dim]")
            else:
                console.print("[yellow]Engine already stopped[/yellow]")
    except AppError as e:
        _handle_error(e, as_json)


@cli.command()
@click.pass_context
def watch(ctx: click.Context) -> None:
    """Watch prices for symbols in your strategies."""
    from kodiak.app.portfolio import watch_strategies

    config = ctx.obj["config"]
    as_json = _get_json_flag(ctx)

    try:
        results = watch_strategies(config)
        if as_json:
            _json_output(results)
        else:
            if not results:
                console.print("[yellow]No strategies configured[/yellow]")
                return

            table = Table(title="Price Watch")
            table.add_column("Symbol", style="cyan")
            table.add_column("Bid", justify="right")
            table.add_column("Ask", justify="right")
            table.add_column("Strategies")

            for item in results:
                if "error" in item:
                    table.add_row(item["symbol"], "[red]Error[/red]", str(item["error"]), "-")
                else:
                    table.add_row(
                        item["symbol"],
                        f"${Decimal(item['bid']):,.2f}",
                        f"${Decimal(item['ask']):,.2f}",
                        ", ".join(item["strategies"]) if item["strategies"] else "-",
                    )

            console.print(table)
    except AppError as e:
        _handle_error(e, as_json)


# =============================================================================
# History & Analysis Commands
# =============================================================================


@cli.command()
@click.option("--symbol", help="Filter by symbol")
@click.option("--limit", type=int, default=20, help="Number of trades to show")
@click.pass_context
def history(ctx: click.Context, symbol: str | None, limit: int) -> None:
    """Show trade history."""
    from kodiak.app.analysis import get_today_pnl, get_trade_history

    as_json = _get_json_flag(ctx)

    trades = get_trade_history(symbol=symbol, limit=limit)

    if as_json:
        _json_output(trades)
        return

    if not trades:
        console.print("[yellow]No trades recorded[/yellow]")
        return

    table = Table(title=f"Trade History{f' - {symbol}' if symbol else ''}")
    table.add_column("Time", style="dim")
    table.add_column("Symbol", style="cyan")
    table.add_column("Side")
    table.add_column("Qty", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Status")

    for trade in trades:
        ts = datetime.fromisoformat(trade["timestamp"])
        side_val = trade["side"]
        side_style = "green" if side_val == "buy" else "red"
        time_str = ts.strftime("%m/%d %H:%M")
        table.add_row(
            time_str,
            trade["symbol"],
            f"[{side_style}]{side_val.upper()}[/{side_style}]",
            trade["quantity"],
            f"${Decimal(trade['price']):,.2f}",
            f"${Decimal(trade['total']):,.2f}",
            trade["status"].upper(),
        )

    console.print(table)

    today_pnl = get_today_pnl()
    pnl_style = "green" if today_pnl >= 0 else "red"
    console.print(f"\nToday's Realized P/L: [{pnl_style}]${today_pnl:,.2f}[/{pnl_style}]")


@cli.command()
@click.option("--symbol", help="Filter by symbol")
@click.option("--days", type=int, default=30, help="Analyze trades from last N days")
@click.option("--limit", type=int, default=1000, help="Max trades to analyze")
@click.pass_context
def analyze(ctx: click.Context, symbol: str | None, days: int, limit: int) -> None:
    """Analyze trade performance."""
    from kodiak.app.analysis import analyze_trade_performance

    as_json = _get_json_flag(ctx)

    result = analyze_trade_performance(symbol=symbol, days=days, limit=limit)
    if result is None:
        if as_json:
            _json_output({"trades": 0, "message": "No trades recorded for analysis"})
        else:
            console.print("[yellow]No trades recorded for analysis[/yellow]")
        return

    if as_json:
        _json_output(result)
        return

    summary = result.summary

    title = f"Trade Analysis{f' - {symbol}' if symbol else ''}"
    table = Table(title=title)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Trades", str(summary.total_trades))
    table.add_row("Winning Trades", f"{summary.winning_trades} ({summary.win_rate:.1f}%)")
    table.add_row("Gross Profit", f"${summary.gross_profit:,.2f}")
    table.add_row("Gross Loss", f"-${summary.gross_loss:,.2f}")

    net_style = "green" if summary.net_profit >= 0 else "red"
    table.add_row("Net P/L", f"[{net_style}]${summary.net_profit:,.2f}[/{net_style}]")

    profit_factor = "N/A"
    if summary.gross_loss > 0:
        profit_factor = f"{summary.profit_factor:.2f}"
    table.add_row("Profit Factor", profit_factor)

    table.add_row("Avg Win", f"${summary.avg_win:,.2f}")
    table.add_row("Avg Loss", f"${summary.avg_loss:,.2f}")
    table.add_row("Largest Win", f"${summary.largest_win:,.2f}")
    table.add_row("Largest Loss", f"${summary.largest_loss:,.2f}")
    table.add_row("Avg Hold (min)", f"{summary.avg_hold_minutes:.1f}")

    console.print(table)

    if result.per_symbol:
        symbol_table = Table(title="Per-Symbol Performance")
        symbol_table.add_column("Symbol", style="cyan")
        symbol_table.add_column("Trades", justify="right")
        symbol_table.add_column("Win %", justify="right")
        symbol_table.add_column("Net P/L", justify="right")
        symbol_table.add_column("Profit Factor", justify="right")

        for sym, stats in sorted(result.per_symbol.items()):
            s_net_style = "green" if stats.net_profit >= 0 else "red"
            pf_display = "N/A" if stats.gross_loss == 0 else f"{stats.profit_factor:.2f}"
            symbol_table.add_row(
                sym,
                str(stats.total_trades),
                f"{stats.win_rate:.1f}%",
                f"[{s_net_style}]${stats.net_profit:,.2f}[/{s_net_style}]",
                pf_display,
            )

        console.print(symbol_table)

    if result.open_positions:
        open_table = Table(title="Open Lots (Unmatched Buys)")
        open_table.add_column("Symbol", style="cyan")
        open_table.add_column("Lots", justify="right")
        open_table.add_column("Qty", justify="right")
        open_table.add_column("Avg Cost", justify="right")

        for pos in result.open_positions:
            open_table.add_row(
                pos.symbol,
                str(pos.lots),
                str(pos.quantity),
                f"${pos.avg_cost:,.2f}",
            )

        console.print(open_table)

    remaining_sells = {k: v for k, v in result.unmatched_sell_qty.items() if v > 0}
    if remaining_sells:
        console.print("[yellow]Warning: sells without matching buys detected.[/yellow]")


@cli.command()
@click.argument("output", type=click.Path())
@click.option("--days", type=int, default=30, help="Export trades from last N days")
@click.pass_context
def export(ctx: click.Context, output: str, days: int) -> None:
    """Export trade history to CSV."""
    from kodiak.data.ledger import TradeLedger

    ledger = TradeLedger()
    since = datetime.now() - timedelta(days=days)
    path = Path(output)

    count = ledger.export_csv(path, since=since)
    as_json = _get_json_flag(ctx)
    if as_json:
        _json_output({"exported": count, "path": str(path)})
    else:
        console.print(f"[green]Exported {count} trades to {path}[/green]")


@cli.command("analysis-report")
@click.option("--output", "-o", type=click.Path(), help="Write report to a file")
@click.option(
    "--format",
    "report_format",
    type=click.Choice(["json", "markdown"]),
    default="json",
    show_default=True,
    help="Report output format",
)
@click.option("--symbol", help="Filter by symbol")
@click.option("--days", type=int, default=30, show_default=True, help="Analyze trades from last N days")
@click.option("--limit", type=int, default=1000, show_default=True, help="Max trades to include")
@click.option(
    "--include-portfolio/--no-include-portfolio",
    default=False,
    show_default=True,
    help="Include portfolio analytics when broker/data config is available",
)
@click.option(
    "--portfolio-lookback-days",
    type=int,
    default=252,
    show_default=True,
    help="Lookback window for portfolio analytics",
)
@click.option(
    "--benchmark-symbol",
    default="SPY",
    show_default=True,
    help="Benchmark symbol for portfolio analytics",
)
@click.pass_context
def analysis_report(
    ctx: click.Context,
    output: str | None,
    report_format: str,
    symbol: str | None,
    days: int,
    limit: int,
    include_portfolio: bool,
    portfolio_lookback_days: int,
    benchmark_symbol: str,
) -> None:
    """Generate a headless analysis report."""
    from kodiak.app.reports import ReportFormat, export_analysis_report

    config = ctx.obj["config"]
    as_json = _get_json_flag(ctx)

    try:
        result = export_analysis_report(
            config,
            output_path=output,
            format=cast(ReportFormat, report_format),
            symbol=symbol,
            days=days,
            limit=limit,
            include_portfolio=include_portfolio,
            portfolio_lookback_days=portfolio_lookback_days,
            benchmark_symbol=benchmark_symbol,
        )
    except AppError as e:
        _handle_error(e, as_json)
        return

    if as_json:
        _json_output(result)
        return

    if output:
        console.print(
            f"[green]Wrote {report_format} analysis report to {result['path']} ({result['bytes']} bytes)[/green]"
        )
        return

    console.print(result["content"])


# =============================================================================
# Safety Commands
# =============================================================================


@cli.command()
@click.pass_context
def safety(ctx: click.Context) -> None:
    """Show safety controls status."""
    from kodiak.app.data import get_safety_status

    config = ctx.obj["config"]
    as_json = _get_json_flag(ctx)

    try:
        result = get_safety_status(config)
        if as_json:
            _json_output(result)
        else:
            status = result["status"]
            limits_data = result["limits"]

            table = Table(title="Safety Controls")
            table.add_column("Control", style="cyan")
            table.add_column("Status", justify="right")
            table.add_column("Limit", justify="right")

            kill_status = "[red]ACTIVE[/red]" if status["kill_switch"] else "[green]OFF[/green]"
            table.add_row("Kill Switch", kill_status, "-")

            pnl = status["daily_pnl"]
            pnl_style = "green" if pnl >= 0 else "red"
            remaining = status["daily_pnl_remaining"]
            table.add_row(
                "Daily P/L",
                f"[{pnl_style}]${pnl:,.2f}[/{pnl_style}]",
                f"${status['daily_pnl_limit']:,.2f}",
            )
            table.add_row("Loss Remaining", f"${remaining:,.2f}", "-")

            trades_count = status["trade_count"]
            trade_limit = status["trade_limit"]
            pct = trades_count / trade_limit * 100 if trade_limit > 0 else 0
            table.add_row("Trades Today", f"{trades_count} ({pct:.0f}%)", str(trade_limit))
            table.add_row("Trades Remaining", str(status["trades_remaining"]), "-")

            can_trade = status["can_trade"]
            trade_status = "[green]YES[/green]" if can_trade else "[red]NO[/red]"
            table.add_row("Can Trade", trade_status, "-")

            console.print(table)

            # Position limits
            console.print()
            limit_table = Table(title="Position Limits")
            limit_table.add_column("Limit", style="cyan")
            limit_table.add_column("Value", justify="right")

            limit_table.add_row("Max Position Size", f"{limits_data['max_position_size']} shares")
            mpv = Decimal(limits_data['max_position_value'])
            mov = Decimal(limits_data['max_order_value'])
            limit_table.add_row("Max Position Value", f"${mpv:,.2f}")
            limit_table.add_row("Max Order Value", f"${mov:,.2f}")
            limit_table.add_row("Max Daily Loss", f"${Decimal(limits_data['max_daily_loss']):,.2f}")
            limit_table.add_row("Max Daily Trades", str(limits_data["max_daily_trades"]))

            console.print(limit_table)

    except AppError as e:
        _handle_error(e, as_json)
    except Exception as e:
        if as_json:
            console.print(json_lib.dumps({"error": "UNEXPECTED", "message": str(e)}, indent=2))
        else:
            console.print(f"[red]Error: {e}[/red]")


@cli.command()
@click.pass_context
def kill(ctx: click.Context) -> None:
    """Activate kill switch - stops all automated trading."""
    as_json = _get_json_flag(ctx)
    if as_json:
        _json_output({"status": "kill_switch_activated"})
    else:
        console.print("[red]KILL SWITCH ACTIVATED[/red]")
        console.print("All automated trading is now stopped.")
        console.print("Manual trades via buy/sell commands are still allowed.")
        console.print("\nTo reset, restart the trading engine.")


@cli.command()
@click.argument("symbols", nargs=-1)
@click.pass_context
def scan(ctx: click.Context, symbols: tuple[str, ...]) -> None:
    """Scan symbols for current prices.

    Examples:

        Scan specific symbols:
        trader scan AAPL TSLA GOOGL

        Scan all symbols in strategies:
        trader scan
    """
    from kodiak.app.portfolio import scan_symbols

    config = ctx.obj["config"]
    as_json = _get_json_flag(ctx)

    try:
        results = scan_symbols(config, list(symbols) if symbols else None)
        if as_json:
            _json_output(results)
        else:
            if not results:
                console.print("[yellow]No symbols to scan[/yellow]")
                console.print("Provide symbols: trader scan AAPL TSLA")
                return

            table = Table(title="Market Scan")
            table.add_column("Symbol", style="cyan")
            table.add_column("Bid", justify="right")
            table.add_column("Ask", justify="right")
            table.add_column("Spread", justify="right")
            table.add_column("Strategies")

            for item in results:
                if "error" in item:
                    table.add_row(item["symbol"], "[red]Error[/red]", "-", "-", str(item["error"]))
                else:
                    table.add_row(
                        item["symbol"],
                        f"${Decimal(item['bid']):,.2f}",
                        f"${Decimal(item['ask']):,.2f}",
                        f"${Decimal(item['spread']):.2f} ({Decimal(item['spread_pct']):.2f}%)",
                        ", ".join(item["strategies"]) if item["strategies"] else "-",
                    )

            console.print(table)
    except AppError as e:
        _handle_error(e, as_json)


# =============================================================================
# Config Commands (CLI-only: set/list/get env-based config; secrets redacted)
# =============================================================================


@cli.group("config")
def config_group() -> None:
    """View and set environment-based configuration (API keys, URLs, etc.).

    Values are read from environment variables; use 'kodiak config set' to
    persist them to a .env file. Secrets are never shown in full when listing.
    """
    pass


@config_group.command("list")
@click.option("--show-secrets", is_flag=True, help="Show secret values in full (use with care)")
@click.pass_context
def config_list(ctx: click.Context, show_secrets: bool) -> None:
    """List current configuration (secrets redacted by default)."""
    from kodiak.utils.env_config import (
        CONFIG_KEYS,
        get_config_value,
        get_display_value,
        get_env_file_path,
        load_dotenv_for_config,
    )

    load_dotenv_for_config()
    as_json = _get_json_flag(ctx)

    rows = []
    for key in sorted(CONFIG_KEYS.keys()):
        desc = CONFIG_KEYS[key][1]
        value = get_config_value(key)
        display = get_display_value(key, value, redact_secrets=not show_secrets)
        rows.append({"key": key, "value": display, "description": desc})

    if as_json:
        _json_output(rows)
        return

    table = Table(title="Configuration")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Description", style="dim")
    for r in rows:
        table.add_row(r["key"], r["value"], r["description"])
    console.print(table)
    env_path = get_env_file_path()
    console.print(f"\n[dim]Config file: {env_path}[/dim]")


@config_group.command("get")
@click.argument("key", required=True)
@click.option("--show-secret", is_flag=True, help="Show secret value in full")
@click.pass_context
def config_get(ctx: click.Context, key: str, show_secret: bool) -> None:
    """Get a single config value (secret redacted unless --show-secret)."""
    from kodiak.utils.env_config import (
        CONFIG_KEYS,
        get_config_value,
        get_display_value,
        load_dotenv_for_config,
    )

    load_dotenv_for_config()
    as_json = _get_json_flag(ctx)
    key = key.strip()
    # Normalize to known key if present (e.g. alpaca_api_key -> ALPACA_API_KEY)
    lookup_key = key.upper() if key.upper() in CONFIG_KEYS else key
    value = get_config_value(lookup_key)
    display = get_display_value(lookup_key, value, redact_secrets=not show_secret)

    if as_json:
        _json_output({"key": lookup_key, "value": display})
        return
    console.print(display)


@config_group.command("set")
@click.argument("key", required=True)
@click.argument("value", required=True)
@click.pass_context
def config_set(ctx: click.Context, key: str, value: str) -> None:
    """Set a config value (persisted to .env in config directory)."""
    from kodiak.utils.env_config import (
        CONFIG_KEYS,
        get_env_file_path,
        load_dotenv_for_config,
        set_config_value,
    )

    load_dotenv_for_config()
    key = key.strip()
    key_upper = key.upper()
    if key_upper in CONFIG_KEYS:
        key = key_upper  # normalize to known key
    try:
        set_config_value(key, value)
    except ValueError as e:
        if not ctx.obj.get("json"):
            console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)

    as_json = _get_json_flag(ctx)
    if as_json:
        _json_output({"ok": True, "key": key, "message": "Value set"})
    else:
        console.print(f"[green]Set {key}[/green]")
        console.print(f"[dim]Saved to {get_env_file_path()}[/dim]")


@config_group.command("keys")
@click.pass_context
def config_keys(ctx: click.Context) -> None:
    """List available config keys and descriptions (no values)."""
    from kodiak.utils.env_config import CONFIG_KEYS

    as_json = _get_json_flag(ctx)
    rows = [{"key": k, "description": CONFIG_KEYS[k][1], "secret": CONFIG_KEYS[k][0]} for k in sorted(CONFIG_KEYS)]
    if as_json:
        _json_output(rows)
        return
    table = Table(title="Available config keys")
    table.add_column("Key", style="cyan")
    table.add_column("Description", style="green")
    table.add_column("Secret", justify="center")
    for r in rows:
        table.add_row(r["key"], r["description"], "yes" if r["secret"] else "no")
    console.print(table)


# =============================================================================
# Strategy Commands
# =============================================================================



STRATEGY_HELP = {
    "trailing-stop": """
TRAILING STOP STRATEGY

Rides the trend and locks in gains. When price rises, the stop follows.
When price drops by the trailing percentage, it sells to protect profits.

Best for: Trending stocks you want to hold but protect gains

Example:
    trader strategy add trailing-stop AAPL --qty 10 --trailing-pct 5

    This buys 10 AAPL at market price. As price rises, a trailing stop
    follows 5% behind. If price drops 5% from any high, sells to lock profit.
""",
    "bracket": """
BRACKET STRATEGY

Defined risk/reward with both take-profit and stop-loss. Whichever hits
first closes the position. Classic risk management approach.

Best for: Trades where you know your target and max acceptable loss

Example:
    trader strategy add bracket TSLA --qty 5 --take-profit 10 --stop-loss 5

    Buys 5 TSLA. Sets take-profit at +10% and stop-loss at -5%.
    First one hit closes the position.
""",
    "scale-out": """
SCALE OUT STRATEGY

Captures gains progressively while letting winners run. Sells portions
of your position at different profit targets.

Best for: Strong conviction plays where you want to lock some gains

Example:
    trader strategy add scale-out GOOGL --qty 30

    Buys 30 shares. Default targets: sell 33% at +5%, 33% at +10%, 34% at +15%.
""",
    "grid": """
GRID STRATEGY

Profits from sideways volatility by buying at regular intervals on the
way down and selling on the way up. Works best in ranging markets.

Best for: Stocks that trade in a predictable range

Example:
    trader strategy add grid NVDA --qty 50 --levels 5

    Creates a grid with 5 buy levels below current price and
    5 sell levels above. Profits from price oscillation.
""",
    "pullback-trailing": """
PULLBACK-TRAILING STRATEGY

Wait for a pullback (price drops X% from the recent high), then buy at market.
Once in the position, manage the exit with a trailing stop. Holistic
"buy the dip + trail gains" strategy.

Best for: Names you want to own but prefer to buy on weakness

Example:
    trader strategy add pullback-trailing SOFI --qty 300 --pullback-pct 5 --trailing-pct 5

    Watches SOFI; on first run sets reference = current price. Each cycle
    reference = max(reference, current price). When price drops 5%% from
    reference, buys 300 shares at market. Then a 5%% trailing stop manages the exit.
""",
}


@cli.group()
def strategy() -> None:
    """Manage trading strategies.

    Strategies are automated trading plans that handle both entry and exit.
    Unlike simple rules that fire once, strategies manage the complete trade
    lifecycle.

    Available strategies:
    - trailing-stop: Ride trends, lock in gains with trailing stop
    - bracket: Defined risk/reward with take-profit and stop-loss
    - pullback-trailing: Wait for X% pullback, then buy; exit with trailing stop
    - scale-out: Sell portions at progressive profit targets
    - grid: Profit from sideways volatility

    Run 'kodiak strategy add --help' for more details.
    """
    pass


@cli.group()
def indicator() -> None:
    """Work with technical indicators."""
    pass


@indicator.command("list")
@click.pass_context
def indicator_list(ctx: click.Context) -> None:
    """List available indicators."""
    from kodiak.app.indicators import list_all_indicators

    as_json = _get_json_flag(ctx)

    indicators = list_all_indicators()
    if as_json:
        _json_output([i.model_dump() for i in indicators])
    else:
        table = Table(title="Indicators")
        table.add_column("Name", style="cyan")
        table.add_column("Description", style="white")
        table.add_column("Params", style="green")

        for spec in indicators:
            params = ", ".join(f"{k}" for k in spec.params.keys()) if spec.params else "-"
            table.add_row(spec.name, spec.description, params)

        console.print(table)


@indicator.command("describe")
@click.argument("name")
@click.pass_context
def indicator_describe(ctx: click.Context, name: str) -> None:
    """Show details for an indicator."""
    from kodiak.app.indicators import describe_indicator

    as_json = _get_json_flag(ctx)

    try:
        result = describe_indicator(name)
        if as_json:
            _json_output(result)
        else:
            table = Table(title=f"Indicator - {result.name}")
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="white")

            table.add_row("Description", result.description)
            table.add_row("Output", result.output or "-")
            params = (
                ", ".join(f"{k}: {v}" for k, v in result.params.items())
                if result.params else "-"
            )
            table.add_row("Params", params)

            console.print(table)
    except AppError as e:
        _handle_error(e, as_json)


# =============================================================================
# Notify Commands
# =============================================================================


@cli.group()
def notify() -> None:
    """Send and test notifications (Discord, webhook).

    Configure via DISCORD_WEBHOOK_URL or config/notifications.yaml.
    """
    pass


@notify.command("test")
@click.option(
    "--channel",
    type=click.Choice(["discord", "webhook", "all"]),
    default="all",
    help="Channel to test (default: all enabled)",
)
@click.pass_context
def notify_test(ctx: click.Context, channel: str) -> None:
    """Send a test notification to verify channel configuration."""
    from kodiak.app.notifications import get_notification_manager, send_test_notification
    from kodiak.utils.paths import get_config_dir

    as_json = _get_json_flag(ctx)
    config_dir = get_config_dir()

    manager = get_notification_manager(config_dir=config_dir)
    if not manager.enabled:
        if as_json:
            _json_output({"ok": False, "message": "No notification channels configured"})
        else:
            console.print(
                "[yellow]No notification channels configured.[/yellow]\n"
                "Set DISCORD_WEBHOOK_URL or CUSTOM_WEBHOOK_URL, or add config/notifications.yaml"
            )
        return

    ok = send_test_notification(channel=channel, config_dir=config_dir)
    if as_json:
        _json_output({"ok": ok, "channel": channel})
    else:
        if ok:
            console.print(f"[green]Test notification sent to {channel}[/green]")
        else:
            console.print(f"[red]Failed to send test to {channel}[/red]")


@notify.command("send")
@click.argument("message", required=True)
@click.option(
    "--channel",
    type=click.Choice(["discord", "webhook", "all"]),
    default="all",
    help="Channel to send to (default: all)",
)
@click.pass_context
def notify_send(ctx: click.Context, message: str, channel: str) -> None:
    """Send a manual notification message."""
    from kodiak.app.notifications import get_notification_manager, send_notification
    from kodiak.utils.paths import get_config_dir

    as_json = _get_json_flag(ctx)
    config_dir = get_config_dir()

    manager = get_notification_manager(config_dir=config_dir)
    if not manager.enabled:
        if as_json:
            _json_output({"ok": False, "message": "No channels configured"})
        else:
            console.print("[yellow]No notification channels configured.[/yellow]")
        return

    send_notification(message, channel=channel, config_dir=config_dir)
    if as_json:
        _json_output({"ok": True, "channel": channel})
    else:
        console.print(f"[green]Message sent to {channel}[/green]")


@strategy.command("list")
@click.pass_context
def strategy_list(ctx: click.Context) -> None:
    """List all trading strategies."""
    from kodiak.app.strategies import list_strategies

    as_json = _get_json_flag(ctx)
    result = list_strategies()

    if as_json:
        _json_output(result)
        return

    if not result.strategies:
        console.print("[yellow]No strategies configured[/yellow]")
        console.print("\nAdd a strategy with:")
        console.print("  trader strategy add trailing-stop AAPL --qty 10")
        console.print("\nSee available strategies:")
        console.print("  trader strategy add --help")
        return

    table = Table(title="Trading Strategies")
    table.add_column("ID", style="dim")
    table.add_column("Symbol", style="cyan")
    table.add_column("Type")
    table.add_column("Qty", justify="right")
    table.add_column("Phase")
    table.add_column("Details")

    for s in result.strategies:
        # Phase styling
        phase_styles = {
            "pending": "[yellow]PENDING[/yellow]",
            "entry_active": "[blue]ENTERING[/blue]",
            "position_open": "[green]OPEN[/green]",
            "exiting": "[blue]EXITING[/blue]",
            "completed": "[dim]DONE[/dim]",
            "failed": "[red]FAILED[/red]",
            "paused": "[yellow]PAUSED[/yellow]",
        }
        phase_str = phase_styles.get(s.phase, s.phase)

        if not s.enabled:
            phase_str = "[dim]DISABLED[/dim]"

        # Build details string
        details = []
        stype = s.strategy_type
        if stype == "trailing_stop":
            details.append(f"trail: {s.trailing_stop_pct}%")
            if s.high_watermark:
                details.append(f"high: ${s.high_watermark:.2f}")
        elif stype == "pullback_trailing":
            details.append(f"pullback: {s.pullback_pct}%")
            details.append(f"trail: {s.trailing_stop_pct}%")
            if getattr(s, "pullback_reference_price", None):
                details.append(f"ref: ${float(s.pullback_reference_price):.2f}")
        elif stype == "bracket":
            details.append(f"TP: +{s.take_profit_pct}%")
            details.append(f"SL: -{s.stop_loss_pct}%")
        elif stype == "scale_out":
            if s.scale_targets:
                targets = [f"+{t['target_pct']}%" for t in s.scale_targets]
                details.append(f"targets: {', '.join(targets)}")

        if s.entry_fill_price:
            details.insert(0, f"entry: ${s.entry_fill_price:.2f}")

        table.add_row(
            s.id,
            s.symbol,
            s.strategy_type.replace("_", "-"),
            str(s.quantity),
            phase_str,
            " | ".join(details) if details else "-",
        )

    console.print(table)


@strategy.command("add")
@click.argument("strategy_type", type=click.Choice([
    "trailing-stop", "bracket", "scale-out", "grid", "pullback-trailing",
]))
@click.argument("symbol")
@click.option("--qty", type=int, default=1, help="Number of shares (default: 1)")
@click.option("--trailing-pct", type=float, help="Trailing stop percentage (for trailing-stop and pullback-trailing)")
@click.option("--pullback-pct", type=float, help="Pullback % from high to trigger buy (for pullback-trailing, default: 5)")
@click.option("--take-profit", type=float, help="Take profit percentage (for bracket)")
@click.option("--stop-loss", type=float, help="Stop loss percentage (for bracket)")
@click.option("--limit", "-L", type=float, help="Limit price for entry (default: market order)")
@click.option("--levels", type=int, help="Number of grid levels (for grid)")
@click.pass_context
def strategy_add(
    ctx: click.Context,
    strategy_type: str,
    symbol: str,
    qty: int,
    trailing_pct: float | None,
    pullback_pct: float | None,
    take_profit: float | None,
    stop_loss: float | None,
    limit: float | None,
    levels: int | None,
) -> None:
    """Add a new trading strategy.

    STRATEGY TYPES:

    \b
    trailing-stop     Ride trends, lock in gains with a trailing stop
    bracket           Take-profit AND stop-loss (OCO style)
    scale-out         Sell portions at progressive profit targets
    grid              Buy low intervals, sell high intervals
    pullback-trailing Wait for X% pullback from high, then buy; exit with trailing stop

    \b
    EXAMPLES:
        trader strategy add trailing-stop AAPL --qty 10 --trailing-pct 5
        trader strategy add bracket TSLA --qty 5 --take-profit 10 --stop-loss 5
        trader strategy add pullback-trailing SOFI --qty 300 --pullback-pct 5 --trailing-pct 5
        trader strategy add scale-out GOOGL --qty 20
        trader strategy add grid NVDA --levels 5

    Use --limit/-L to enter at a specific price instead of market.
    """
    from kodiak.app.strategies import create_strategy
    from kodiak.schemas.strategies import StrategyCreate

    config = ctx.obj["config"]
    as_json = _get_json_flag(ctx)

    try:
        request = StrategyCreate(
            strategy_type=strategy_type,
            symbol=symbol,
            qty=qty,
            trailing_pct=trailing_pct,
            pullback_pct=pullback_pct,
            take_profit=take_profit,
            stop_loss=stop_loss,
            entry_price=limit,
            levels=levels,
        )
        result = create_strategy(config, request)

        if as_json:
            _json_output(result)
        else:
            console.print(f"[green]Strategy added:[/green] {strategy_type} {qty} {symbol.upper()}")
            console.print(f"[dim]ID: {result.id}[/dim]")
            entry_str = f"limit @ ${limit:.2f}" if limit else "market"
            console.print(f"[dim]Entry: {entry_str}[/dim]")

            # Build detail string for display
            stype = result.strategy_type
            if stype == "trailing_stop":
                console.print(f"[dim]trailing stop: {result.trailing_stop_pct}%[/dim]")
            elif stype == "bracket":
                tp = result.take_profit_pct
                sl = result.stop_loss_pct
                console.print(f"[dim]take-profit: +{tp}%, stop-loss: -{sl}%[/dim]")
            elif stype == "scale_out" and result.scale_targets:
                targets = [f"+{t['target_pct']}%" for t in result.scale_targets]
                console.print(f"[dim]targets: {', '.join(targets)}[/dim]")
            elif stype == "grid" and result.grid_config:
                gc = result.grid_config
                lo, hi, lvl = gc['low'], gc['high'], gc['levels']
                console.print(f"[dim]range: ${lo:.2f}-${hi:.2f}, {lvl} levels[/dim]")
            elif stype == "pullback_trailing":
                console.print(f"[dim]pullback: {result.pullback_pct}%, trailing stop: {result.trailing_stop_pct}%[/dim]")
                console.print("[dim]Entry: market when price pulls back from reference high[/dim]")

            console.print()
            console.print("Start the engine to activate: [cyan]trader start[/cyan]")
    except AppError as e:
        _handle_error(e, as_json)


@strategy.command("show")
@click.argument("strategy_id")
@click.pass_context
def strategy_show(ctx: click.Context, strategy_id: str) -> None:
    """Show details of a specific strategy."""
    from kodiak.app.strategies import get_strategy_detail

    as_json = _get_json_flag(ctx)

    try:
        strat = get_strategy_detail(strategy_id)
        if as_json:
            _json_output(strat)
        else:
            stype_label = strat.strategy_type.replace('_', '-').upper()
            console.print(f"\n[bold]{stype_label}[/bold] Strategy")
            console.print(f"ID: {strat.id}")
            console.print(f"Symbol: [cyan]{strat.symbol}[/cyan]")
            console.print(f"Quantity: {strat.quantity}")
            console.print(f"Phase: {strat.phase}")
            console.print(f"Enabled: {'Yes' if strat.enabled else 'No'}")
            console.print()

            console.print("[bold]Entry Configuration[/bold]")
            console.print(f"  Type: {strat.entry_type}")
            if strat.entry_price:
                console.print(f"  Price: ${strat.entry_price:.2f}")
            if strat.entry_order_id:
                console.print(f"  Order ID: {strat.entry_order_id}")
            if strat.entry_fill_price:
                console.print(f"  Fill Price: ${strat.entry_fill_price:.2f}")
            console.print()

            console.print("[bold]Exit Configuration[/bold]")
            if strat.strategy_type == "trailing_stop":
                console.print(f"  Trailing Stop: {strat.trailing_stop_pct}%")
                if strat.high_watermark:
                    console.print(f"  High Watermark: ${strat.high_watermark:.2f}")
                    stop_price = strat.high_watermark * (1 - strat.trailing_stop_pct / 100)
                    console.print(f"  Current Stop: ${stop_price:.2f}")
            elif strat.strategy_type == "pullback_trailing":
                console.print(f"  Pullback: {strat.pullback_pct}% (buy when price drops from reference)")
                console.print(f"  Trailing Stop: {strat.trailing_stop_pct}%")
                if strat.pullback_reference_price:
                    console.print(f"  Reference (high): ${strat.pullback_reference_price:.2f}")
                    threshold = strat.pullback_reference_price * (1 - strat.pullback_pct / 100)
                    console.print(f"  Buy Trigger: price <= ${threshold:.2f}")
                if strat.high_watermark:
                    console.print(f"  High Watermark: ${strat.high_watermark:.2f}")
            elif strat.strategy_type == "bracket":
                console.print(f"  Take Profit: +{strat.take_profit_pct}%")
                console.print(f"  Stop Loss: -{strat.stop_loss_pct}%")
                if strat.entry_fill_price:
                    tp_price = strat.entry_fill_price * (1 + strat.take_profit_pct / 100)
                    sl_price = strat.entry_fill_price * (1 - strat.stop_loss_pct / 100)
                    console.print(f"  TP Target: ${tp_price:.2f}")
                    console.print(f"  SL Target: ${sl_price:.2f}")
            elif strat.strategy_type == "scale_out" and strat.scale_targets:
                console.print("  Targets:")
                for t in strat.scale_targets:
                    console.print(f"    - {t['pct']}% at +{t['target_pct']}%")
            elif strat.strategy_type == "grid" and strat.grid_config:
                lo = strat.grid_config['low']
                hi = strat.grid_config['high']
                console.print(f"  Range: ${lo:.2f} - ${hi:.2f}")
                console.print(f"  Levels: {strat.grid_config['levels']}")
                console.print(f"  Qty/Level: {strat.grid_config['qty_per_level']}")

            if strat.exit_order_ids:
                console.print(f"  Exit Orders: {', '.join(strat.exit_order_ids)}")
            console.print()

            console.print("[bold]Metadata[/bold]")
            console.print(f"  Created: {strat.created_at}")
            console.print(f"  Updated: {strat.updated_at}")
            if strat.notes:
                console.print(f"  Notes: {strat.notes}")
    except AppError as e:
        _handle_error(e, as_json)


@strategy.command("remove")
@click.argument("strategy_id")
@click.pass_context
def strategy_remove(ctx: click.Context, strategy_id: str) -> None:
    """Remove a trading strategy."""
    from kodiak.app.strategies import remove_strategy

    as_json = _get_json_flag(ctx)

    try:
        result = remove_strategy(strategy_id)
        if as_json:
            _json_output(result)
        else:
            console.print(f"[green]Strategy {strategy_id} removed[/green]")
    except AppError as e:
        _handle_error(e, as_json)


@strategy.command("enable")
@click.argument("strategy_id")
@click.pass_context
def strategy_enable(ctx: click.Context, strategy_id: str) -> None:
    """Enable a trading strategy."""
    from kodiak.app.strategies import set_strategy_enabled

    as_json = _get_json_flag(ctx)

    try:
        result = set_strategy_enabled(strategy_id, enabled=True)
        if as_json:
            _json_output(result)
        else:
            console.print(f"[green]Strategy {strategy_id} enabled[/green]")
    except AppError as e:
        _handle_error(e, as_json)


@strategy.command("disable")
@click.argument("strategy_id")
@click.pass_context
def strategy_disable(ctx: click.Context, strategy_id: str) -> None:
    """Disable a trading strategy."""
    from kodiak.app.strategies import set_strategy_enabled

    as_json = _get_json_flag(ctx)

    try:
        result = set_strategy_enabled(strategy_id, enabled=False)
        if as_json:
            _json_output(result)
        else:
            console.print(f"[yellow]Strategy {strategy_id} disabled[/yellow]")
    except AppError as e:
        _handle_error(e, as_json)


@strategy.command("pause")
@click.argument("strategy_id")
@click.pass_context
def strategy_pause(ctx: click.Context, strategy_id: str) -> None:
    """Pause an active strategy."""
    from kodiak.app.strategies import pause_strategy

    as_json = _get_json_flag(ctx)

    try:
        result = pause_strategy(strategy_id)
        if as_json:
            _json_output(result)
        else:
            console.print(f"[yellow]Strategy {strategy_id} paused[/yellow]")
    except AppError as e:
        _handle_error(e, as_json)


@strategy.command("resume")
@click.argument("strategy_id")
@click.pass_context
def strategy_resume(ctx: click.Context, strategy_id: str) -> None:
    """Resume a paused strategy."""
    from kodiak.app.strategies import resume_strategy

    as_json = _get_json_flag(ctx)

    try:
        result = resume_strategy(strategy_id)
        if as_json:
            _json_output(result)
        else:
            console.print(f"[green]Strategy {strategy_id} resumed ({result['phase']})[/green]")
    except AppError as e:
        _handle_error(e, as_json)


@strategy.command("explain")
@click.argument("strategy_type", type=click.Choice([
    "trailing-stop", "bracket", "scale-out", "grid", "pullback-trailing",
]))
def strategy_explain(strategy_type: str) -> None:
    """Explain how a strategy type works."""
    help_text = STRATEGY_HELP.get(strategy_type, "No help available")
    console.print(help_text)


@strategy.group()
def schedule() -> None:
    """Schedule strategies to start at specific times."""
    pass


@schedule.command("add")
@click.argument("strategy_id")
@click.argument("schedule_at", type=str)
@click.pass_context
def schedule_add(ctx: click.Context, strategy_id: str, schedule_at: str) -> None:
    """Schedule a strategy to start at a specific time.

    SCHEDULE_AT format: ISO datetime string or relative time
    Examples:
        "2026-02-13T09:30:00"  (9:30 AM on Feb 13)
        "2026-02-13 09:30:00"   (alternative format)
        "tomorrow 09:30"        (9:30 AM tomorrow)
        "+2h"                   (2 hours from now)

    The strategy will be disabled until the schedule time arrives.
    Once the time arrives, the engine will automatically enable it.

    Examples:
        trader strategy schedule add abc123 "2026-02-13T09:30:00"
        trader strategy schedule add abc123 "tomorrow 09:30"
    """
    from kodiak.app.strategies import schedule_strategy

    as_json = _get_json_flag(ctx)

    try:
        # Parse schedule_at string
        schedule_dt = _parse_schedule_time(schedule_at)

        result = schedule_strategy(strategy_id, schedule_dt)

        if as_json:
            _json_output(result)
        else:
            console.print(f"[green]Strategy {strategy_id} scheduled[/green]")
            console.print(f"[dim]Will start at: {schedule_dt.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
            console.print("[dim]Strategy is now disabled until schedule time[/dim]")
    except AppError as e:
        _handle_error(e, as_json)
    except ValueError as e:
        if as_json:
            _json_output({"error": "INVALID_SCHEDULE", "message": str(e)})
        else:
            console.print(f"[red]Error parsing schedule time: {e}[/red]")
            console.print("[dim]Use ISO format: '2026-02-13T09:30:00' or '2026-02-13 09:30:00'[/dim]")


@schedule.command("list")
@click.pass_context
def schedule_list(ctx: click.Context) -> None:
    """List all scheduled strategies."""
    from kodiak.app.strategies import list_scheduled_strategies

    as_json = _get_json_flag(ctx)
    result = list_scheduled_strategies()

    if as_json:
        _json_output(result)
        return

    if not result["scheduled"]:
        console.print("[yellow]No scheduled strategies[/yellow]")
        return

    table = Table(title="Scheduled Strategies")
    table.add_column("ID", style="dim")
    table.add_column("Symbol", style="cyan")
    table.add_column("Type")
    table.add_column("Schedule Time")
    table.add_column("Status")

    for s in result["scheduled"]:
        from datetime import datetime
        schedule_dt = datetime.fromisoformat(s["schedule_at"])
        time_str = schedule_dt.strftime("%Y-%m-%d %H:%M:%S")
        status = "[green]Enabled[/green]" if s["enabled"] else "[yellow]Disabled[/yellow]"
        table.add_row(
            s["id"],
            s["symbol"],
            s["strategy_type"].replace("_", "-"),
            time_str,
            status,
        )

    console.print(table)


@schedule.command("cancel")
@click.argument("strategy_id")
@click.pass_context
def schedule_cancel(ctx: click.Context, strategy_id: str) -> None:
    """Cancel a scheduled strategy.

    This clears the schedule and leaves the strategy in its current state
    (enabled or disabled).
    """
    from kodiak.app.strategies import cancel_schedule

    as_json = _get_json_flag(ctx)

    try:
        result = cancel_schedule(strategy_id)
        if as_json:
            _json_output(result)
        else:
            if result.get("status") == "no_schedule":
                console.print(f"[yellow]{result.get('message', 'No schedule found')}[/yellow]")
            else:
                console.print(f"[green]Schedule canceled for strategy {strategy_id}[/green]")
    except AppError as e:
        _handle_error(e, as_json)


def _parse_schedule_time(schedule_str: str) -> datetime:
    """Parse schedule time string to datetime.

    Supports:
    - ISO format: "2026-02-13T09:30:00" or "2026-02-13 09:30:00"
    - Relative: "+2h" (2 hours), "+30m" (30 minutes), "+1d" (1 day)
    - Tomorrow: "tomorrow 09:30"
    """
    from datetime import datetime, timedelta

    schedule_str = schedule_str.strip().lower()

    # Relative time: +2h, +30m, +1d
    if schedule_str.startswith("+"):
        now = datetime.now()
        time_str = schedule_str[1:]

        if time_str.endswith("h"):
            hours = int(time_str[:-1])
            return now + timedelta(hours=hours)
        elif time_str.endswith("m"):
            minutes = int(time_str[:-1])
            return now + timedelta(minutes=minutes)
        elif time_str.endswith("d"):
            days = int(time_str[:-1])
            return now + timedelta(days=days)
        else:
            raise ValueError(f"Invalid relative time format: {schedule_str}")

    # Tomorrow format: "tomorrow 09:30"
    if schedule_str.startswith("tomorrow"):
        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        time_part = schedule_str.replace("tomorrow", "").strip()

        if time_part:
            try:
                hour, minute = map(int, time_part.split(":"))
                return tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
            except ValueError:
                raise ValueError(f"Invalid time format in 'tomorrow {time_part}'")
        else:
            return tomorrow.replace(hour=9, minute=30, second=0, microsecond=0)  # Default 9:30 AM

    # ISO format: try parsing as ISO datetime
    try:
        # Try with T separator first
        if "T" in schedule_str:
            return datetime.fromisoformat(schedule_str)
        # Try with space separator
        elif " " in schedule_str:
            return datetime.strptime(schedule_str, "%Y-%m-%d %H:%M:%S")
        else:
            # Try date only, default to 9:30 AM
            date_part = datetime.strptime(schedule_str, "%Y-%m-%d")
            return date_part.replace(hour=9, minute=30, second=0, microsecond=0)
    except ValueError:
        raise ValueError(f"Invalid datetime format: {schedule_str}. Use ISO format: '2026-02-13T09:30:00'")


# ============================================================================
# BACKTEST COMMANDS
# ============================================================================


@cli.group()
def backtest() -> None:
    """Run and analyze backtests.

    Backtesting allows you to test trading strategies against historical
    data before risking real capital. This helps validate strategy logic,
    optimize parameters, and build confidence.

    Available commands:
    - run: Run a backtest on historical data
    - list: List all saved backtests
    - show: Show detailed results for a backtest
    - compare: Compare multiple backtests side-by-side
    """
    pass


@cli.command()
@click.argument("source")
@click.option(
    "--data-source",
    type=click.Choice(["csv", "alpaca", "cached"]),
    default="csv",
    help="Data source for charting",
)
@click.option(
    "--data-dir",
    type=click.Path(exists=True),
    help="Backtests directory (containing backtests/)",
)
@click.option(
    "--historical-dir",
    type=click.Path(exists=True),
    help="Historical data directory for charting",
)
@click.option("--output", type=click.Path(dir_okay=False), help="Save chart to HTML file")
@click.option("--show", is_flag=True, help="Open chart in browser")
@click.option(
    "--theme",
    type=click.Choice(["dark", "light"]),
    default="dark",
    show_default=True,
    help="Chart theme",
)
@click.pass_context
def visualize(
    ctx: click.Context,
    source: str,
    data_source: str,
    data_dir: str | None,
    historical_dir: str | None,
    output: str | None,
    show: bool,
    theme: str,
) -> None:
    """Visualize a backtest result from ID or JSON file."""
    if not output and not show:
        console.print("[red]Provide --output or --show to render a chart[/red]")
        return

    from kodiak.backtest import load_backtest
    from kodiak.backtest.results import BacktestResult

    result = None
    source_path = Path(source)
    if source_path.exists():
        try:
            with open(source_path) as f:
                data = json_lib.load(f)
            result = BacktestResult.from_dict(data)
        except Exception as exc:
            console.print(f"[red]Error loading backtest file: {exc}[/red]")
            return
    else:
        data_dir_path = Path(data_dir) if data_dir else None
        try:
            result = load_backtest(source, data_dir=data_dir_path)
        except FileNotFoundError:
            console.print(f"[red]Backtest {source} not found[/red]")
            return
        except Exception as exc:
            console.print(f"[red]Error loading backtest: {exc}[/red]")
            return

    _render_backtest_chart(
        result=result,
        data_source=data_source,
        historical_dir=historical_dir,
        chart_path=output,
        show=show,
        theme=theme,
    )


@cli.command()
@click.argument("strategy_type", type=click.Choice(["trailing-stop", "bracket"]))
@click.option("--symbol", required=True, help="Trading symbol")
@click.option("--start", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end", required=True, help="End date (YYYY-MM-DD)")
@click.option(
    "--params",
    multiple=True,
    required=True,
    help="Parameter grid (e.g. trailing_stop_pct:1,2,3)",
)
@click.option(
    "--objective",
    type=click.Choice(
        [
            "total_return_pct",
            "total_return",
            "win_rate",
            "profit_factor",
            "max_drawdown_pct",
        ]
    ),
    default="total_return_pct",
    show_default=True,
    help="Optimization objective",
)
@click.option(
    "--method",
    type=click.Choice(["grid", "random"]),
    default="grid",
    show_default=True,
    help="Search method",
)
@click.option("--num-samples", type=int, help="Number of samples for random search")
@click.option(
    "--data-source",
    type=click.Choice(["csv", "alpaca", "cached"]),
    default="csv",
    help="Historical data source",
)
@click.option("--data-dir", type=click.Path(exists=True), help="Historical data directory")
@click.option(
    "--results-dir",
    type=click.Path(exists=True),
    help="Directory to save optimization results",
)
@click.option("--initial-capital", type=float, default=100000.0, help="Starting capital")
@click.option("--save/--no-save", default=True, help="Save optimization results")
@click.option("--show-results", is_flag=True, help="Display results summary")
@click.pass_context
def optimize(
    ctx: click.Context,
    strategy_type: str,
    symbol: str,
    start: str,
    end: str,
    params: tuple[str, ...],
    objective: str,
    method: str,
    num_samples: int | None,
    data_source: str,
    data_dir: str | None,
    results_dir: str | None,
    initial_capital: float,
    save: bool,
    show_results: bool,
) -> None:
    """Optimize strategy parameters using backtests."""
    from kodiak.optimization import Optimizer, save_optimization

    logger = ctx.obj["logger"]
    as_json = _get_json_flag(ctx)

    try:
        start_date = datetime.strptime(start, "%Y-%m-%d")
        end_date = datetime.strptime(end, "%Y-%m-%d")
        param_grid = _parse_param_grid(params)
        _validate_optimization_params(strategy_type, param_grid)

        optimizer = Optimizer(
            strategy_type=strategy_type,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            objective=objective,
            data_source=data_source,
            data_dir=data_dir,
            initial_capital=initial_capital,
        )

        result = optimizer.optimize(
            param_grid=param_grid,
            method=method,
            num_samples=num_samples,
        )

        if save:
            save_optimization(
                result,
                data_dir=Path(results_dir) if results_dir else None,
            )
            if not as_json:
                console.print(f"[green]Optimization saved with ID: {result.id}[/green]")

        if as_json:
            from kodiak.schemas.optimization import OptimizeResponse
            _json_output(OptimizeResponse.from_domain(result))
        elif show_results:
            _display_optimization_result(result)

    except Exception as exc:
        logger.error(f"Optimization failed: {exc}", exc_info=True)
        if as_json:
            err = {"error": "OPTIMIZATION_FAILED", "message": str(exc)}
            console.print(json_lib.dumps(err, indent=2))
        else:
            console.print(f"[red]Error running optimization: {exc}[/red]")


@backtest.command("run")
@click.argument("strategy_type", type=click.Choice(["trailing-stop", "bracket"]))
@click.argument("symbol", nargs=-1, required=True)
@click.option("--start", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end", required=True, help="End date (YYYY-MM-DD)")
@click.option("--qty", type=int, default=10, help="Quantity to trade per symbol")
@click.option("--trailing-pct", type=float, help="Trailing stop percentage (for trailing-stop)")
@click.option("--take-profit", type=float, help="Take profit percentage (for bracket)")
@click.option("--stop-loss", type=float, help="Stop loss percentage (for bracket)")
@click.option(
    "--data-source",
    type=click.Choice(["csv", "alpaca", "cached"]),
    default="csv",
    help="Data source",
)
@click.option(
    "--data-dir", type=click.Path(exists=True),
    help="Directory containing CSV data files",
)
@click.option("--initial-capital", type=float, default=100000.0, help="Total starting capital (split equally across symbols)")
@click.option("--save/--no-save", default=True, help="Save backtest results")
@click.option("--chart", type=click.Path(dir_okay=False), help="Save chart to HTML file (single-symbol only)")
@click.option("--show", is_flag=True, help="Open chart in browser (single-symbol only)")
@click.option(
    "--theme",
    type=click.Choice(["dark", "light"]),
    default="dark",
    show_default=True,
    help="Chart theme",
)
@click.pass_context
def backtest_run(
    ctx: click.Context,
    strategy_type: str,
    symbol: tuple[str, ...],
    start: str,
    end: str,
    qty: int,
    trailing_pct: float | None,
    take_profit: float | None,
    stop_loss: float | None,
    data_source: str,
    data_dir: str | None,
    initial_capital: float,
    save: bool,
    chart: str | None,
    show: bool,
    theme: str,
) -> None:
    """Run a backtest for a strategy.

    Pass one or more SYMBOL arguments to run a portfolio backtest:

        kodiak backtest run trailing-stop AAPL --start 2024-01-01 --end 2024-12-31 --trailing-pct 5

        kodiak backtest run bracket AAPL MSFT GOOGL --start 2024-01-01 --end 2024-12-31 --take-profit 0.05 --stop-loss 0.02
    """
    from kodiak.app.backtests import run_backtest
    from kodiak.schemas.backtests import BacktestRequest, PortfolioBacktestResponse

    logger = ctx.obj["logger"]
    as_json = _get_json_flag(ctx)
    symbols = list(symbol)
    is_portfolio = len(symbols) > 1

    try:
        request = BacktestRequest(
            strategy_type=strategy_type,
            symbols=symbols if is_portfolio else None,
            symbol=symbols[0] if not is_portfolio else None,
            start=start,
            end=end,
            qty=qty,
            trailing_pct=trailing_pct,
            take_profit=take_profit,
            stop_loss=stop_loss,
            data_source=data_source,
            data_dir=data_dir,
            initial_capital=initial_capital,
            save=save,
        )

        if not as_json:
            sym_display = ", ".join(symbols)
            console.print(f"[cyan]Loading historical data for {sym_display}...[/cyan]")
            console.print("[cyan]Running backtest...[/cyan]")

        result = run_backtest(ctx.obj["config"], request)

        if as_json:
            _json_output(result)
        elif isinstance(result, PortfolioBacktestResponse):
            _display_portfolio_backtest_result(result)
        else:
            if save:
                console.print(f"[green]Backtest saved with ID: {result.id}[/green]")
            _display_backtest_result_from_schema(result)

            # Load domain result for charting (single-symbol only)
            if chart or show:
                from kodiak.backtest import load_backtest as _load_bt
                try:
                    domain_result = _load_bt(result.id)
                    data_dir_path = (
                        Path(data_dir) if data_dir
                        else Path.cwd() / "data" / "historical"
                    )
                    _render_backtest_chart(
                        result=domain_result,
                        data_source=data_source,
                        historical_dir=str(data_dir_path),
                        chart_path=chart,
                        show=show,
                        theme=theme,
                    )
                except Exception:
                    pass

    except AppError as e:
        _handle_error(e, as_json)
    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        if as_json:
            console.print(json_lib.dumps({"error": "BACKTEST_FAILED", "message": str(e)}, indent=2))
        else:
            console.print(f"[red]Error running backtest: {e}[/red]")


@backtest.command("list")
@click.option("--data-dir", type=click.Path(exists=True), help="Data directory")
@click.pass_context
def backtest_list(ctx: click.Context, data_dir: str | None) -> None:
    """List all saved backtests."""
    from kodiak.app.backtests import list_backtests_app

    as_json = _get_json_flag(ctx)

    try:
        backtests = list_backtests_app(data_dir=data_dir)

        if as_json:
            _json_output([bt.model_dump() for bt in backtests])
            return

        if not backtests:
            console.print("[yellow]No backtests found[/yellow]")
            return

        table = Table(title="Backtest Results")
        table.add_column("ID", style="cyan")
        table.add_column("Symbol", style="white")
        table.add_column("Strategy", style="blue")
        table.add_column("Date Range", style="white")
        table.add_column("Return %", style="green")
        table.add_column("Win Rate", style="yellow")
        table.add_column("Trades", style="white")
        table.add_column("Max DD %", style="red")

        for bt in backtests:
            return_color = "green" if bt.total_return_pct > 0 else "red"
            return_str = f"[{return_color}]{bt.total_return_pct:+.2f}%[/{return_color}]"
            date_range = f"{bt.start_date[:10]} to {bt.end_date[:10]}"

            table.add_row(
                bt.id,
                bt.symbol,
                bt.strategy_type,
                date_range,
                return_str,
                f"{bt.win_rate:.1f}%",
                str(bt.total_trades),
                f"{bt.max_drawdown_pct:.2f}%",
            )

        console.print(table)

    except Exception as e:
        if as_json:
            console.print(json_lib.dumps({"error": "UNEXPECTED", "message": str(e)}, indent=2))
        else:
            console.print(f"[red]Error listing backtests: {e}[/red]")


@backtest.command("show")
@click.argument("backtest_id")
@click.option("--data-dir", type=click.Path(exists=True), help="Data directory")
@click.option(
    "--historical-dir",
    type=click.Path(exists=True),
    help="Historical data directory for charting",
)
@click.option(
    "--data-source",
    type=click.Choice(["csv", "alpaca", "cached"]),
    default="csv",
    help="Data source for charting",
)
@click.option("--chart", type=click.Path(dir_okay=False), help="Save chart to HTML file")
@click.option("--show", is_flag=True, help="Open chart in browser")
@click.option(
    "--theme",
    type=click.Choice(["dark", "light"]),
    default="dark",
    show_default=True,
    help="Chart theme",
)
@click.pass_context
def backtest_show(
    ctx: click.Context,
    backtest_id: str,
    data_dir: str | None,
    historical_dir: str | None,
    data_source: str,
    chart: str | None,
    show: bool,
    theme: str,
) -> None:
    """Show detailed results for a backtest."""
    from kodiak.app.backtests import show_backtest
    from kodiak.backtest import load_backtest

    as_json = _get_json_flag(ctx)

    try:
        result = show_backtest(backtest_id, data_dir=data_dir)
        if as_json:
            _json_output(result)
        else:
            _display_backtest_result_from_schema(result, detailed=True)

            if chart or show:
                data_dir_path = Path(data_dir) if data_dir else None
                try:
                    domain_result = load_backtest(backtest_id, data_dir=data_dir_path)
                    _render_backtest_chart(
                        result=domain_result,
                        data_source=data_source,
                        historical_dir=historical_dir,
                        chart_path=chart,
                        show=show,
                        theme=theme,
                    )
                except Exception:
                    pass

    except AppError as e:
        _handle_error(e, as_json)
    except Exception as e:
        if as_json:
            console.print(json_lib.dumps({"error": "UNEXPECTED", "message": str(e)}, indent=2))
        else:
            console.print(f"[red]Error loading backtest: {e}[/red]")


@backtest.command("compare")
@click.argument("backtest_ids", nargs=-1, required=True)
@click.option("--data-dir", type=click.Path(exists=True), help="Data directory")
@click.pass_context
def backtest_compare(
    ctx: click.Context, backtest_ids: tuple[str, ...],
    data_dir: str | None,
) -> None:
    """Compare multiple backtests side-by-side."""
    from kodiak.app.backtests import compare_backtests

    as_json = _get_json_flag(ctx)

    try:
        results = compare_backtests(list(backtest_ids), data_dir=data_dir)

        if as_json:
            _json_output([r.model_dump() for r in results])
            return

        if not results:
            console.print("[red]No backtests found to compare[/red]")
            return

        table = Table(title="Backtest Comparison")
        table.add_column("Metric", style="cyan")
        for result in results:
            table.add_column(f"{result.id[:6]}...", style="white")

        metrics = [
            ("Symbol", lambda r: r.symbol),
            ("Strategy", lambda r: r.strategy_type),
            ("Date Range", lambda r: f"{r.start_date.date()} to {r.end_date.date()}"),
            ("Initial Capital", lambda r: f"${r.initial_capital:,.2f}"),
            ("Final Equity", lambda r: f"${r.initial_capital + r.total_return:,.2f}"),
            ("Total Return", lambda r: f"${r.total_return:+,.2f}"),
            ("Return %", lambda r: f"{r.total_return_pct:+.2f}%"),
            ("Total Trades", lambda r: str(r.total_trades)),
            ("Win Rate", lambda r: f"{r.win_rate:.1f}%"),
            ("Profit Factor", lambda r: f"{r.profit_factor:.2f}"),
            ("Max Drawdown", lambda r: f"${r.max_drawdown:,.2f}"),
            ("Max Drawdown %", lambda r: f"{r.max_drawdown_pct:.2f}%"),
            ("Avg Win", lambda r: f"${r.avg_win:,.2f}"),
            ("Avg Loss", lambda r: f"${r.avg_loss:,.2f}"),
        ]

        for metric_name, metric_fn in metrics:
            row = [metric_name]
            for result in results:
                row.append(metric_fn(result))
            table.add_row(*row)

        console.print(table)

    except Exception as e:
        if as_json:
            console.print(json_lib.dumps({"error": "UNEXPECTED", "message": str(e)}, indent=2))
        else:
            console.print(f"[red]Error comparing backtests: {e}[/red]")


# =============================================================================
# Display Helpers
# =============================================================================


def _display_portfolio_backtest_result(result) -> None:
    """Display portfolio backtest result from a PortfolioBacktestResponse schema."""
    ret_color = "green" if result.portfolio_return_pct >= 0 else "red"

    summary = Table(title=f"Portfolio Backtest — {', '.join(result.symbols)}")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", style="white")
    summary.add_row("Strategy", result.strategy_type)
    summary.add_row("Symbols", ", ".join(result.symbols))
    summary.add_row("Date Range", f"{result.start_date.date()} to {result.end_date.date()}")
    summary.add_row("Initial Capital", f"${result.initial_capital:,.2f}")
    summary.add_row(
        "Portfolio Return %",
        f"[{ret_color}]{result.portfolio_return_pct:+.2f}%[/{ret_color}]",
    )
    summary.add_row("Portfolio Win Rate", f"{result.portfolio_win_rate:.1f}%")
    summary.add_row("Max Drawdown %", f"[red]{result.portfolio_max_drawdown_pct:.2f}%[/red]")
    summary.add_row("Total Fees Paid", f"${result.portfolio_total_fees_paid:,.2f}")
    summary.add_row("Total Trades", str(result.total_trades))
    console.print(summary)

    attr = Table(title="Per-Symbol Attribution")
    attr.add_column("Symbol", style="cyan")
    attr.add_column("Allocation", style="white")
    attr.add_column("Return %", style="white")
    attr.add_column("Win Rate", style="white")
    attr.add_column("Trades", style="white")
    attr.add_column("Max DD %", style="red")
    attr.add_column("Fees Paid", style="white")
    for s in result.symbol_attribution:
        s_ret_color = "green" if s.total_return_pct >= 0 else "red"
        attr.add_row(
            s.symbol,
            f"${s.allocation:,.2f}",
            f"[{s_ret_color}]{s.total_return_pct:+.2f}%[/{s_ret_color}]",
            f"{s.win_rate:.1f}%",
            str(s.total_trades),
            f"{s.max_drawdown_pct:.2f}%",
            f"${s.total_fees_paid:,.2f}",
        )
    console.print(attr)


def _display_backtest_result_from_schema(result, detailed: bool = False) -> None:
    """Display backtest result from a BacktestResponse schema."""
    table = Table(title=f"Backtest Results - {result.id}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Symbol", result.symbol)
    table.add_row("Strategy", result.strategy_type)
    table.add_row("Date Range", f"{result.start_date.date()} to {result.end_date.date()}")

    return_color = "green" if result.total_return > 0 else "red"
    table.add_row("Initial Capital", f"${result.initial_capital:,.2f}")
    table.add_row("Final Equity", f"${result.initial_capital + result.total_return:,.2f}")
    table.add_row("Total Return", f"[{return_color}]${result.total_return:+,.2f}[/{return_color}]")
    table.add_row("Return %", f"[{return_color}]{result.total_return_pct:+.2f}%[/{return_color}]")

    table.add_row("Total Trades", str(result.total_trades))
    table.add_row("Winning Trades", f"{result.winning_trades} ({result.win_rate:.1f}%)")
    table.add_row("Losing Trades", str(result.losing_trades))
    table.add_row("Profit Factor", f"{result.profit_factor:.2f}")

    dd = f"${result.max_drawdown:,.2f} ({result.max_drawdown_pct:.2f}%)"
    table.add_row("Max Drawdown", f"[red]{dd}[/red]")
    table.add_row("Avg Win", f"[green]${result.avg_win:,.2f}[/green]")
    table.add_row("Avg Loss", f"[red]${result.avg_loss:,.2f}[/red]")
    table.add_row("Largest Win", f"[green]${result.largest_win:,.2f}[/green]")
    table.add_row("Largest Loss", f"[red]${result.largest_loss:,.2f}[/red]")

    console.print(table)

    if detailed and result.trades:
        console.print("\n[cyan]Trade History:[/cyan]")
        trades_table = Table()
        trades_table.add_column("Timestamp", style="white")
        trades_table.add_column("Side", style="yellow")
        trades_table.add_column("Qty", style="white")
        trades_table.add_column("Price", style="cyan")
        trades_table.add_column("Total", style="green")

        for trade in result.trades:
            side_color = "green" if trade["side"] == "buy" else "red"
            trades_table.add_row(
                trade["timestamp"],
                f"[{side_color}]{trade['side'].upper()}[/{side_color}]",
                trade["qty"],
                f"${Decimal(trade['price']):,.2f}",
                f"${Decimal(trade['total']):,.2f}",
            )

        console.print(trades_table)


def _render_backtest_chart(
    result,
    data_source: str,
    historical_dir: str | None,
    chart_path: str | None,
    show: bool,
    theme: str,
) -> None:
    if not chart_path and not show:
        return

    from kodiak.visualization import build_backtest_chart, default_historical_data_dir

    resolved_dir = Path(historical_dir) if historical_dir else default_historical_data_dir()
    chart_builder = build_backtest_chart(
        result=result,
        data_source=data_source,
        data_dir=resolved_dir,
        theme=theme,
        include_price=True,
    )

    if chart_path:
        chart_builder.save_html(chart_path)
        console.print(f"[green]Chart saved to {chart_path}[/green]")

    if show:
        chart_builder.show()


def _parse_param_grid(param_entries: tuple[str, ...]) -> dict[str, list]:
    alias_map = {
        "trail_percent": "trailing_stop_pct",
        "trailing_pct": "trailing_stop_pct",
        "trailing_stop_pct": "trailing_stop_pct",
        "take_profit": "take_profit_pct",
        "take_profit_pct": "take_profit_pct",
        "stop_loss": "stop_loss_pct",
        "stop_loss_pct": "stop_loss_pct",
        "qty": "quantity",
        "quantity": "quantity",
    }
    grid: dict[str, list] = {}

    for entry in param_entries:
        if ":" not in entry:
            raise ValueError(f"Invalid param format: {entry}")
        key, raw_values = entry.split(":", 1)
        key = key.strip()
        if key not in alias_map:
            raise ValueError(f"Unknown parameter: {key}")
        canonical = alias_map[key]
        values = [v.strip() for v in raw_values.split(",") if v.strip()]
        if not values:
            raise ValueError(f"No values provided for {key}")

        parsed_values = []
        for value in values:
            if canonical == "quantity":
                parsed_values.append(int(value))
            else:
                parsed_values.append(Decimal(value))

        grid[canonical] = parsed_values

    return grid


def _validate_optimization_params(strategy_type: str, param_grid: dict[str, list]) -> None:
    if strategy_type == "trailing-stop":
        if "trailing_stop_pct" not in param_grid:
            raise ValueError("trailing_stop_pct is required for trailing-stop optimization")
    elif strategy_type == "bracket":
        if "take_profit_pct" not in param_grid or "stop_loss_pct" not in param_grid:
            raise ValueError(
                "take_profit_pct and stop_loss_pct are required"
                " for bracket optimization"
            )


def _display_optimization_result(result) -> None:
    table = Table(title=f"Optimization Results - {result.id}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Strategy", result.strategy_type)
    table.add_row("Symbol", result.symbol)
    table.add_row("Date Range", f"{result.start_date.date()} to {result.end_date.date()}")
    table.add_row("Objective", result.objective)
    table.add_row("Method", result.method)
    table.add_row("Combinations", str(result.num_combinations))
    table.add_row("Runtime (s)", f"{result.runtime_seconds:.2f}")
    table.add_row("Best Score", str(result.best_score))
    table.add_row("Best Params", str(result.best_params))

    console.print(table)


# =============================================================================
# Primitives Commands
# =============================================================================


@cli.group()
def primitives() -> None:
    """Inspect registered financial action primitives."""
    pass


@primitives.command("list")
@click.option("--show-deprecated", is_flag=True, help="Include deprecated primitives")
@click.pass_context
def primitives_list(ctx: click.Context, show_deprecated: bool) -> None:
    """List all registered financial action primitives (latest version of each)."""
    from kodiak.primitives import list_all

    as_json = _get_json_flag(ctx)
    all_primitives = list_all()
    if not show_deprecated:
        all_primitives = [p for p in all_primitives if not p.deprecated]

    if as_json:
        _json_output([p.to_dict() for p in all_primitives])
        return

    table = Table(title="Financial Action Primitives", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Risk", style="yellow")
    table.add_column("Latency")
    table.add_column("Mode")
    table.add_column("Tags")
    table.add_column("Deprecated")
    for p in all_primitives:
        table.add_row(
            p.name,
            p.version,
            p.risk_level.value,
            p.latency_class.value if p.latency_class else "—",
            p.execution_mode.value,
            ", ".join(p.tags),
            "yes" if p.deprecated else "",
        )
    console.print(table)


@primitives.command("versions")
@click.argument("name")
@click.pass_context
def primitives_versions(ctx: click.Context, name: str) -> None:
    """List all registered versions of a primitive."""
    from kodiak.primitives import list_versions

    versions = list_versions(name)
    if not versions:
        console.print(f"[red]Primitive '{name}' not found.[/red]")
        raise SystemExit(1)

    as_json = _get_json_flag(ctx)
    if as_json:
        _json_output([p.to_dict() for p in versions])
        return

    table = Table(title=f"Versions: {name}", show_lines=True)
    table.add_column("Version", style="cyan")
    table.add_column("Deprecated")
    table.add_column("Note")
    for p in versions:
        table.add_row(
            p.version,
            "yes" if p.deprecated else "",
            p.deprecation_message or "",
        )
    console.print(table)


@primitives.command("describe")
@click.argument("name")
@click.option("--version", "ver", default="latest", show_default=True, help="Version or 'latest'")
@click.pass_context
def primitives_describe(ctx: click.Context, name: str, ver: str) -> None:
    """Show full descriptor for a primitive including input/output schemas."""
    import json as json_lib

    from kodiak.primitives import get

    primitive = get(name, version=ver)
    if primitive is None:
        console.print(f"[red]Primitive '{name}' version '{ver}' not found.[/red]")
        raise SystemExit(1)

    as_json = _get_json_flag(ctx)
    if as_json:
        _json_output(primitive.to_dict())
        return

    table = Table(title=f"Primitive: {primitive.name} v{primitive.version}", show_lines=True)
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Name", primitive.name)
    table.add_row("Version", primitive.version)
    table.add_row("Description", primitive.description)
    table.add_row("Risk Level", primitive.risk_level.value)
    table.add_row("Latency Class", primitive.latency_class.value if primitive.latency_class else "—")
    table.add_row("Execution Mode", primitive.execution_mode.value)
    table.add_row("Permissions", ", ".join(primitive.permissions))
    table.add_row("Tags", ", ".join(primitive.tags))
    if primitive.deprecated:
        note = primitive.deprecation_message or "Use a newer version."
        table.add_row("Deprecated", f"[yellow]yes — {note}[/yellow]")
    table.add_row("Input Schema", json_lib.dumps(primitive.input_schema, indent=2))
    table.add_row("Output Schema", json_lib.dumps(primitive.output_schema, indent=2))
    console.print(table)


# =============================================================================
# Workflow DSL Commands
# =============================================================================


@cli.group()
def workflow() -> None:
    """Validate and run declarative YAML/JSON workflow specs."""
    pass


@workflow.command("validate")
@click.argument("spec_file", type=click.Path(exists=True))
@click.pass_context
def workflow_validate(ctx: click.Context, spec_file: str) -> None:
    """Validate a workflow spec file without executing it."""
    from kodiak.orchestration import WorkflowSpec, WorkflowSpecError

    as_json = _get_json_flag(ctx)

    try:
        spec = WorkflowSpec.from_file(spec_file)
    except WorkflowSpecError as exc:
        if as_json:
            _json_output({"valid": False, "errors": [str(exc)]})
        else:
            console.print(f"[red]Parse error:[/red] {exc}")
        raise SystemExit(1)

    errors = spec.validate()
    if as_json:
        _json_output({"valid": len(errors) == 0, "errors": errors})
        return

    if errors:
        console.print(f"[red]Validation failed ({len(errors)} error(s)):[/red]")
        for err in errors:
            console.print(f"  [red]•[/red] {err}")
        raise SystemExit(1)

    try:
        plan = spec.compile()
        console.print(
            f"[green]✓[/green] Valid — '{plan.name}' "
            f"({len(plan.steps)} step(s), deterministic={plan.deterministic})"
        )
    except WorkflowSpecError as exc:
        console.print(f"[red]Compile error:[/red] {exc}")
        raise SystemExit(1)


@workflow.command("run-file")
@click.argument("spec_file", type=click.Path(exists=True))
@click.pass_context
def workflow_run_file(ctx: click.Context, spec_file: str) -> None:
    """Parse, validate, and execute a workflow spec file."""
    from kodiak.orchestration import WorkflowExecutor, WorkflowSpec, WorkflowSpecError

    as_json = _get_json_flag(ctx)

    try:
        spec = WorkflowSpec.from_file(spec_file)
    except WorkflowSpecError as exc:
        if as_json:
            _json_output({"valid": False, "errors": [str(exc)], "result": None})
        else:
            console.print(f"[red]Parse error:[/red] {exc}")
        raise SystemExit(1)

    errors = spec.validate()
    if errors:
        if as_json:
            _json_output({"valid": False, "errors": errors, "result": None})
        else:
            console.print(f"[red]Validation failed ({len(errors)} error(s)):[/red]")
            for err in errors:
                console.print(f"  [red]•[/red] {err}")
        raise SystemExit(1)

    plan = spec.compile()
    if not as_json:
        console.print(f"[cyan]Running workflow:[/cyan] {plan.name} ({len(plan.steps)} steps)")

    result = WorkflowExecutor().execute(plan)

    if as_json:
        _json_output({"valid": True, "errors": [], "result": result.to_dict()})
        return

    status = "[green]✓ success[/green]" if result.success else "[red]✗ failed[/red]"
    console.print(f"Result: {status} — {result.steps_completed}/{result.steps_total} steps completed")

    table = Table(title="Step Results", show_lines=True)
    table.add_column("#", style="dim")
    table.add_column("Primitive", style="cyan")
    table.add_column("Version")
    table.add_column("Status")
    table.add_column("Attempts")
    table.add_column("ms")
    table.add_column("Error")
    for sr in result.step_results:
        ok = "[green]ok[/green]" if sr.success else "[red]fail[/red]"
        table.add_row(
            str(sr.step_index),
            sr.primitive,
            sr.version_resolved,
            ok,
            str(sr.attempts),
            f"{sr.duration_ms:.1f}",
            sr.error or "",
        )
    console.print(table)

    if not result.success:
        raise SystemExit(1)


# =============================================================================
# MCP Server Commands
# =============================================================================


@cli.command("mcp")
@click.pass_context
def mcp_serve(ctx: click.Context) -> None:
    """Start the MCP server (stdio transport).

    Launches an MCP-compliant server over stdio, allowing AI agents
    (e.g. Claude Desktop) to interact with Kodiak via the MCP protocol.

    For HTTP transport, use kodiak-server instead.
    """
    import asyncio
    import sys

    from kodiak.utils.logging import setup_logging

    # Redirect logging to stderr so stdio protocol stream is not corrupted.
    setup_logging(
        log_dir=ctx.obj["config"].log_dir,
        log_to_file=True,
        console_stream=sys.stderr,
    )

    from kodiak.mcp.tools import build_server

    print("Starting Kodiak MCP server (stdio)...", file=sys.stderr, flush=True)
    server = build_server()
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    cli()
