"""Built-in primitive definitions for Kodiak's core financial actions.

Each primitive descriptor is registered in the global registry on import.
The actual execution logic lives in the existing app/MCP/REST layers;
these objects describe the contract those layers expose.
"""

from __future__ import annotations

from kodiak.primitives.base import ExecutionMode, LatencyClass, Primitive, RiskLevel, register

# ---------------------------------------------------------------------------
# get_quote
# ---------------------------------------------------------------------------

get_quote = Primitive(
    name="get_quote",
    version="1.0.0",
    description=(
        "Fetch the latest bid/ask/last quote for a single equity symbol. "
        "Read-only. Safe for high-frequency agent polling."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Equity ticker symbol (e.g. 'AAPL').",
            },
        },
        "required": ["symbol"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "bid": {"type": "number"},
            "ask": {"type": "number"},
            "last": {"type": "number"},
            "timestamp": {"type": "string", "format": "date-time"},
        },
        "required": ["symbol"],
    },
    permissions=["market_data:read"],
    risk_level=RiskLevel.READ_ONLY,
    execution_mode=ExecutionMode.SYNC,
    tags=["market_data", "quotes"],
    latency_class=LatencyClass.REALTIME,
)

# ---------------------------------------------------------------------------
# place_order
# ---------------------------------------------------------------------------

place_order = Primitive(
    name="place_order",
    version="1.0.0",
    description=(
        "Submit a market or limit order to the configured broker. "
        "Requires confirm_execution=true. Always paper-trading via MCP."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Equity ticker."},
            "qty": {"type": "integer", "minimum": 1, "description": "Share quantity."},
            "side": {
                "type": "string",
                "enum": ["buy", "sell"],
                "description": "Order side.",
            },
            "price": {"type": "number", "description": "Limit price (0 for market)."},
            "confirm_execution": {
                "type": "boolean",
                "description": "Must be true to submit the order.",
            },
        },
        "required": ["symbol", "qty", "side", "price", "confirm_execution"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "order_id": {"type": "string"},
            "symbol": {"type": "string"},
            "qty": {"type": "integer"},
            "side": {"type": "string"},
            "status": {"type": "string"},
        },
        "required": ["order_id", "symbol", "qty", "side", "status"],
    },
    permissions=["orders:write", "confirm_execution"],
    risk_level=RiskLevel.HIGH,
    execution_mode=ExecutionMode.SYNC,
    tags=["orders", "execution"],
    latency_class=LatencyClass.FAST,
)

# ---------------------------------------------------------------------------
# run_backtest
# ---------------------------------------------------------------------------

run_backtest = Primitive(
    name="run_backtest",
    version="1.0.0",
    description=(
        "Run a historical backtest for one or more symbols using a named strategy. "
        "No broker interaction — purely computational. Results are saved by default."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "strategy_type": {
                "type": "string",
                "enum": ["trailing-stop", "bracket"],
                "description": "Strategy to backtest.",
            },
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "description": "One or more ticker symbols.",
            },
            "start": {
                "type": "string",
                "format": "date",
                "description": "Start date (YYYY-MM-DD).",
            },
            "end": {
                "type": "string",
                "format": "date",
                "description": "End date (YYYY-MM-DD).",
            },
            "initial_capital": {
                "type": "number",
                "minimum": 1,
                "description": "Starting capital in USD.",
            },
            "trailing_pct": {
                "type": "number",
                "description": "Trailing stop percentage (trailing-stop only).",
            },
        },
        "required": ["strategy_type", "symbols", "start", "end"],
        "additionalProperties": True,
    },
    output_schema={
        "type": "object",
        "description": "BacktestResponse or PortfolioBacktestResponse depending on symbol count.",
        "properties": {
            "id": {"type": "string"},
            "strategy_type": {"type": "string"},
            "total_return_pct": {"type": "string"},
            "win_rate": {"type": "string"},
            "max_drawdown_pct": {"type": "string"},
        },
    },
    permissions=["backtests:run"],
    risk_level=RiskLevel.MEDIUM,
    execution_mode=ExecutionMode.SYNC,
    tags=["backtesting", "research"],
    latency_class=LatencyClass.BATCH,
)

# ---------------------------------------------------------------------------
# Auto-register on import
# ---------------------------------------------------------------------------

for _primitive in (get_quote, place_order, run_backtest):
    register(_primitive)
