# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **Versioned REST API (K1-A)** — All REST routes are now under `/api/v1/` (e.g. `/api/v1/engine/status`, `/api/v1/portfolio/summary`). The previous unversioned paths no longer exist.
- **Standard response envelopes (K1-B)** — Every REST response now uses a consistent JSON envelope: `{"data": ..., "error": null, "meta": {"request_id": "...", "version": "v1"}}` for success and `{"data": null, "error": {"code": ..., "message": ...}, "meta": {...}}` for errors. `AppError` subclasses map to correct HTTP status codes (404 for `NotFoundError`, 422 for `ValidationError`, 400 for others).
- **Actor propagation (K1-C)** — REST middleware accepts `X-Kodiak-Actor` and `X-Kodiak-Role` headers and threads them into the audit log. Every audit entry now includes `actor`, `role`, and `request_id` fields when a request originates from the REST API. New `set_audit_context()` function in `audit.py` for setting these context vars.
- **Request ID tracing** — Every API response carries an `X-Request-ID` response header and a matching `meta.request_id` in the body. Both are the same UUID generated per request.
- **OpenAPI schema export (K1-D)** — `GET /api/v1/schema.json` returns the full OpenAPI spec for the REST API. Useful for generating typed clients and contract validators. Interactive docs remain at `/api/docs`.
- **REST API contract tests** — New `tests/server/test_rest_api.py` covering: auth enforcement, versioned routes, envelope shape, request ID consistency, actor header acceptance, and schema export.
- **Portfolio analytics (K3-A)** — Added snapshot-based portfolio analytics with Sharpe ratio, max drawdown, rolling returns, benchmark comparison (`SPY` by default), exposure summaries, a new REST endpoint at `GET /api/v1/portfolio/analytics`, and a new MCP tool `get_portfolio_analytics`. This pass intentionally replays current holdings over historical closes rather than reconstructing transaction-level portfolio history.
- **Portfolio construction primitives (K3-B)** — Added planning-only position sizing and rebalance planning via new MCP tools `calculate_position_size` and `get_rebalance_plan`, plus REST endpoints at `POST /api/v1/portfolio/position-size` and `POST /api/v1/portfolio/rebalance-plan`. Supports target-value, target-weight, and risk-budget sizing, along with drift thresholds, cash buffers, and optional liquidation of omitted symbols for rebalance plans.
- **CI pipeline (K4-A)** — Added a GitHub Actions workflow that runs `ruff check`, scoped `mypy`, `pytest`, and coverage generation on pull requests and pushes to `main`, with `coverage.xml` uploaded as a workflow artifact.
- **Structured logging and tracing (K4-B)** — Added JSON-capable structured logging, REST request timing with `X-Request-ID` and `X-Process-Time-Ms`, and engine-cycle metric events for observability across server and automation flows.
- **Research data expansion (K5-A)** — Added file-backed fundamentals and normalized benchmark history through new MCP tools `get_fundamentals` and `get_benchmark_history`, plus REST endpoints at `GET /api/v1/research/fundamentals/{symbol}` and `GET /api/v1/research/benchmark/{symbol}`.
- **Fundamentals ingestion (K5-C)** — Added `scripts/import_fundamentals.py` and reusable ingestion utilities to validate CSV/JSON fundamentals exports, enforce optional `as_of` freshness, and write Kodiak-readable `fundamentals.json`, per-symbol JSON, or CSV layouts.
- **Headless server landing page (K6-A)** — Kept Kodiak headless-first by replacing the browser dashboard shell with a minimal server landing page that links to health, REST docs, schema export, and MCP without rendering account or trading data.
- **Headless execution policy (K6-B)** — Added a shared execution policy layer that classifies actions and blocks sensitive REST/MCP execution calls unless `confirm_execution=true`, while attaching policy decision metadata to audit logs.
- **Policy contract coverage (K6-C)** — Added REST and MCP contract tests proving sensitive execution tools and endpoints block without confirmation, reach the underlying execution layer with confirmation, and emit audit records with policy metadata and request context.
- **Contract snapshots (K7-A)** — Added checked-in REST OpenAPI and MCP tool schema snapshots plus a regeneration script and snapshot tests to catch accidental public interface changes.
- **Headless smoke harness (K7-B)** — Added an in-process release smoke command that validates health, landing page, REST auth/schema/envelope, MCP auth, and MCP tool registration without placing orders or starting the engine.
- **Operator onboarding docs (K7-C)** — Added a focused headless operator runbook covering install, paper configuration, REST/MCP access, planning-first workflows, execution confirmation, release checks, and troubleshooting.
- **Transaction-level portfolio analytics (K8-A)** — Portfolio analytics now use trade ledger records when available to reconstruct an equity curve from current cash, current positions, transactions, and historical closes, while preserving snapshot replay as the no-ledger fallback.
- **Performance attribution (K8-B)** — Transaction-level portfolio analytics now include attribution grouped by symbol, rule, and best-effort strategy key, with realized P&L, unrealized P&L, total P&L, contribution, trade counts, and buy/sell quantities.
- **Realistic execution modeling (K9-A)** — Backtests now support configurable fee models (fixed per order or percentage of notional), slippage models (fixed bps or volatility-aware bps scaled by bar range), and partial fill simulation. Results include `total_fees_paid`, `gross_return`, and `gross_return_pct` alongside existing net metrics, and the applied `execution_config` is persisted in result artifacts for auditability. All models are exposed via CLI, MCP (`run_backtest`, `run_optimization`), and REST schemas. Defaults preserve zero-cost full-fill backward compatibility.
- **Multi-symbol portfolio backtesting (K9-B)** — `BacktestRequest` now accepts a `symbols: list[str]` field in addition to the legacy `symbol: str`. When multiple symbols are provided, capital is split equally and each symbol is backtested independently; a `PortfolioBacktestResponse` is returned with portfolio-level summary metrics (return, drawdown, win rate, fees) and a per-symbol attribution table. The MCP `run_backtest` tool exposes a new `symbols` parameter; the CLI `backtest run` command accepts multiple positional SYMBOL arguments. Existing single-symbol workflows are unchanged.
- **Exportable headless analysis reports (K8-C)** — Added JSON and Markdown analysis report generation through the app layer, CLI (`kodiak analysis-report`), REST (`POST /api/v1/reports/analysis`), and MCP (`export_analysis_report`) without introducing embedded UI state.
- **Financial action primitive SDK (K10-A)** — Added `kodiak.primitives` module defining a typed, versioned descriptor layer for deterministic financial actions. Each `Primitive` carries name, version, description, input/output JSON Schema, permissions, risk level (`read_only`/`low`/`medium`/`high`), and execution mode. Three built-in primitives are registered on import: `get_quote` (read-only), `place_order` (high risk), and `run_backtest` (medium risk). The registry is exposed through CLI (`kodiak primitives list/describe`), REST (`GET /api/v1/primitives/`, `GET /api/v1/primitives/{name}`), and MCP (`list_primitives`, `describe_primitive` tools). New primitives can be registered via `kodiak.primitives.register()`.
- **Primitive registry versioning and governance (K10-B)** — The primitive registry now stores all registered versions per primitive name and resolves "latest" to the highest semver non-deprecated version (falling back to deprecated only when every version is deprecated). Added `deprecated: bool`, `deprecation_message: str | None`, and `latency_class: LatencyClass` (`realtime`/`fast`/`batch`) fields to `Primitive`. All three built-in primitives carry latency class annotations. New surface area: REST `GET /api/v1/primitives/{name}/versions`, `GET /api/v1/primitives/{name}?version=<semver>`, `GET /api/v1/primitives/?include_deprecated=true`; CLI `kodiak primitives versions <name>`, `kodiak primitives list --show-deprecated`, `kodiak primitives describe --version <semver>`; MCP `describe_primitive` accepts an optional `version` arg. Version resolution logic lives in `_semver_key()` in `base.py`.
- **Workflow orchestration engine (K11-A)** — Added `kodiak.orchestration` module implementing the AI = planner / Kodiak = executor paradigm. A `WorkflowPlan` is a named, ordered sequence of `WorkflowStep`s each referencing a registered primitive by name with its inputs. `WorkflowExecutor` runs steps sequentially, logs plan intent vs actual execution, retries on transient exceptions (linear back-off, configurable per step), halts on business-level `AppError` responses (no retry), and records per-step results including version resolved, output, attempt count, and timing. `deterministic=True` validates all primitives are registered before execution begins. Dispatch is auto-populated from MCP tool functions by name matching. Exposed via REST (`POST /api/v1/workflows/run`) and MCP (`run_workflow` tool, 42 tools total). `depends_on` field on steps reserves the interface for future DAG execution.
- **Execution session memory layer (K12-A)** — Every workflow execution is now automatically persisted as an `ExecutionSession` record in `data/sessions/`. Each session captures the full plan spec, all step outputs (primitive name, version, inputs, output, timing), aggregate outcome, and start/end timestamps — enabling post-hoc audit, reproducibility, and AI context minimization. `SessionStore` provides a file-backed store with per-session JSON files. `replay_session` re-executes a stored plan and persists a new session. Exposed via REST (`GET /api/v1/sessions/`, `GET /api/v1/sessions/{id}`, `POST /api/v1/sessions/{id}/replay`), MCP (`list_sessions`, `get_session`, `replay_session` — 47 tools total), and CLI (`kodiak sessions list/show/replay`). Both the `run_workflow` and `run_workflow_spec` tools and REST endpoints now return a `session_id` in their response.
- **Financial workflow DSL (K11-B)** — Added a declarative YAML/JSON workflow spec language so AI agents and operators can author multi-step financial workflows without writing Python. Supports three authoring formats: full form (`name:`/`steps:` with dict steps), short form (bare primitive name strings), and compact form (`{workflow_name: [step, ...]}`) — all compile to a `WorkflowPlan` and execute identically. `WorkflowSpec.validate()` reports unknown primitives, empty step lists, and invalid retry counts before execution. `WorkflowSpec.compile()` produces a `WorkflowPlan` ready for `WorkflowExecutor`. New loaders: `from_yaml()`, `from_json()`, `from_file()` (auto-detects format by extension). Exposed via REST (`POST /api/v1/workflows/validate`, `POST /api/v1/workflows/run-spec`), MCP (`validate_workflow_spec`, `run_workflow_spec` — 44 tools total), and CLI (`kodiak workflow validate <file>`, `kodiak workflow run-file <file>`). Example workflow files added under `examples/workflows/`.

