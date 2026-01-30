"""CLI entry point for AutoTrader."""

import click
from rich.console import Console
from rich.table import Table

from decimal import Decimal

from trader import __version__
from trader.api.alpaca import AlpacaBroker
from trader.api.broker import Broker, OrderSide, OrderType
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
    console.print("[yellow]Rules list not yet implemented[/yellow]")


@rules.command("add")
@click.argument("direction", type=click.Choice(["long", "short"]))
@click.argument("symbol")
@click.argument("price", type=float)
@click.option("--qty", type=int, default=1, help="Quantity to trade")
@click.pass_context
def rules_add(
    ctx: click.Context, direction: str, symbol: str, price: float, qty: int
) -> None:
    """Add a trading rule."""
    console.print(f"[yellow]Adding rule: {direction} {symbol} @ ${price} qty={qty}[/yellow]")
    console.print("[yellow]Rules add not yet implemented[/yellow]")


@cli.command()
@click.option("--confirm", is_flag=True, help="Confirm production start")
@click.pass_context
def start(ctx: click.Context, confirm: bool) -> None:
    """Start the trading engine."""
    config = ctx.obj["config"]

    if config.env == Environment.PROD and not confirm:
        console.print("[red]Error: Production start requires --confirm flag[/red]")
        return

    if config.env == Environment.PROD and not config.enable_prod:
        console.print("[red]Error: Production trading is disabled[/red]")
        console.print("Set ENABLE_PROD=true in .env.prod to enable")
        return

    console.print(f"[green]Starting trading engine in {config.env.value} mode...[/green]")
    console.print("[yellow]Trading engine not yet implemented[/yellow]")


@cli.command()
@click.pass_context
def stop(ctx: click.Context) -> None:
    """Stop the trading engine."""
    console.print("[yellow]Stop command not yet implemented[/yellow]")


if __name__ == "__main__":
    cli()
