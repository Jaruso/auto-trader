<div align="center">

# Kodiak

### Automated trading platform for human + AI collaboration

Trade lifecycle automation with a human-first CLI and agent-first MCP interface.

![python](https://img.shields.io/badge/python-3.11%2B-blue)
![license](https://img.shields.io/badge/license-Apache%202.0-green)
![protocol](https://img.shields.io/badge/protocol-MCP-purple)
![interfaces](https://img.shields.io/badge/interfaces-CLI%20%2B%20Server-0ea5e9)

</div>

Kodiak is a **Python monorepo** with two products:
- **Kodiak CLI** (`kodiak`) — Ad-hoc calculations, predefined workloads, manual trading, and stdio MCP for local agents.
- **Kodiak Server** (`kodiak-server`) — Headless persistent service with REST API, streamable HTTP MCP, a minimal landing page, and scheduling for remote integrations.

Both share a common core library (`kodiak-core`). The system supports paper and live trading via Alpaca, with strategy automation that manages the full trade lifecycle from entry to exit. From 2.0.0 onward, architecture and interfaces are stable; breaking changes are rare and clearly noted in [CHANGELOG](CHANGELOG.md).

The Bare Systems workspace also now contains an incubating cloud rendezvous
portal scaffold under [`../Portal/`](../Portal/README.md). That directory is
intentionally separate
from the trading runtime and is reserved for the future public control plane
that will broker authenticated access to home-edge services without terminating
application TLS in the cloud.

---

## Table of Contents

- [🚀 Features](#-features)
- [🤖 Using Kodiak](#-using-kodiak)
- [🧭 Operator Onboarding](#-operator-onboarding)
- [📦 Installation](#-installation)
- [⚙️ Configuration](#️-configuration)
- [▶️ Usage (CLI)](#️-usage-cli)
- [📊 Trading Strategies](#-trading-strategies)
- [🧪 Backtesting](#-backtesting)
- [🧪 Strategy Optimization](#-strategy-optimization)
- [📈 Indicators Library](#-indicators-library)
- [💡 Quick Start](#-quick-start)
- [🔒 Safety & Risk Controls](#-safety--risk-controls)
- [🤝 Contributing](#-contributing)
- [⚠️ Disclaimer](#️-disclaimer)

---

## 🚀 Features

Kodiak is built around a simple promise: **one trading core, two great interfaces**.

* ✅ **Human-first CLI + agent-first MCP**: run the same capabilities from terminal commands or MCP tools.
* ✅ **Strategy lifecycle automation**: define entry + exit behavior once, then let Kodiak manage the full trade lifecycle.
* ✅ **Research-to-execution workflow**: backtest, optimize, paper trade, then promote to production when validated.
* ✅ **Operational safety by default**: paper mode default, production confirmation, limits, kill switch, and audit logging.
* ✅ **Production-ready integration surface**: REST API + streamable HTTP MCP + stdio MCP for local and remote agents.

**MCP coverage:** 39 tools across engine, portfolio, research data, orders, strategies, backtests, analysis, indicators, optimization, safety, and scheduling.

### Feature Deep Dive

- **Dual interfaces, shared business logic**  
  CLI and MCP call the same app layer and schemas, which keeps behavior consistent across humans and agents.

- **Strategy engine (entry → management → exit)**  
  Supports `trailing-stop`, `bracket`, `scale-out`, `grid`, and `pullback-trailing` strategies with stateful lifecycle phases.

- **Backtesting + optimization**  
  Validate strategy behavior on historical data (CSV/Alpaca), then run grid or random search to tune parameters.

- **Portfolio intelligence**  
  Track balances, positions, orders, and ledger history with both quick summaries and detailed inspection.

- **Risk and control plane**  
  Built-in safety controls include position and buying-power checks, daily loss protections, rate-limited long-running MCP calls, and audit trails.

- **Notifications + automation**  
  Send alerts to Discord/webhooks and run via cron (CLI) or async scheduler (server) for continuous operations.

- **Deterministic signal monitoring**  
  Kodiak Server can poll configured external sources, classify explicit buy/sell language with regex rules, route unmatched items into a `needs_inference` bucket, and expose the resulting alerts over REST for downstream dashboards such as BearClawWeb.

## 🤖 Using Kodiak

**For human users**: Use the CLI. `kodiak --help` lists all commands.

**For AI agents**: Use the MCP tools (preferred). Connect via:
- CLI stdio MCP: `kodiak mcp` (for Claude Desktop, Cursor, local agents)
- Server HTTP MCP: `kodiak-server` then connect to `http://localhost:8000/mcp/` (for remote agents and optional external integrations)

CLI is for humans and testing; agents should use MCP tools for all operations.

## 🧭 Operator Onboarding

New operators should start with the [operator onboarding guide](docs/operator-onboarding.md). It covers the safe headless path from install to paper credentials, server startup, MCP connection, planning tools, explicit execution confirmation, smoke checks, and troubleshooting.

Common MCP workflows:
- `get_status` — confirm broker config, environment, engine state, and active strategy count
- `list_strategies` / `resume_strategy` — inspect and manage strategy lifecycle
- `run_backtest` / `run_optimization` — research and tune strategies on historical data
- `get_portfolio`, `get_positions`, `get_portfolio_analytics` — inspect the live portfolio plus snapshot-based analytics versus a benchmark such as `SPY`
- `calculate_position_size` / `get_rebalance_plan` — turn target weights, dollar caps, and risk budgets into planning outputs before placing trades
- `get_fundamentals` / `get_benchmark_history` — pull file-backed company fundamentals and normalized benchmark price history for research workflows
- `export_analysis_report` — generate JSON or Markdown trade analysis reports, optionally writing them to a local file from the MCP subprocess

For deterministic social-signal monitoring, create `config/market_signals.yaml` from
[`config/market_signals.yaml.example`](config/market_signals.yaml.example). The primary
X integration path now uses OAuth 2.0 user-context tokens obtained through
BearClawWeb's Settings UI, then stored in Kodiak for direct API calls and token refresh.
Kodiak expects the same X app credentials locally for refresh operations:

```env
X_CLIENT_ID=<x oauth client id>
X_CLIENT_SECRET=<x oauth client secret for confidential clients>
KODIAK_SIGNAL_ENCRYPTION_SECRET=<secret used to encrypt stored X refresh tokens>
```

With that in place, connect X in BearClawWeb under `Settings → Integrations → X`.

The monitor config still controls which followed-account posts become signals:

```yaml
enabled: true
sources:
  - id: x-signaldesk
    provider: x
    account: "@signaldesk"
    capture_unmatched: true
    rules:
      - id: buy-on-add
        pattern: "added\\s+\\$(?P<symbol>[A-Z]{1,5})"
        action: buy
```

With that config in place, Kodiak Server:
- polls the configured accounts on its background interval
- reads the authenticated user's X home timeline with OAuth when X is connected
- emits direct `buy` / `sell` alerts when a regex rule matches
- stores unmatched posts as `needs_inference` instead of guessing
- exposes the monitor via `GET /api/v1/signals/overview`, `/alerts`, and `/sources`
- supports an on-demand poll via `POST /api/v1/signals/poll`

The older Playwright-profile collector remains available as a fallback for local experimentation:

```yaml
x:
  enabled: true
  user_data_dir: /absolute/path/to/playwright-x-profile
```

`get_portfolio_analytics` accepts `lookback_days`, `benchmark_symbol`, and optional `end_date` (`YYYY-MM-DD`). When trade ledger records exist inside the lookback window, Kodiak reconstructs a transaction-level equity curve from current cash, current positions, trades, and historical closes. It also returns attribution grouped by symbol, rule, and best-effort strategy key derived from `rule_id`; if no ledger trades are available, it falls back to the reproducible current-holdings snapshot replay.

`export_analysis_report` accepts `format` (`json` or `markdown`), optional `output_path`, `symbol`, `days`, `limit`, `include_portfolio`, `portfolio_lookback_days`, and `benchmark_symbol`. If `output_path` is omitted, the tool returns the report content directly. If `include_portfolio=true`, the report includes portfolio analytics when broker credentials and historical data are available; otherwise it records a structured unavailable reason instead of failing the whole report. The same capability is available to humans as `kodiak analysis-report --output reports/analysis.md --format markdown --days 30`.

If an agent will run CSV-backed MCP tools such as `run_backtest`, `run_optimization`, or `get_portfolio_analytics`, include `HISTORICAL_DATA_DIR` in the MCP process `env` block so the subprocess can see your dataset.

`get_benchmark_history` also uses the configured historical data provider and returns normalized bars plus first close, latest close, and period return. `get_fundamentals` reads file-backed data from `FUNDAMENTALS_DATA_DIR` when set, otherwise from `data/fundamentals`. Supported layouts are `{SYMBOL}.json`, `fundamentals.json`, or `fundamentals.csv` with a `symbol` column.

To import fundamentals from a vendor export or manually maintained file:
```bash
poetry run python scripts/import_fundamentals.py /path/to/fundamentals.csv
poetry run python scripts/import_fundamentals.py /path/to/fundamentals.json --format json-files
poetry run python scripts/import_fundamentals.py /path/to/fundamentals.csv --max-age-days 120
```

Importer input can be CSV rows with a `symbol` column, a JSON list of objects, a single JSON object with `symbol`, or a JSON symbol map. Numeric fields are validated and non-finite values are rejected.

### Headless Server Landing Page

The server root `/` intentionally stays minimal. It links to `/health`, `/api/docs`, `/api/v1/schema.json`, and `/mcp/`, but it does not render account, order, or portfolio data. Kodiak remains headless-first: use the CLI for human operation, MCP for agents, and authenticated REST endpoints for integrations.

### Contract Snapshots

Kodiak checks in versioned contract artifacts for its public headless interfaces:
- `contracts/rest-openapi.v1.json` — generated from the REST OpenAPI schema.
- `contracts/mcp-tools.v1.json` — generated from the registered MCP tool schemas.

Regenerate snapshots after intentional REST or MCP contract changes:
```bash
poetry run python scripts/export_contracts.py
poetry run python scripts/export_contracts.py --check
```

CI runs snapshot tests so accidental endpoint, request, response, or MCP tool signature changes fail fast.

### Headless Smoke Harness

Run the release smoke harness before publishing or deploying:
```bash
poetry run python scripts/headless_smoke.py
poetry run python scripts/headless_smoke.py --json
```

The smoke harness runs in-process and does not place orders or start the engine. It validates `/health`, the landing page, REST authentication, the OpenAPI export, REST envelope shape, MCP authentication, and registered MCP tools.

`calculate_position_size` supports three methods:
- `target_value` — size to a desired dollar exposure
- `target_weight` — size to a desired portfolio weight percentage
- `risk_budget` — size from a dollar risk budget plus `stop_loss_pct`

`get_rebalance_plan` is planning-only. It returns proposed buy/sell quantities from a target weight map, optional drift threshold, optional cash buffer, and an option to liquidate symbols omitted from the target set.

Sensitive execution operations are guarded by Kodiak's headless execution policy. REST and MCP calls that place orders, cancel orders, start the engine, or stop the engine must pass `confirm_execution=true`; otherwise Kodiak returns `POLICY_BLOCKED` and writes an audit entry with the policy decision. CLI commands pass this intent explicitly because the user has invoked an execution command directly.

REST examples:
```bash
# Blocked: missing explicit execution intent
curl -X POST http://localhost:8000/api/v1/engine/stop \
  -H "Authorization: Bearer $KODIAK_API_TOKEN" \
  -H "X-Kodiak-Actor: operator@example.com" \
  -d '{"force": false}'

# Confirmed: reaches the engine state check
curl -X POST http://localhost:8000/api/v1/engine/stop \
  -H "Authorization: Bearer $KODIAK_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"force": false, "confirm_execution": true}'
```

MCP examples:
```json
{"tool": "stop_engine", "arguments": {"force": false}}
{"tool": "stop_engine", "arguments": {"force": false, "confirm_execution": true}}
```

**Quick Start**: See Installation and Configuration sections below.

## 📦 Installation

**Prerequisites**: Python 3.11+ ([python.org](https://www.python.org/downloads/)). On Windows, install from python.org and check **Add Python to PATH**.

### Option 1: CLI Only (Recommended)

For ad-hoc trading and Claude Desktop MCP:

```bash
git clone <repo-url>
cd Kodiak
pip install pipx
pipx install -e packages/cli/
```

Verify:
```bash
kodiak status
```

Config, data, and logs go to `~/.kodiak/` (macOS/Linux) or `%APPDATA%/kodiak/` (Windows).

**Configure Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "Kodiak": {
      "command": "kodiak",
      "args": ["mcp"],
      "env": {
        "ALPACA_API_KEY": "your_paper_key",
        "ALPACA_SECRET_KEY": "your_paper_secret",
        "HISTORICAL_DATA_DIR": "/absolute/path/to/historical-csvs"
      }
    }
  }
}
```

Claude Desktop often runs with a limited `PATH`, so the most reliable setup is to use the full binary path from `which kodiak`:
```json
{
  "mcpServers": {
    "Kodiak": {
      "command": "/usr/local/bin/kodiak",
      "args": ["mcp"],
      "env": { ... }
    }
  }
}
```

Restart Claude Desktop after saving. Done!

If you are developing Kodiak locally, each new stdio MCP session starts a fresh `kodiak mcp` subprocess, so restarting the agent client is enough to pick up code changes.

### Option 2: Server + CLI (For Integration)

For standalone server usage, remote agents, or optional external integrations:

```bash
git clone <repo-url>
cd Kodiak
pip install poetry
poetry install
```

Start the server:
```bash
poetry run kodiak-server
```

Server runs on `http://localhost:8000` with:
- REST API at `/api/`
- MCP endpoint at `/mcp/`
- Minimal headless landing page at `/`

Remote agents connect to `http://localhost:8000/mcp/` for MCP.

CLI is also available: `poetry run kodiak status`.

The included homelab Blink deployment publishes Kodiak on `http://192.168.86.53:18000` while keeping the app's internal server port at `8000`. Host port `8000` on that target is reserved for Portainer.

### Option 3: Development

For contributing to Kodiak:

```bash
git clone <repo-url>
cd Kodiak
pip install poetry
poetry install              # Install all 3 packages
pipx install -e packages/cli/    # Optional: CLI on PATH
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup.

### Troubleshooting

- **"kodiak" not found**: Ensure pipx bin is on PATH. Run `pipx ensurepath`.
- **"command not found" in Claude Desktop**: Use the full path. Run `which kodiak` and use that path in the config.
- **MCP server error**: Check Alpaca API keys and JSON syntax (no trailing commas). For CSV-backed MCP workflows, also set `HISTORICAL_DATA_DIR` in the MCP process environment.
- **Homelab Blink deploy fails with "port is already allocated"**: The included Blink manifest publishes Kodiak on `192.168.86.53:18000`. If you still see a bind error, check for another service already using that host port.
- **Tool not visible**: All 39 tools are registered. If a tool doesn’t appear in your client, it may be filtered. List all tools: `python3 -c "from kodiak.mcp.tools import build_server; [print(t.name) for t in build_server().list_tools()]"`

## ⚙️ Configuration

Configuration is **environment-based**: the app reads from environment variables and, when present, from a `.env` file (project root, CWD, or `~/.kodiak/.env` when installed). You can view and set values via the CLI; secrets are never shown in full when listing.

**Set API keys (persisted to `.env`):**
```bash
kodiak config set ALPACA_API_KEY your_paper_key
kodiak config set ALPACA_SECRET_KEY your_paper_secret
```

**View current config (secrets redacted):**
```bash
kodiak config list
kodiak config get ALPACA_API_KEY          # redacted
kodiak config get ALPACA_API_KEY --show-secret   # full value
kodiak config keys   # list all available keys
```

**Schedule (cron)** — CLI only:
```bash
kodiak schedule enable          # Install cron job (every 5 min default)
kodiak schedule enable --every 1  # Run every minute
kodiak schedule status          # Show whether enabled
kodiak schedule disable         # Remove cron job
```

For MCP/stdio, set keys in your `claude_desktop_config.json` `env` block so they are available to the subprocess. For CLI-only use, `kodiak config set` writes to the appropriate `.env` file.

### MCP server (optional)

When using the MCP server, you can tune rate limits and timeouts for long-running tools (`run_backtest`, `run_optimization`):

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_BACKTEST_TIMEOUT_SECONDS` | 300 | Max wall-clock time (seconds) for a single backtest; 0 = no limit. |
| `MCP_OPTIMIZATION_TIMEOUT_SECONDS` | 600 | Max wall-clock time (seconds) for a single optimization run; 0 = no limit. |
| `MCP_RATE_LIMIT_LONG_RUNNING_PER_MINUTE` | 10 | Max number of long-running tool calls (backtest + optimization combined) per 60-second window; 0 = no limit. |

### Logging and tracing

Kodiak Server now emits request-scoped logs and timing metadata by default:

- Every REST response includes `X-Request-ID` and `X-Process-Time-Ms`
- REST request logs include actor, role, method, path, status code, and duration
- Engine runs emit `engine_cycle_complete` metrics with cycle duration, action count, market-open state, and scheduled strategy activations

Server logging can be tuned with:

| Variable | Default | Description |
|----------|---------|-------------|
| `KODIAK_LOG_FORMAT` | `json` (server) | Log format for server processes. Use `json` for structured ingestion or `text` for local readability. |
| `KODIAK_LOG_TO_FILE` | `true` | When enabled, write `kodiak.log` and `trades.log` under the configured log directory in addition to stderr/stdout. |

For stdio MCP sessions, prefer stderr logging so the JSON-RPC/MCP transport stream stays clean. The CLI already does this for `kodiak mcp`.

### Notifications (optional)

Alerts can be sent to Discord or a custom webhook (e.g. for trade events or manual messages):

| Variable | Description |
|----------|-------------|
| `DISCORD_WEBHOOK_URL` | Discord webhook URL (primary channel). |
| `CUSTOM_WEBHOOK_URL` | Generic HTTP webhook URL (POST JSON with `message`). |
| `NOTIFICATIONS_ENABLED` | Set to `false` or `0` to disable all notifications. |

Optional YAML: copy `config/notifications.yaml.example` to `config/notifications.yaml` to configure events and channels. CLI: `kodiak notify test` (test delivery), `kodiak notify send "message"` (send manual message).

---

## ▶️ Usage (CLI)

### Check Status

```bash
kodiak status
```

### Start Trading Engine

```bash
kodiak start
```

For production:

```bash
kodiak --prod start
# You'll be prompted to confirm before trading with real money
```

### Stop Engine

```bash
kodiak stop
```

### Schedule (cron) mode — CLI only

Instead of running the engine as a long-lived loop, you can run one evaluation cycle on a schedule:

```bash
kodiak schedule enable          # every 5 minutes (default)
kodiak schedule enable --every 1 # every minute
kodiak schedule status          # show whether enabled and the cron line
kodiak schedule disable         # remove the cron job
```

Supported on macOS and Linux only. The job is added to your user crontab.

### View Portfolio

```bash
kodiak portfolio      # Full overview (balance + positions + orders)
kodiak balance        # Account summary with P/L
kodiak positions      # Open positions
kodiak orders         # Open orders
kodiak quote AAPL     # Get current quote
```

### Analyze Trades

```bash
# Last 30 days (default)
kodiak analyze

# Filter by symbol and time window
kodiak analyze --symbol AAPL --days 7
```

### Notifications

```bash
# Test notification delivery
kodiak notify test
kodiak notify test --channel discord

# Send a manual message
kodiak notify send "Trading paused for maintenance"
kodiak notify send "AAPL target hit" --channel discord
```

---

## 📊 Trading Strategies

Strategies are **automated trading plans** that handle both entry and exit, managing the complete trade lifecycle.

### Available Strategies

| Strategy | Description | Best For |
|----------|-------------|----------|
| **trailing-stop** | Rides trends, locks in gains with a trailing stop | Trending stocks you want to hold but protect gains |
| **bracket** | Take-profit AND stop-loss (first hit wins) | Trades with defined risk/reward |
| **scale-out** | Sells portions at progressive profit targets | Strong conviction plays where you want to lock some gains |
| **grid** | Buys at intervals down, sells at intervals up | Stocks that trade in a predictable range |

### Add a Strategy

```bash
# Trailing stop: buy AAPL, exit when price drops 5% from any high
kodiak strategy add trailing-stop AAPL --qty 10 --trailing-pct 5

# Bracket: buy TSLA with +10% take-profit and -5% stop-loss
kodiak strategy add bracket TSLA --qty 5 --take-profit 10 --stop-loss 5

# Scale out: buy GOOGL, sell portions at +5%, +10%, +15%
kodiak strategy add scale-out GOOGL --qty 20

# Grid: profit from NVDA's volatility with 5 buy/sell levels
kodiak strategy add grid NVDA --levels 5
```

### Strategy Options

All strategies support:

```bash
--qty INTEGER          # Number of shares (default: 1)
--limit, -L FLOAT      # Limit price for entry (default: market order)
```

Strategy-specific options:

```bash
# Trailing stop
--trailing-pct FLOAT   # Trailing stop percentage (default: 5%)

# Bracket
--take-profit FLOAT    # Take profit percentage (default: 10%)
--stop-loss FLOAT      # Stop loss percentage (default: 5%)

# Grid
--levels INTEGER       # Number of grid levels (default: 5)
```

### Manage Strategies

```bash
kodiak strategy list              # List all strategies
kodiak strategy show <id>         # Show details
kodiak strategy enable <id>       # Enable
kodiak strategy disable <id>      # Disable
kodiak strategy pause <id>        # Pause (keeps state)
kodiak strategy resume <id>       # Resume
kodiak strategy remove <id>       # Remove
kodiak strategy explain <type>    # Learn about a strategy type
```

### How Strategies Work

1. **Add a strategy** → It starts in `PENDING` phase
2. **Start the engine** → `kodiak start`
3. **Entry executes** → Strategy moves to `POSITION_OPEN`
4. **Exit conditions monitored** → Based on strategy type
5. **Exit executes** → Strategy moves to `COMPLETED`

Strategy phases: `PENDING` → `ENTRY_ACTIVE` → `POSITION_OPEN` → `EXITING` → `COMPLETED`

---

## 🧪 Backtesting

Test your trading strategies against historical data before risking real capital. Backtesting helps validate strategy logic, optimize parameters, and identify potential issues.

### Prepare Historical Data

For CSV-based backtesting, create CSV files with OHLCV data. The default directory is `data/historical/` (relative to project root) or `~/.kodiak/data/historical/` (when installed via pipx). You can override this with the `HISTORICAL_DATA_DIR` environment variable or the `--data-dir` flag.

**CSV File Format**:
- File naming: `{SYMBOL}.csv` (e.g., `AAPL.csv`, `MSFT.csv`)
- Required columns: `timestamp`, `open`, `high`, `low`, `close`, `volume`
- Timestamp format: ISO format or `YYYY-MM-DD HH:MM:SS`
- OHLCV values must be finite numbers. Files with `NaN`, `inf`, or `-inf` values are rejected before research, backtest, or analytics calculations run.

Example CSV file (`AAPL.csv`):
```csv
timestamp,open,high,low,close,volume
2024-01-02 09:30:00,185.75,186.50,185.00,185.75,50000000
2024-01-03 09:30:00,186.50,187.25,186.00,186.75,48000000
```

**Setup Steps**:
```bash
# Option 1: Use default directory (project root)
mkdir -p data/historical
# Add CSV files: data/historical/AAPL.csv, data/historical/MSFT.csv, etc.

# Option 2: Use custom directory via environment variable
export HISTORICAL_DATA_DIR=/path/to/your/data
mkdir -p $HISTORICAL_DATA_DIR
# Add CSV files: $HISTORICAL_DATA_DIR/AAPL.csv, etc.

# Option 3: Use --data-dir flag when running backtests
kodiak backtest run trailing-stop AAPL --data-dir /path/to/data ...
```

**Note**: If you get a "Data directory not found" error, check that:
1. The directory exists and contains CSV files named `{SYMBOL}.csv`
2. CSV files have the required columns (timestamp, open, high, low, close, volume)
3. The `HISTORICAL_DATA_DIR` environment variable is set correctly (if using custom path)

### Run a Backtest

```bash
# Trailing stop strategy
kodiak backtest run trailing-stop AAPL \
  --start 2024-01-02 \
  --end 2024-12-31 \
  --qty 10 \
  --trailing-pct 5 \
  --data-source csv \
  --data-dir data/historical

# Bracket strategy
kodiak backtest run bracket TSLA \
  --start 2024-01-02 \
  --end 2024-12-31 \
  --qty 5 \
  --take-profit 10 \
  --stop-loss 5 \
  --data-source csv \
  --data-dir data/historical

# Alpaca historical data (requires API keys)
kodiak backtest run trailing-stop AAPL \
  --start 2024-01-02 \
  --end 2024-12-31 \
  --qty 10 \
  --trailing-pct 5 \
  --data-source alpaca
```

### Options

```bash
--start YYYY-MM-DD          # Start date (required)
--end YYYY-MM-DD            # End date (required)
--qty INTEGER               # Quantity to trade (default: 10)
--initial-capital FLOAT     # Starting capital (default: 100000)
--data-source csv|alpaca|cached  # Data source
--data-dir PATH             # Directory with CSV files
--save / --no-save          # Save results (default: save)
--chart PATH                # Save chart to HTML file
--show                       # Open chart in browser
--theme dark|light           # Chart theme (default: dark)
```

Note: Parquet caching requires the optional `pyarrow` dependency
(`pip install pyarrow`).

### View Results

```bash
# List all backtests
kodiak backtest list

# Show detailed results
kodiak backtest show <backtest-id>

# Compare multiple backtests
kodiak backtest compare <id1> <id2> <id3>

# Save a chart for an existing backtest
kodiak backtest show <backtest-id> --chart charts/backtest.html

# Visualize a backtest by ID or JSON file
kodiak visualize <backtest-id> --output charts/backtest.html --historical-dir data/historical
kodiak visualize data/backtests/abc123.json --show --historical-dir data/historical
```

### What Gets Tracked

* **Performance**: Total return, return %, final equity
* **Trade Statistics**: Win rate, profit factor, total trades
* **Risk Metrics**: Max drawdown, avg win/loss, largest win/loss
* **Trade History**: Complete log of all fills with prices
* **Equity Curve**: Portfolio value over time

### Order Fill Simulation

* **Market orders**: Fill at current bar's close price
* **Limit orders**: Fill at limit price if within bar's [low, high] range
* **Stop orders**: Fill at stop price if triggered by bar's range
* **Trailing stops**: Track high watermark, trigger on pullback threshold

### Example Output

```bash
$ kodiak backtest show abc123

         Backtest Results - abc123
┌─────────────────┬────────────────────────┐
│ Symbol          │ AAPL                   │
│ Strategy        │ trailing_stop          │
│ Date Range      │ 2024-01-02 to 2024-12-31│
│ Initial Capital │ $100,000.00            │
│ Final Equity    │ $115,250.00            │
│ Total Return    │ +$15,250.00            │
│ Return %        │ +15.25%                │
│ Total Trades    │ 12                     │
│ Winning Trades  │ 8 (66.7%)              │
│ Max Drawdown    │ $3,200.00 (3.2%)       │
└─────────────────┴────────────────────────┘
```

### Best Practices

1. **Test with sufficient data**: Use at least 6-12 months of historical data
2. **Account for costs**: Results don't include slippage or commissions yet (coming in Phase 4)
3. **Validate assumptions**: Backtest results show what *could have* happened, not what *will* happen
4. **Paper trade next**: After successful backtests, validate in paper trading before going live
5. **Multiple scenarios**: Test across different market conditions (trending, ranging, volatile)

---

## 🧪 Strategy Optimization

Use `kodiak optimize` to run grid or random search over strategy parameters.

```bash
# Optimize trailing-stop percentage (grid search)
kodiak optimize trailing-stop \
  --symbol AAPL \
  --start 2024-01-02 \
  --end 2024-12-31 \
  --params trailing_stop_pct:2,3,4 \
  --objective total_return_pct \
  --show-results

# Optimize bracket strategy with multiple parameters
kodiak optimize bracket \
  --symbol TSLA \
  --start 2024-01-02 \
  --end 2024-12-31 \
  --params take_profit_pct:5,8 stop_loss_pct:2,4 \
  --objective profit_factor \
  --method grid \
  --show-results

# Random search with sampling
kodiak optimize trailing-stop \
  --symbol SPY \
  --start 2024-01-02 \
  --end 2024-12-31 \
  --params trailing_stop_pct:1,2,3,4,5 \
  --method random \
  --num-samples 10 \
  --show-results
```

### Optimization Options

```bash
--params KEY:VAL1,VAL2      # Parameter grid (repeatable)
--objective total_return_pct|total_return|win_rate|profit_factor|max_drawdown_pct
--method grid|random         # Search method
--num-samples INTEGER        # Required for random search
--data-source csv|alpaca|cached
--data-dir PATH              # Historical data directory
--results-dir PATH           # Optimization results directory
--save / --no-save           # Save results (default: save)
--show-results               # Display results summary
```

Saved optimization results are stored under `data/optimizations/` by default.

---

## 📈 Indicators Library

Kodiak ships with a lightweight indicators library. If `pandas-ta` is
installed it will be used; otherwise, built-in pandas-based calculations are used.

```bash
# List indicators
kodiak indicator list

# Describe an indicator
kodiak indicator describe rsi
```

Available indicators include SMA, EMA, RSI, MACD, ATR, Bollinger Bands, OBV, VWAP,
and a rolling high/low band helper.

---

## 💡 Quick Start

```bash
# 1. Configure your Alpaca keys in .env

# 2. Check connection
kodiak status
kodiak balance

# 3. Add a strategy
kodiak strategy add trailing-stop AAPL --qty 5 --trailing-pct 5

# 4. Dry run first
kodiak start --dry-run --once

# 5. When ready, run for real
kodiak start
```

---

## 🔒 Safety & Risk Controls

Kodiak enforces multiple layers of protection:

* Paper trading by default
* Production requires `--prod` flag with interactive confirmation
* Position size limits
* Daily loss limits
* Kill switch available
* Immutable audit logs — `logs/audit.log` (JSONL) records place_order, cancel_order, create_strategy, remove_strategy, run_backtest, stop_engine from both CLI and MCP, with source and timestamp

**Never deploy to production without extensive paper testing.**

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

---

## ⚠️ Disclaimer

This software is for educational and experimental purposes only. It is not financial advice. Use at your own risk.

---