### Added (K2 — State Management)

- **PostgreSQL strategy store (K2-A)** — New `kodiak.db` module with `db/connection.py`, `db/migrations.py`, and `db/pg_strategy_store.py`. When `KODIAK_DATABASE_URL` is set, `strategies/loader.py` routes all reads/writes to the `kodiak.strategies` Postgres table. Falls back to YAML transparently when the env var is absent, so CI and local dev continue unchanged.
- **PostgreSQL order store (K2-B)** — `db/pg_order_store.py` mirrors the OMS `save_order`/`load_orders`/`save_orders` interface against a `kodiak.orders` Postgres table with indexed `external_id` and `status` columns. `oms/store.py` routes to Postgres when configured.
- **Auto-migration on startup** — `kodiak-server` now calls `ensure_schema()` during the FastAPI lifespan startup hook. Schema is applied automatically on every deploy — no manual migration step needed. If `KODIAK_DATABASE_URL` is unset, startup is a no-op and YAML stores are used. Migration failure logs a warning but does not crash the server.
- **Enriched audit log (K2-C)** — Audit records now include `client_ip` (source IP of REST requests) in addition to `actor`, `role`, and `request_id` added in K1. The audit file is opened in append-only mode; all fields are written atomically per record.
- **psycopg2-binary** — Added to `kodiak-core` dependencies.

