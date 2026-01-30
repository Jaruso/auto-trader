"""CLI entry point for AutoTrader."""

import click
from rich.console import Console
from rich.table import Table

from decimal import Decimal

from datetime import datetime
from pathlib import Path

from trader import __version__
from trader.api.alpaca import AlpacaBroker
from trader.api.broker import Broker, OrderSide, OrderStatus, OrderType
from trader.core.backtest import Backtester
from trader.core.engine import TradingEngine
from trader.core.portfolio import Portfolio
from trader.core.safety import SafetyCheck, SafetyLimits
from trader.data.ledger import TradeLedger
from trader.rules.models import Rule, RuleAction, RuleCondition
from trader.rules.loader import load_rules, save_rule, delete_rule, enable_rule
from trader.utils.config import Config, Environment, load_config
from trader.utils.logging import get_logger, setup_logging

console = Console()


def get_broker(config: Config) -> Broker:
    """Create broker instance from config."""
    return AlpacaBroker(
        api_key=config.alpaca_api_key,
        secret_key=config.alpaca_secret_key,
        paper=config.is_paper,
    )


@click.group()
@click.version_option(version=__version__, prog_name="trader")
@click.option(
    "--env",
    type=click.Choice(["paper", "prod"]),
    default="paper",
    help="Trading environment",
)
@click.pass_context
def cli(ctx: click.Context, env: str) -> None:
    """AutoTrader - CLI-based automated trading system."""
    ctx.ensure_object(dict)
    config = load_config(env)
    ctx.obj["config"] = config

    # Set up logging
    logger = setup_logging(log_dir=config.log_dir, log_to_file=True)
    ctx.obj["logger"] = logger


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show current system status."""
    config = ctx.obj["config"]

    table = Table(title="AutoTrader Status")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    # Environment info
    env_style = "yellow" if config.env == Environment.PAPER else "red bold"
    table.add_row("Environment", f"[{env_style}]{config.env.value.upper()}[/{env_style}]")
    table.add_row("Broker", config.broker)
    table.add_row("Base URL", config.base_url)

    # API key status
    key_status = "Configured" if config.alpaca_api_key else "[red]Not Set[/red]"
    table.add_row("API Key", key_status)

    # Production safety
    if config.env == Environment.PROD:
        prod_status = "[red]ENABLED[/red]" if config.enable_prod else "[green]DISABLED[/green]"
        table.add_row("Production Trading", prod_status)

    console.print(table)


@cli.command()
@click.pass_context
def balance(ctx: click.Context) -> None:
    """Show account balance."""
    config = ctx.obj["config"]

    if not config.alpaca_api_key:
        console.print("[red]Error: Alpaca API key not configured[/red]")
        console.print("Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env.paper")
        return

    try:
        broker = get_broker(config)
        account = broker.get_account()
        market_open = broker.is_market_open()

        table = Table(title="Account Balance")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")

        table.add_row("Cash", f"${account.cash:,.2f}")
        table.add_row("Buying Power", f"${account.buying_power:,.2f}")
        table.add_row("Equity", f"${account.equity:,.2f}")
        table.add_row("Currency", account.currency)

        market_status = "[green]OPEN[/green]" if market_open else "[yellow]CLOSED[/yellow]"
        table.add_row("Market", market_status)

        console.print(table)
    except Exception as e:
        console.print(f"[red]Error fetching balance: {e}[/red]")


@cli.command()
@click.pass_context
def positions(ctx: click.Context) -> None:
    """Show current positions."""
    config = ctx.obj["config"]

    if not config.alpaca_api_key:
        console.print("[red]Error: Alpaca API key not configured[/red]")
        return

    try:
        broker = get_broker(config)
        positions_list = broker.get_positions()

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
    except Exception as e:
        console.print(f"[red]Error fetching positions: {e}[/red]")


@cli.command()
@click.argument("symbol")
@click.pass_context
def quote(ctx: click.Context, symbol: str) -> None:
    """Get current quote for a symbol."""
    config = ctx.obj["config"]

    if not config.alpaca_api_key:
        console.print("[red]Error: Alpaca API key not configured[/red]")
        return

    try:
        broker = get_broker(config)
        q = broker.get_quote(symbol.upper())

        table = Table(title=f"Quote: {symbol.upper()}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")

        table.add_row("Bid", f"${q.bid:,.2f}")
        table.add_row("Ask", f"${q.ask:,.2f}")
        table.add_row("Spread", f"${q.ask - q.bid:,.2f}")

        console.print(table)
    except Exception as e:
        console.print(f"[red]Error fetching quote: {e}[/red]")


@cli.command()
@click.argument("symbol")
@click.argument("qty", type=int)
@click.option("--limit", type=float, help="Limit price (default: market order)")
@click.pass_context
def buy(ctx: click.Context, symbol: str, qty: int, limit: float | None) -> None:
    """Buy shares of a stock."""
    config = ctx.obj["config"]
    logger = get_logger("autotrader.trades")

    if not config.alpaca_api_key:
        console.print("[red]Error: Alpaca API key not configured[/red]")
        return

    try:
        broker = get_broker(config)
        symbol = symbol.upper()

        # Determine order type
        if limit:
            order_type = OrderType.LIMIT
            limit_price = Decimal(str(limit))
            console.print(f"[yellow]Placing LIMIT BUY: {qty} {symbol} @ ${limit:.2f}[/yellow]")
        else:
            order_type = OrderType.MARKET
            limit_price = None
            console.print(f"[yellow]Placing MARKET BUY: {qty} {symbol}[/yellow]")

        order = broker.place_order(
            symbol=symbol,
            qty=Decimal(str(qty)),
            side=OrderSide.BUY,
            order_type=order_type,
            limit_price=limit_price,
        )

        logger.info(f"BUY {qty} {symbol} | Order ID: {order.id} | Status: {order.status.value}")

        table = Table(title="Order Placed")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Order ID", order.id)
        table.add_row("Symbol", order.symbol)
        table.add_row("Side", "BUY")
        table.add_row("Quantity", str(order.qty))
        table.add_row("Type", order.order_type.value.upper())
        if order.limit_price:
            table.add_row("Limit Price", f"${order.limit_price:,.2f}")
        table.add_row("Status", order.status.value.upper())

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error placing order: {e}[/red]")


@cli.command()
@click.argument("symbol")
@click.argument("qty", type=int)
@click.option("--limit", type=float, help="Limit price (default: market order)")
@click.pass_context
def sell(ctx: click.Context, symbol: str, qty: int, limit: float | None) -> None:
    """Sell shares of a stock."""
    config = ctx.obj["config"]
    logger = get_logger("autotrader.trades")

    if not config.alpaca_api_key:
        console.print("[red]Error: Alpaca API key not configured[/red]")
        return

    try:
        broker = get_broker(config)
        symbol = symbol.upper()

        # Determine order type
        if limit:
            order_type = OrderType.LIMIT
            limit_price = Decimal(str(limit))
            console.print(f"[yellow]Placing LIMIT SELL: {qty} {symbol} @ ${limit:.2f}[/yellow]")
        else:
            order_type = OrderType.MARKET
            limit_price = None
            console.print(f"[yellow]Placing MARKET SELL: {qty} {symbol}[/yellow]")

        order = broker.place_order(
            symbol=symbol,
            qty=Decimal(str(qty)),
            side=OrderSide.SELL,
            order_type=order_type,
            limit_price=limit_price,
        )

        logger.info(f"SELL {qty} {symbol} | Order ID: {order.id} | Status: {order.status.value}")

        table = Table(title="Order Placed")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Order ID", order.id)
        table.add_row("Symbol", order.symbol)
        table.add_row("Side", "SELL")
        table.add_row("Quantity", str(order.qty))
        table.add_row("Type", order.order_type.value.upper())
        if order.limit_price:
            table.add_row("Limit Price", f"${order.limit_price:,.2f}")
        table.add_row("Status", order.status.value.upper())

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error placing order: {e}[/red]")


@cli.command()
@click.pass_context
def orders(ctx: click.Context) -> None:
    """Show open orders."""
    config = ctx.obj["config"]

    if not config.alpaca_api_key:
        console.print("[red]Error: Alpaca API key not configured[/red]")
        return

    try:
        broker = get_broker(config)
        orders_list = broker.get_orders()

        if not orders_list:
            console.print("[yellow]No open orders[/yellow]")
            return

        table = Table(title="Open Orders")
        table.add_column("ID", style="dim")
        table.add_column("Symbol", style="cyan")
        table.add_column("Side")
        table.add_column("Type")
        table.add_column("Qty", justify="right")
        table.add_column("Limit", justify="right")
        table.add_column("Status")

        for order in orders_list:
            side_style = "green" if order.side == OrderSide.BUY else "red"
            table.add_row(
                order.id[:8] + "...",
                order.symbol,
                f"[{side_style}]{order.side.value.upper()}[/{side_style}]",
                order.order_type.value.upper(),
                str(order.qty),
                f"${order.limit_price:,.2f}" if order.limit_price else "-",
                order.status.value.upper(),
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error fetching orders: {e}[/red]")


@cli.command()
@click.argument("order_id")
@click.pass_context
def cancel(ctx: click.Context, order_id: str) -> None:
    """Cancel an open order."""
    config = ctx.obj["config"]

    if not config.alpaca_api_key:
        console.print("[red]Error: Alpaca API key not configured[/red]")
        return

    try:
        broker = get_broker(config)
        success = broker.cancel_order(order_id)

        if success:
            console.print(f"[green]Order {order_id} canceled[/green]")
        else:
            console.print(f"[red]Failed to cancel order {order_id}[/red]")

    except Exception as e:
        console.print(f"[red]Error canceling order: {e}[/red]")


@cli.group()
def rules() -> None:
    """Manage trading rules."""
    pass


@rules.command("list")
@click.pass_context
def rules_list(ctx: click.Context) -> None:
    """List all trading rules."""
    rules_data = load_rules()

    if not rules_data:
        console.print("[yellow]No rules configured[/yellow]")
        console.print("Add a rule with: trader rules add buy AAPL 170 --qty 10")
        return

    table = Table(title="Trading Rules")
    table.add_column("ID", style="dim")
    table.add_column("Symbol", style="cyan")
    table.add_column("Action")
    table.add_column("Condition")
    table.add_column("Target", justify="right")
    table.add_column("Qty", justify="right")
    table.add_column("Status")

    for rule in rules_data:
        action_style = "green" if rule.action == RuleAction.BUY else "red"
        cond = "≤" if rule.condition == RuleCondition.BELOW else "≥"

        if rule.triggered:
            status = "[dim]TRIGGERED[/dim]"
        elif rule.enabled:
            status = "[green]ACTIVE[/green]"
        else:
            status = "[yellow]DISABLED[/yellow]"

        table.add_row(
            rule.id,
            rule.symbol,
            f"[{action_style}]{rule.action.value.upper()}[/{action_style}]",
            f"price {cond}",
            f"${rule.target_price:,.2f}",
            str(rule.quantity),
            status,
        )

    console.print(table)


@rules.command("add")
@click.argument("action", type=click.Choice(["buy", "sell"]))
@click.argument("symbol")
@click.argument("price", type=float)
@click.option("--qty", type=int, default=1, help="Quantity to trade")
@click.option("--above", is_flag=True, help="Trigger when price goes ABOVE target (default: below)")
@click.pass_context
def rules_add(
    ctx: click.Context, action: str, symbol: str, price: float, qty: int, above: bool
) -> None:
    """Add a trading rule.

    Examples:

        Buy 10 AAPL when price drops to $170:
        trader rules add buy AAPL 170 --qty 10

        Sell 5 TSLA when price rises to $300:
        trader rules add sell TSLA 300 --qty 5 --above
    """
    rule_action = RuleAction.BUY if action == "buy" else RuleAction.SELL
    condition = RuleCondition.ABOVE if above else RuleCondition.BELOW

    rule = Rule(
        symbol=symbol.upper(),
        action=rule_action,
        condition=condition,
        target_price=Decimal(str(price)),
        quantity=qty,
    )

    save_rule(rule)

    cond = "≥" if above else "≤"
    console.print(f"[green]Rule added:[/green] {rule.action.value.upper()} {rule.quantity} {rule.symbol} when price {cond} ${rule.target_price}")
    console.print(f"[dim]Rule ID: {rule.id}[/dim]")


@rules.command("remove")
@click.argument("rule_id")
@click.pass_context
def rules_remove(ctx: click.Context, rule_id: str) -> None:
    """Remove a trading rule."""
    if delete_rule(rule_id):
        console.print(f"[green]Rule {rule_id} deleted[/green]")
    else:
        console.print(f"[red]Rule {rule_id} not found[/red]")


@rules.command("enable")
@click.argument("rule_id")
@click.pass_context
def rules_enable(ctx: click.Context, rule_id: str) -> None:
    """Enable a trading rule."""
    if enable_rule(rule_id, enabled=True):
        console.print(f"[green]Rule {rule_id} enabled[/green]")
    else:
        console.print(f"[red]Rule {rule_id} not found[/red]")


@rules.command("disable")
@click.argument("rule_id")
@click.pass_context
def rules_disable(ctx: click.Context, rule_id: str) -> None:
    """Disable a trading rule."""
    if enable_rule(rule_id, enabled=False):
        console.print(f"[yellow]Rule {rule_id} disabled[/yellow]")
    else:
        console.print(f"[red]Rule {rule_id} not found[/red]")


@cli.command()
@click.option("--confirm", is_flag=True, help="Confirm production start")
@click.option("--dry-run", is_flag=True, help="Evaluate rules but don't execute trades")
@click.option("--interval", type=int, default=60, help="Poll interval in seconds")
@click.option("--once", is_flag=True, help="Run once and exit")
@click.pass_context
def start(ctx: click.Context, confirm: bool, dry_run: bool, interval: int, once: bool) -> None:
    """Start the trading engine.

    The engine will continuously monitor prices and execute trades
    based on your configured rules.

    Examples:

        Run in paper mode:
        trader start

        Dry run (no actual trades):
        trader start --dry-run

        Run once and exit:
        trader start --once

        Custom poll interval:
        trader start --interval 30
    """
    config = ctx.obj["config"]

    if not config.alpaca_api_key:
        console.print("[red]Error: Alpaca API key not configured[/red]")
        return

    if config.env == Environment.PROD and not confirm:
        console.print("[red]Error: Production start requires --confirm flag[/red]")
        return

    if config.env == Environment.PROD and not config.enable_prod:
        console.print("[red]Error: Production trading is disabled[/red]")
        console.print("Set ENABLE_PROD=true in .env.prod to enable")
        return

    # Check for rules
    rules_data = load_rules()
    active_rules = [r for r in rules_data if r.enabled and not r.triggered]

    if not active_rules:
        console.print("[yellow]Warning: No active rules configured[/yellow]")
        console.print("Add rules with: trader rules add buy AAPL 170 --qty 10")
        if not once:
            return

    broker = get_broker(config)
    engine = TradingEngine(broker, poll_interval=interval, dry_run=dry_run)

    mode = "[yellow]DRY RUN[/yellow]" if dry_run else f"[green]{config.env.value.upper()}[/green]"
    console.print(f"Starting trading engine in {mode} mode...")
    console.print(f"Active rules: {len(active_rules)}")
    console.print(f"Poll interval: {interval}s")
    console.print("[dim]Press Ctrl+C to stop[/dim]")
    console.print()

    if once:
        order_ids = engine.run_once()
        if order_ids:
            console.print(f"[green]Executed {len(order_ids)} orders[/green]")
        else:
            console.print("[yellow]No rules triggered[/yellow]")
    else:
        engine.start()


@cli.command()
@click.pass_context
def watch(ctx: click.Context) -> None:
    """Watch prices for symbols in your rules."""
    config = ctx.obj["config"]

    if not config.alpaca_api_key:
        console.print("[red]Error: Alpaca API key not configured[/red]")
        return

    rules_data = load_rules()
    if not rules_data:
        console.print("[yellow]No rules configured[/yellow]")
        return

    broker = get_broker(config)

    # Get unique symbols
    symbols = list(set(r.symbol for r in rules_data))

    table = Table(title="Price Watch")
    table.add_column("Symbol", style="cyan")
    table.add_column("Bid", justify="right")
    table.add_column("Ask", justify="right")
    table.add_column("Rules")

    for symbol in symbols:
        try:
            q = broker.get_quote(symbol)
            mid = (q.bid + q.ask) / 2

            # Find rules for this symbol
            symbol_rules = [r for r in rules_data if r.symbol == symbol and r.enabled]
            rule_strs = []
            for r in symbol_rules:
                cond = "≤" if r.condition == RuleCondition.BELOW else "≥"
                triggered = "✓" if r.check(mid) else ""
                rule_strs.append(f"{r.action.value} {cond}${r.target_price}{triggered}")

            table.add_row(
                symbol,
                f"${q.bid:,.2f}",
                f"${q.ask:,.2f}",
                ", ".join(rule_strs) if rule_strs else "-",
            )
        except Exception as e:
            table.add_row(symbol, "[red]Error[/red]", str(e), "-")

    console.print(table)


@cli.command()
@click.pass_context
def portfolio(ctx: click.Context) -> None:
    """Show portfolio summary and performance."""
    config = ctx.obj["config"]

    if not config.alpaca_api_key:
        console.print("[red]Error: Alpaca API key not configured[/red]")
        return

    try:
        broker = get_broker(config)
        ledger = TradeLedger()
        pf = Portfolio(broker, ledger)

        summary = pf.get_summary()

        # Summary table
        table = Table(title="Portfolio Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")

        table.add_row("Total Equity", f"${summary.total_equity:,.2f}")
        table.add_row("Cash", f"${summary.cash:,.2f}")
        table.add_row("Positions Value", f"${summary.positions_value:,.2f}")
        table.add_row("Position Count", str(summary.position_count))

        # P/L styling
        unreal_style = "green" if summary.unrealized_pnl >= 0 else "red"
        real_style = "green" if summary.realized_pnl_today >= 0 else "red"
        total_style = "green" if summary.total_pnl_today >= 0 else "red"

        table.add_row(
            "Unrealized P/L",
            f"[{unreal_style}]${summary.unrealized_pnl:,.2f} ({summary.unrealized_pnl_pct:.2%})[/{unreal_style}]",
        )
        table.add_row(
            "Realized P/L (Today)",
            f"[{real_style}]${summary.realized_pnl_today:,.2f}[/{real_style}]",
        )
        table.add_row(
            "Total P/L (Today)",
            f"[{total_style}]${summary.total_pnl_today:,.2f}[/{total_style}]",
        )

        console.print(table)

        # Positions breakdown
        positions = pf.get_positions_detail()
        if positions:
            console.print()
            pos_table = Table(title="Position Breakdown")
            pos_table.add_column("Symbol", style="cyan")
            pos_table.add_column("Qty", justify="right")
            pos_table.add_column("Avg Cost", justify="right")
            pos_table.add_column("Current", justify="right")
            pos_table.add_column("Value", justify="right")
            pos_table.add_column("P/L", justify="right")
            pos_table.add_column("Weight", justify="right")

            for pos in positions:
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

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@cli.command()
@click.option("--symbol", help="Filter by symbol")
@click.option("--limit", type=int, default=20, help="Number of trades to show")
@click.pass_context
def history(ctx: click.Context, symbol: str | None, limit: int) -> None:
    """Show trade history."""
    ledger = TradeLedger()
    trades = ledger.get_trades(symbol=symbol, limit=limit)

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
        side_style = "green" if trade.is_buy else "red"
        time_str = trade.timestamp.strftime("%m/%d %H:%M")
        table.add_row(
            time_str,
            trade.symbol,
            f"[{side_style}]{trade.side.upper()}[/{side_style}]",
            str(trade.quantity),
            f"${trade.price:,.2f}",
            f"${trade.total:,.2f}",
            trade.status.upper(),
        )

    console.print(table)

    # Show today's P/L
    today_pnl = ledger.get_total_today_pnl()
    pnl_style = "green" if today_pnl >= 0 else "red"
    console.print(f"\nToday's Realized P/L: [{pnl_style}]${today_pnl:,.2f}[/{pnl_style}]")


@cli.command()
@click.argument("output", type=click.Path())
@click.option("--days", type=int, default=30, help="Export trades from last N days")
@click.pass_context
def export(ctx: click.Context, output: str, days: int) -> None:
    """Export trade history to CSV."""
    from datetime import timedelta

    ledger = TradeLedger()
    since = datetime.now() - timedelta(days=days)
    path = Path(output)

    count = ledger.export_csv(path, since=since)
    console.print(f"[green]Exported {count} trades to {path}[/green]")


@cli.command()
@click.pass_context
def safety(ctx: click.Context) -> None:
    """Show safety controls status."""
    config = ctx.obj["config"]

    if not config.alpaca_api_key:
        console.print("[red]Error: Alpaca API key not configured[/red]")
        return

    try:
        broker = get_broker(config)
        ledger = TradeLedger()
        checker = SafetyCheck(broker, ledger)

        status = checker.get_status()

        table = Table(title="Safety Controls")
        table.add_column("Control", style="cyan")
        table.add_column("Status", justify="right")
        table.add_column("Limit", justify="right")

        # Kill switch
        kill_status = "[red]ACTIVE[/red]" if status["kill_switch"] else "[green]OFF[/green]"
        table.add_row("Kill Switch", kill_status, "-")

        # Daily P/L
        pnl = status["daily_pnl"]
        pnl_style = "green" if pnl >= 0 else "red"
        remaining = status["daily_pnl_remaining"]
        table.add_row(
            "Daily P/L",
            f"[{pnl_style}]${pnl:,.2f}[/{pnl_style}]",
            f"${status['daily_pnl_limit']:,.2f}",
        )
        table.add_row("Loss Remaining", f"${remaining:,.2f}", "-")

        # Trade count
        trades = status["trade_count"]
        limit = status["trade_limit"]
        pct = trades / limit * 100 if limit > 0 else 0
        table.add_row("Trades Today", f"{trades} ({pct:.0f}%)", str(limit))
        table.add_row("Trades Remaining", str(status["trades_remaining"]), "-")

        # Can trade
        can_trade = status["can_trade"]
        trade_status = "[green]YES[/green]" if can_trade else "[red]NO[/red]"
        table.add_row("Can Trade", trade_status, "-")

        console.print(table)

        # Show limits
        console.print()
        limits = SafetyLimits()
        limit_table = Table(title="Position Limits")
        limit_table.add_column("Limit", style="cyan")
        limit_table.add_column("Value", justify="right")

        limit_table.add_row("Max Position Size", f"{limits.max_position_size} shares")
        limit_table.add_row("Max Position Value", f"${limits.max_position_value:,.2f}")
        limit_table.add_row("Max Order Value", f"${limits.max_order_value:,.2f}")
        limit_table.add_row("Max Daily Loss", f"${limits.max_daily_loss:,.2f}")
        limit_table.add_row("Max Daily Trades", str(limits.max_daily_trades))

        console.print(limit_table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@cli.command()
@click.pass_context
def kill(ctx: click.Context) -> None:
    """Activate kill switch - stops all automated trading."""
    console.print("[red]KILL SWITCH ACTIVATED[/red]")
    console.print("All automated trading is now stopped.")
    console.print("Manual trades via buy/sell commands are still allowed.")
    console.print("\nTo reset, restart the trading engine.")


@cli.command()
@click.option("--days", type=int, default=30, help="Number of days to simulate")
@click.option("--capital", type=float, default=100000, help="Starting capital")
@click.option("--volatility", type=float, default=0.02, help="Daily volatility (0.02 = 2%)")
@click.pass_context
def backtest(ctx: click.Context, days: int, capital: float, volatility: float) -> None:
    """Backtest your trading rules with simulated data.

    This runs a Monte Carlo simulation using your current rules
    to estimate potential performance.

    Examples:

        Basic backtest:
        trader backtest

        30 days with $50k:
        trader backtest --days 30 --capital 50000

        High volatility simulation:
        trader backtest --volatility 0.05
    """
    rules_data = load_rules()
    active_rules = [r for r in rules_data if r.enabled]

    if not active_rules:
        console.print("[yellow]No active rules to backtest[/yellow]")
        console.print("Add rules with: trader rules add buy AAPL 170 --qty 10")
        return

    console.print(f"[cyan]Running backtest...[/cyan]")
    console.print(f"Rules: {len(active_rules)}")
    console.print(f"Days: {days}")
    console.print(f"Capital: ${capital:,.2f}")
    console.print(f"Volatility: {volatility:.1%}")
    console.print()

    try:
        bt = Backtester(initial_capital=Decimal(str(capital)))
        result = bt.run(active_rules, days=days, volatility=Decimal(str(volatility)))

        # Results table
        table = Table(title="Backtest Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")

        table.add_row("Period", f"{result.start_date.strftime('%Y-%m-%d')} to {result.end_date.strftime('%Y-%m-%d')}")
        table.add_row("Initial Capital", f"${result.initial_capital:,.2f}")
        table.add_row("Final Capital", f"${result.final_capital:,.2f}")

        ret_style = "green" if result.total_return >= 0 else "red"
        table.add_row(
            "Total Return",
            f"[{ret_style}]${result.total_return:,.2f} ({result.total_return_pct:.2%})[/{ret_style}]",
        )

        table.add_row("Total Trades", str(result.total_trades))
        table.add_row("Winning Trades", str(result.winning_trades))
        table.add_row("Losing Trades", str(result.losing_trades))
        table.add_row("Win Rate", f"{result.win_rate:.1%}")
        table.add_row("Max Drawdown", f"[red]{result.max_drawdown:.2%}[/red]")

        console.print(table)

        # Show trades
        if result.trades:
            console.print()
            trade_table = Table(title="Simulated Trades")
            trade_table.add_column("Date", style="dim")
            trade_table.add_column("Symbol", style="cyan")
            trade_table.add_column("Side")
            trade_table.add_column("Qty", justify="right")
            trade_table.add_column("Price", justify="right")
            trade_table.add_column("Rule")

            for trade in result.trades[:20]:  # Show first 20
                side_style = "green" if trade.side == "buy" else "red"
                trade_table.add_row(
                    trade.timestamp.strftime("%m/%d"),
                    trade.symbol,
                    f"[{side_style}]{trade.side.upper()}[/{side_style}]",
                    str(trade.quantity),
                    f"${trade.price:,.2f}",
                    trade.rule_id,
                )

            console.print(trade_table)

            if len(result.trades) > 20:
                console.print(f"[dim]... and {len(result.trades) - 20} more trades[/dim]")

        console.print()
        console.print("[dim]Note: This is a simulation with random price movements. Results will vary.[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@cli.command()
@click.argument("symbols", nargs=-1)
@click.pass_context
def scan(ctx: click.Context, symbols: tuple[str, ...]) -> None:
    """Scan symbols for trading opportunities.

    Shows current prices and how close they are to any rule targets.

    Examples:

        Scan specific symbols:
        trader scan AAPL TSLA GOOGL

        Scan all symbols in rules:
        trader scan
    """
    config = ctx.obj["config"]

    if not config.alpaca_api_key:
        console.print("[red]Error: Alpaca API key not configured[/red]")
        return

    # Get symbols from rules if none provided
    if not symbols:
        rules_data = load_rules()
        symbols = tuple(set(r.symbol for r in rules_data))

    if not symbols:
        console.print("[yellow]No symbols to scan[/yellow]")
        console.print("Provide symbols: trader scan AAPL TSLA")
        return

    broker = get_broker(config)
    rules_data = load_rules()

    table = Table(title="Market Scan")
    table.add_column("Symbol", style="cyan")
    table.add_column("Bid", justify="right")
    table.add_column("Ask", justify="right")
    table.add_column("Spread", justify="right")
    table.add_column("Rules")
    table.add_column("Distance")

    for symbol in symbols:
        symbol = symbol.upper()
        try:
            q = broker.get_quote(symbol)
            mid = (q.bid + q.ask) / 2
            spread = q.ask - q.bid
            spread_pct = (spread / mid * 100) if mid > 0 else Decimal("0")

            # Find rules for this symbol
            symbol_rules = [r for r in rules_data if r.symbol == symbol and r.enabled]

            rule_strs = []
            distances = []
            for r in symbol_rules:
                cond = "≤" if r.condition == RuleCondition.BELOW else "≥"
                rule_strs.append(f"{r.action.value} {cond}${r.target_price:.0f}")

                # Calculate distance to target
                if r.condition == RuleCondition.BELOW:
                    dist = (mid - r.target_price) / r.target_price * 100
                else:
                    dist = (r.target_price - mid) / mid * 100
                distances.append(f"{dist:+.1f}%")

            table.add_row(
                symbol,
                f"${q.bid:,.2f}",
                f"${q.ask:,.2f}",
                f"${spread:.2f} ({spread_pct:.2f}%)",
                ", ".join(rule_strs) if rule_strs else "-",
                ", ".join(distances) if distances else "-",
            )

        except Exception as e:
            table.add_row(symbol, "[red]Error[/red]", "-", "-", "-", str(e))

    console.print(table)


if __name__ == "__main__":
    cli()