### Fixed

- **Dogfood resilience for strategy state and analysis surfaces** — Strategy and order storage now fall back to the local YAML stores when `KODIAK_DATABASE_URL` is configured but PostgreSQL is unreachable, so `status`, `strategy list`, and other read-heavy flows keep working during partial outages. Portfolio analytics now retry against Alpaca historical data when local CSV coverage is incomplete, and backtest listings/report exports now surface duplicate setups, open-position runs, and richer portfolio/strategy snapshots for operator review.
- **Historical data quality guardrails** — CSV, Alpaca, and cached historical data now reject non-finite OHLCV values (`NaN`, `inf`, `-inf`). Invalid cached bars are discarded and refetched from the wrapped provider instead of poisoning benchmark, backtest, or portfolio analytics workflows.
- **Container port mapping** — Start command was mapping `6702:6702` (host:container) but the container listens on `8000`. Corrected to `6702:8000`. Updated `port-published` verify regex from `6702->6702` to `6702->8000` to match. This was the root cause of health check timeouts on deploy.

### Changed

- **Portal path docs** — Updated Kodiak's workspace documentation to point at the root-level `../Portal/` rendezvous scaffold after it was moved out of the Kodiak repo tree.
- **Portal scaffold** — Added an incubating `Portal/` control-plane starter with a file-backed site registry, a rendezvous route-resolution API, and directory-local architecture notes for the future public cloud entrypoint. This is not the finished hosted product; public-host and Blink integration remain open.
- **Homelab port renumbered** — Changed homelab host port from `6704` to `6702`. Dropped the reserved `kodiak_mcp_port` (`6705`) — REST and `/mcp` are served on the same port. Updated `blink.toml` target, service port, `port-published` verify regex, and network contract comment.
- **Homelab Blink publish port** — Split Kodiak's internal container port (`8000`) from its published homelab port (`18000`) in the included Blink manifest, avoiding the host-port collision with Portainer while keeping the server's internal runtime contract unchanged.
- **Local Blink file privacy** — Ignored the repository-root `blink.toml` and `BLINK.md` and stopped tracking them so homelab-specific Blink targets and operator notes stay local-only.

## [2.0.1] - 2026-03-11

### Changed

- **README overhaul** — Finalized product-facing documentation refresh with a redesigned hero/header, cleaner platform narrative, and structured Table of Contents. Also corrected stale command/path examples to consistently use `kodiak` and `~/.kodiak`.

## [2.0.0] - 2026-03-06

### Added

- **Monorepo Architecture** — Kodiak is now a Python monorepo with three packages:
  - `kodiak-core` (packages/core/) — Shared library with app services, schemas, MCP tools, broker integrations, backtesting, strategies, indicators, and domain modules.
  - `kodiak-cli` (packages/cli/) — Click CLI tool for humans. Exposes MCP tools via stdio transport (`kodiak mcp` command).
  - `kodiak-server` (packages/server/) — FastAPI-based persistent server with REST API at `/api/`, streamable-HTTP MCP at `/mcp/`, a minimal landing page, and async scheduler. Supports direct usage plus optional external integrations.
- **Three Entry Points**:
  - `kodiak` — CLI tool (installed globally via `pipx install -e packages/cli/`)
  - `kodiak-server` — Persistent server (started via `poetry run kodiak-server` or `kodiak-server`)
  - Both share 32 MCP tools defined in `kodiak/mcp/tools.py` (transport-agnostic)
- **Transport-Agnostic MCP Tools** — All 32 tools moved from `trader/mcp/server.py` to `kodiak/mcp/tools.py`. New `build_server()` factory creates FastMCP instances; `register_tools()` wires all tools. CLI uses stdio, server uses streamable-http.
- **Poetry Workspace** — Root `pyproject.toml` with `package-mode = false` and path dependencies to all three packages. Developers run `poetry install` once from the root and get all packages in editable mode.
- **Path Resolution** — Updated from fragile relative traversal to robust `.git` directory walking. Supports monorepo structure and works when installed globally via pipx.

### Changed

- **Command Renaming** — `trader` → `kodiak` for the CLI tool. Examples: `kodiak status`, `kodiak strategy add`, `kodiak backtest run`, `kodiak mcp`.
- **MCP Command Simplification** — `trader mcp serve` → `kodiak mcp` (shorter, clearer).
- **Config Paths** — `.baretrader/` → `.kodiak/` for consistency.
- **Documentation** — CLAUDE.md, CONTRIBUTING.md, README.md, and PLAN.md updated for monorepo architecture, new command names, and dual-interface (CLI + Server) design.
- **Test Reorganization** — Tests split into `tests/core/`, `tests/cli/`, `tests/server/`, `tests/integration/`. All imports updated from `trader.*` to `kodiak.*` or `kodiak_cli.*`.

### Removed

- **Old `trader/` Package** — Replaced by three new packages in the monorepo.

### Fixed

- **Subprocess Spawn** — Engine subprocess now invokes `kodiak_cli.main` (not `trader.cli.main`).

### Quality

- ✅ All 217 tests passing
- ✅ Monorepo workspace validation
- ✅ Cross-package integration tests (CLI–MCP parity)
- ✅ Contract tests for MCP tools and REST API

## [1.1.0] - 2026-02-13

### Fixed
- **Strategy loading with hyphen format** — `Strategy.from_dict()` now normalizes `"pullback-trailing"` (hyphen) to `"pullback_trailing"` (underscore) enum value, fixing failures when `strategies.yaml` contains hyphen-formatted strategy types. All strategy operations (`list_strategies`, `create_strategy`, `get_strategy`) now work correctly regardless of config format.
- **Optimization parameter normalization** — `run_optimization` now accepts both short parameter names (`take_profit`, `stop_loss`) and canonical names (`take_profit_pct`, `stop_loss_pct`). Short names are automatically normalized to canonical format before validation, fixing "Missing required parameters" errors when using CLI/MCP-friendly names.

### Changed
- **CSV data path documentation** — Enhanced README with comprehensive "Backtesting with CSV Data" section explaining CSV file format, directory setup, environment variable (`HISTORICAL_DATA_DIR`), and default paths. Improved error messages in CSV provider and backtest app layer to include setup instructions and links to documentation.
- **MCP tool visibility documentation** — Added troubleshooting note in README and CONTRIBUTING about tool visibility in MCP clients. Created helper script `scripts/list_mcp_tools.py` to list all registered tools for debugging. Updated MCP server docstring for `run_optimization` to document parameter name normalization.

### Added
- **Test coverage** — Added `test_strategy_load_with_hyphen_format()` to verify strategy loading with hyphen format. Added `tests/test_optimization_params.py` with tests for parameter normalization (`test_normalize_param_keys_take_profit`, `test_normalize_param_keys_canonical_preserved`, `test_normalize_param_keys_mixed`, `test_optimization_with_short_param_names`).

## [1.0.0] - 2026-02-13

### Added
- **Schedule (cron) commands** — `trader schedule enable` installs a user crontab job that runs `trader run-once` on a schedule (default every 5 minutes; `--every N` for 1–60 minutes). `trader schedule disable` removes the job; `trader schedule status` shows whether it is enabled and the cron line. Supported on macOS and Linux. No environment variable; the schedule is enabled or disabled by adding/removing the cron job.
- **Pullback-trailing strategy** — New strategy type `pullback-trailing`: wait for price to pull back X% from the observed high, then buy at market; after entry, exit is managed with a trailing stop. Holistic "buy the dip + trail gains" strategy. CLI: `trader strategy add pullback-trailing SYMBOL --qty N --pullback-pct 5 --trailing-pct 5`. MCP: `create_strategy(strategy_type="pullback-trailing", symbol=..., qty=..., pullback_pct=5, trailing_pct=5)`. Engine sets reference price on first run and raises it when price makes new highs; when price drops pullback_pct from reference, places market buy, then runs trailing stop.
- **Config CLI (CLI-only)** — `trader config list`, `trader config get KEY`, `trader config set KEY VALUE`, `trader config keys`. Environment-based config is the default (env vars and `.env`); values can be viewed and set via CLI. Secrets (API keys, webhook URLs) are redacted when listing or getting unless `--show-secrets` / `--show-secret` is used. Optional base URL overrides: `ALPACA_PAPER_BASE_URL`, `ALPACA_PROD_BASE_URL`. No MCP tools for config (by design, to avoid exposing secrets to agents).
- **Top market movers** — New `get_top_movers()` MCP tool and app function to fetch today's top gainers and losers from Alpaca's screener API. Supports both stocks and crypto markets with configurable limit. Added to `AlpacaBroker` class, exposed via `trader/app/portfolio.py`, and registered as MCP tool. Useful for strategy discovery workflow to identify active trading opportunities.
- **Autonomous research prompts** — Three new research workflows for systematic market exploration:
  - `research-large-caps.md` — Autonomous research of major large-cap stocks (AAPL, GOOGL, MSFT, NVDA, TSLA, etc.) with systematic strategy testing and documentation
  - `research-sectors.md` — Sector-based equity discovery identifying sector-specific patterns and optimal strategies per sector
  - `explore-opportunities.md` — Autonomous discovery workflow using top movers, sector rotation, and pattern recognition to find new trading opportunities
  - All prompts enable agents to research autonomously, document findings in CONTEXTS.md, and build on past research without user direction
  - Corresponding Cursor commands created for easy access: `/research-large-caps`, `/research-sectors`, `/explore-opportunities`

### Removed
- **Deprecated rules subsystem** — Removed `trader/rules/` (RuleEvaluator and missing models/loader). Strategies are the only evaluation path; rules were unused by CLI/MCP/app.

### Changed
- **Documentation** — PLAN.md now uses `trader/backtest/` (not `backtesting/`) and actual file names (broker.py, store.py). Removed references to missing `docs/` files (cli-mcp-usage, QUICK_START, INSTALLATION_PATHS, agent-guide); README/CONTRIBUTING/CLAUDE/PLAN updated. MCP tool count corrected from 28 to 32 in README, PLAN, CLAUDE, CHANGELOG.
- **Lint** — Ruff: ignore E501 (line length); fixed unused vars/imports and undefined `logger` in `trader/app/orders.py`.
- **Agent guidance (MCP first, CLI for testing)** — Documented in PLAN, CLAUDE.md, CONTRIBUTING, README, and .cursor rules/commands: agents use MCP tools for all operations; run CLI only when testing human-facing output (e.g. `trader status` or `trader --json <cmd>`). CLI stays human-first with opt-in `--json`.

### Fixed
- **Safety checks** — Pending orders in `orders_dir` (e.g. orders.yaml) are now considered when the broker returns no pending orders (e.g. mock or API failure), so buying power and position-size limits correctly reserve for local pending orders. Fixes `test_pending_buys_reduce_buying_power` and `test_pending_buys_count_toward_position_size`.

### Added (MCP Phase 4)
- **MCP contract tests** (`tests/test_mcp_contract.py`) — Validate each MCP tool response: success payloads match expected schema (EngineStatus, IndicatorInfo, etc.) or required keys; error payloads match ErrorResponse shape.
- **CLI–MCP parity tests** (`tests/test_cli_mcp_parity.py`) — Compare `trader <cmd> --json` output with MCP tool JSON for status, indicator list/describe, strategy list, and backtest list; assert same top-level keys and matching values where applicable.

## [0.6.0] - 2026-02-11

### Added
- **CLI + MCP usage (MCP Phase 4)** — Per-feature mapping of CLI commands to MCP tools (engine, portfolio, orders, strategies, backtest, analysis, indicators, optimization, safety, notifications) via `trader --help` and MCP tool list. Documents MCP-only and CLI-only actions.
- **Notification system (Phase 3 Automation)** — Discord and generic webhook channels for alerts. New module `trader/notifications/` (NotificationManager, DiscordChannel, WebhookChannel, formatters). CLI: `trader notify test` and `trader notify send "message"`. Config via env (`DISCORD_WEBHOOK_URL`, `CUSTOM_WEBHOOK_URL`, `NOTIFICATIONS_ENABLED`) and optional `config/notifications.yaml` (see `config/notifications.yaml.example`). App layer: `trader/app/notifications.py` for use by engine or MCP later.
- **Central audit log (MCP Phase 3)** — `trader/audit.py` appends structured JSONL to `logs/audit.log` for sensitive actions from both CLI and MCP. Logged actions: `place_order`, `place_order_blocked`, `cancel_order`, `create_strategy`, `remove_strategy`, `run_backtest`, `stop_engine`. Each record includes timestamp (UTC), source (`cli` or `mcp`), action, details, and optional error. Audit source is set via context (CLI sets at startup; MCP sets per tool call).
- **MCP rate limits and timeouts (Phase 3)** — Long-running MCP tools (`run_backtest`, `run_optimization`) are now subject to configurable rate limits and per-call timeouts. New module `trader/mcp/limits.py`; env vars: `MCP_BACKTEST_TIMEOUT_SECONDS` (default 300), `MCP_OPTIMIZATION_TIMEOUT_SECONDS` (default 600), `MCP_RATE_LIMIT_LONG_RUNNING_PER_MINUTE` (default 10). New error types: `RateLimitError`, `TaskTimeoutError` in `trader/errors.py`. See README Configuration for details.

### Fixed
- **Audit log** — Use `timezone.utc` instead of `datetime.UTC` for compatibility in all Python 3.11+ environments.

## [0.5.0] - 2026-02-11

### Documentation
- Consolidated documentation: merged DEVELOPMENT.md into CONTRIBUTING.md (single place for setup, code style, and how to make changes)
- Merged MCP-PLAN.md into PLAN.md; product phases and MCP + CLI roadmap now live in one file
- README: added Prerequisites (Python, pipx) with Mac and Windows notes; MCP section rewritten so Claude Desktop uses `"command": "trader", "args": ["mcp", "serve"]` with no wrapper script; documented config file locations for macOS and Windows; added Troubleshooting
- CONTRIBUTING: added “What is Poetry,” Mac/Windows prerequisites, MCP-for-development (pipx editable + same Claude config), dual-interface diagram, common issues, release workflow
- Replaced mcp-wrapper.sh with a stub that points users to pipx install and the README
- CLAUDE.md reference list now points to PLAN.md and CONTRIBUTING.md only

## [0.4.0] - 2026-02-10

### Added
- **MCP server with full tool parity** (`trader/mcp/`): MCP-compliant server using the official `mcp` Python SDK with stdio transport, 32 tools covering all CLI features
  - Engine: `get_status`, `stop_engine`
  - Portfolio: `get_balance`, `get_positions`, `get_portfolio`, `get_quote`
  - Orders: `place_order`, `list_orders`, `cancel_order`
  - Strategies: `list_strategies`, `get_strategy`, `create_strategy`, `remove_strategy`, `pause_strategy`, `resume_strategy`, `set_strategy_enabled`
  - Backtests: `run_backtest`, `list_backtests`, `show_backtest`, `compare_backtests`, `delete_backtest`
  - Analysis: `analyze_performance`, `get_trade_history`, `get_today_pnl`
  - Indicators: `list_indicators`, `describe_indicator`
  - Optimization: `run_optimization`
  - Safety: `get_safety_status`
  - `trader mcp serve` CLI command to launch the server
  - 27 tests for server setup, tool registration, tool responses, and CLI integration
- **Shared error hierarchy** (`trader/errors.py`): `AppError` base with typed subclasses (`ValidationError`, `NotFoundError`, `ConfigurationError`, `BrokerError`, `SafetyError`, `EngineError`) used by both CLI and MCP server
- **Pydantic v2 schema layer** (`trader/schemas/`): 11 modules defining typed contracts for all API inputs/outputs — portfolio, orders, strategies, backtests, analysis, optimization, indicators, engine status, common types, and error responses
- **Application service layer** (`trader/app/`): 10 modules providing shared business logic that both CLI and MCP server call — indicators, engine, strategies, portfolio, orders, analysis, backtests, optimization, and data/safety
- **`--json` global CLI flag**: All commands now support `--json` for structured JSON output, enabling machine-readable responses for AI agents
- **59 new tests**: Comprehensive test coverage for MCP server, errors, schemas, and app service layer

### Changed
- **CLI refactored to use app layer**: All Click commands now delegate to `trader/app/` service functions instead of directly calling domain modules. CLI is now a thin presentation adapter.
- Added `pydantic>=2.0.0` and `mcp>=1.0.0` as project dependencies

### Fixed
- **BacktestEngine indentation bug**: Fixed critical bug where `_execute_action` and helper methods were incorrectly indented inside `_align_datetime_to_index` function, causing `AttributeError` when running backtests

### Documentation
- Added `DEVELOPMENT.md` with comprehensive development guide including editable install instructions, MCP server setup, debugging tips, and common issues
- Updated README.md with correct installation instructions for development vs. production
- Updated README.md MCP server configuration with Poetry-based development example and clarifications
- Added `MCP-PLAN.md` with MCP + CLI dual-interface roadmap
- Updated MCP-PLAN.md: Phase 1 complete, switched from FastAPI to official MCP SDK

## [0.3.0] - 2026-02-07

### Added


- **Indicators library**: Built-in SMA, EMA, RSI, MACD, ATR, Bollinger Bands, OBV, and VWAP
  - `trader indicator list` and `trader indicator describe` CLI commands
  - Optional `pandas-ta` integration with pandas fallback calculations
- **Trade analysis module**: CLI and analytics for realized trade performance
  - `trader analyze` command with per-symbol stats and open-lot report
  - FIFO matching to compute win rate, profit factor, avg win/loss, and hold time
- **Strategy optimization**: Grid/random parameter search using backtests
  - `trader optimize` command with objectives and sampling
  - Optimization result persistence under `data/optimizations/`
  - Objective scoring for return, win rate, profit factor, and drawdown
- **Backtest visualization**: Interactive Bokeh charts for price/equity curves and trades
  - `trader backtest run --chart/--show` to render charts immediately
  - `trader backtest show --chart/--show` to chart existing results
  - `trader visualize` command for backtest IDs or JSON files
  - New `trader/visualization/` module with `ChartBuilder`
- **Data provider abstraction**: Pluggable historical data sources with optional Parquet caching
  - `AlpacaDataProvider` for Alpaca API historical data
  - `CSVDataProvider` for local CSV files with normalized OHLCV format
  - `CachedDataProvider` for Parquet-backed caching with TTL
  - Provider factory (`get_data_provider`) and new data config env vars
- **Backtesting system**: Complete backtesting framework for testing strategies on historical data
  - `trader backtest run` - Run backtests with CSV historical data
  - `trader backtest list` - List all saved backtest results
  - `trader backtest show` - Display detailed backtest metrics and trade history
  - `trader backtest compare` - Compare multiple backtests side-by-side
- `trader/backtest/` module with core backtesting infrastructure:
  - `HistoricalBroker` - Simulates order fills based on OHLCV bar data
  - `BacktestEngine` - Sequential bar-by-bar strategy evaluation
  - `BacktestResult` - Performance metrics (return %, win rate, profit factor, max drawdown, Sharpe ratio)
  - CSV data loading with validation
  - JSON-based result persistence
- Realistic order fill simulation:
  - Market orders fill at bar close
  - Limit orders fill at limit price if within bar range
  - Stop orders trigger when bar crosses threshold
  - Trailing stops track high watermark
- Performance metrics: total return, win rate, profit factor, max drawdown, avg win/loss, trade history
- Equity curve tracking throughout backtest
- Support for trailing-stop and bracket strategies in backtesting
- **OCO (One-Cancels-Other) bracket orders**: Full implementation with both take-profit and stop-loss
  - Sequential order placement: take-profit limit order, then stop-loss stop order
  - Automatic cancellation of remaining order when one fills
  - Proper strategy completion after OCO execution
  - Works in both live trading and backtesting environments

### Fixed

- **Total Return calculation bug**: HistoricalBroker now properly stores initial_cash for accurate metrics calculation
- **Bracket strategy phase management**: _evaluate_exiting now delegates to bracket handler for proper OCO logic

### Documentation

- Updated README.md with comprehensive backtesting section
- Added backtesting examples and best practices
- Updated feature list to reflect backtesting availability

## [0.2.0] - 2026-02-07

### Added

- `trader portfolio` command: Full portfolio overview showing account summary, positions, and open orders
- `trader orders` command: View open orders with `--all` flag for complete history
- Enhanced account data: portfolio value, day's P/L, day trade count, PDT status
- Service-based configuration with hardcoded URLs per broker (Alpaca paper/prod)

### Changed

- Simplified configuration: Separate env vars for paper (`ALPACA_API_KEY`) and prod (`ALPACA_PROD_API_KEY`)
- Replaced `--env paper/prod` with simpler `--prod` flag
- Production now uses interactive (Y/n) confirmation instead of `--confirm` flag
- `trader balance` now shows full account summary with day's change and unrealized P/L
- `trader status` now displays service name (alpaca)
- Strategy default quantity changed to 1 (was config-based)
- Strategy entry options simplified: `--limit`/`-L` replaces `--entry-type` and `--entry-price`

### Removed

- Legacy rules system (`trader rules` commands, `trader/rules/` module)
- `trader backtest` command (will be reimplemented for strategies)
- `--confirm` flag (replaced with interactive confirmation)
- `TRADER_ENV`, `BROKER`, `BASE_URL`, `ENABLE_PROD` environment variables
- Separate `.env.paper` and `.env.prod` files (now just `.env`)

## [0.1.1] - 2026-02-05

### Changed

- CLI: `rules add` default behavior refined — `sell` rules now default to trigger on price >= target (ABOVE); `buy` rules continue to default to price <= target (BELOW). Updated CLI and README examples; tests updated.

## [0.1.0] - 2026-01-29

### Added

- Project structure with Poetry package management
- CLI framework using Click with commands: status, balance, positions, rules, start, stop
- Configuration system with environment support (paper/prod)
- Logging infrastructure with file and console output
- Trade audit log capability
- Environment-based configuration (.env.paper, .env.prod)
- Safety controls: production disabled by default, confirmation flags required
- Rich terminal output with formatted tables
- Test suite with pytest

### Dependencies

- click, requests, pandas, python-dotenv, pyyaml, alpaca-py, rich
- Dev: pytest, pytest-cov, ruff, mypy

## [0.0.1] - 2026-01-30

### Added

- Initial Setup
