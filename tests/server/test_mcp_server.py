"""Tests for the MCP server module."""

from __future__ import annotations

import asyncio
import json

from kodiak.mcp.tools import (
    _ALL_TOOLS,
    analyze_performance,
    build_server,
    calculate_position_size,
    describe_indicator,
    export_analysis_report,
    get_balance,
    get_benchmark_history,
    get_fundamentals,
    get_portfolio,
    get_portfolio_analytics,
    get_positions,
    get_quote,
    get_rebalance_plan,
    get_safety_status,
    get_status,
    get_today_pnl,
    get_trade_history,
    list_backtests,
    list_indicators,
    list_orders,
    list_strategies,
    stop_engine,
)

mcp = build_server()

# =============================================================================
# Server Setup
# =============================================================================


class TestMCPServerSetup:
    """Test MCP server instantiation and configuration."""

    def test_server_name(self) -> None:
        """Server should be named 'kodiak'."""
        assert mcp.name == "kodiak"

    def test_all_tools_registered(self) -> None:
        """Every tool in _ALL_TOOLS should be registered."""
        tools = asyncio.run(mcp.list_tools())
        registered_names = {t.name for t in tools}
        expected_names = {fn.__name__ for fn in _ALL_TOOLS}
        assert expected_names == registered_names

    def test_tool_count(self) -> None:
        """Should have expected number of MCP tools registered."""
        tools = asyncio.run(mcp.list_tools())
        assert len(tools) == 47

    def test_all_tools_have_descriptions(self) -> None:
        """Every registered tool should have a non-empty description."""
        tools = asyncio.run(mcp.list_tools())
        for tool in tools:
            assert tool.description, f"Tool {tool.name} has no description"


# =============================================================================
# Engine Tools
# =============================================================================


class TestGetStatusTool:
    """Test the get_status tool handler."""

    def test_returns_valid_json(self) -> None:
        result = get_status()
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_returns_engine_status_fields(self) -> None:
        result = get_status()
        parsed = json.loads(result)
        assert "running" in parsed
        assert "environment" in parsed
        assert "service" in parsed
        assert "base_url" in parsed
        assert "api_key_configured" in parsed

    def test_engine_not_running_by_default(self) -> None:
        result = get_status()
        parsed = json.loads(result)
        assert parsed["running"] is False

    def test_environment_is_paper_by_default(self) -> None:
        result = get_status()
        parsed = json.loads(result)
        assert parsed["environment"] == "PAPER"


class TestStopEngineTool:
    """Test the stop_engine tool handler."""

    def test_returns_error_when_not_running(self) -> None:
        result = stop_engine()
        parsed = json.loads(result)
        assert "error" in parsed or "ENGINE_ERROR" in str(parsed)


# =============================================================================
# Portfolio Tools
# =============================================================================


class TestPortfolioTools:
    """Test portfolio/market data tools return valid JSON."""

    def test_get_balance_returns_json(self) -> None:
        result = get_balance()
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_get_positions_returns_json(self) -> None:
        result = get_positions()
        parsed = json.loads(result)
        # Should be a list (possibly empty) or an error dict
        assert isinstance(parsed, list | dict)

    def test_get_portfolio_returns_json(self) -> None:
        result = get_portfolio()
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_get_portfolio_analytics_returns_json(self) -> None:
        result = get_portfolio_analytics(lookback_days=30, benchmark_symbol="SPY", end_date="2024-12-31")
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_calculate_position_size_returns_json(self) -> None:
        result = calculate_position_size(symbol="AAPL", method="target_weight", target_weight_pct=10)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_get_rebalance_plan_returns_json(self) -> None:
        result = get_rebalance_plan(target_weights={"AAPL": 10, "MSFT": 10})
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_get_quote_returns_json(self) -> None:
        result = get_quote("AAPL")
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_get_fundamentals_returns_json(self) -> None:
        result = get_fundamentals("AAPL")
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_get_benchmark_history_returns_json(self) -> None:
        result = get_benchmark_history("SPY", start="2024-01-01", end="2024-01-31")
        parsed = json.loads(result)
        assert isinstance(parsed, dict)


# =============================================================================
# Order Tools
# =============================================================================


class TestOrderTools:
    """Test order tools return valid JSON."""

    def test_list_orders_returns_json(self) -> None:
        result = list_orders()
        parsed = json.loads(result)
        assert isinstance(parsed, list | dict)

    def test_list_orders_show_all_returns_json(self) -> None:
        result = list_orders(show_all=True)
        parsed = json.loads(result)
        assert isinstance(parsed, list | dict)


# =============================================================================
# Strategy Tools
# =============================================================================


class TestStrategyTools:
    """Test strategy tools."""

    def test_list_strategies_returns_json(self) -> None:
        result = list_strategies()
        parsed = json.loads(result)
        assert isinstance(parsed, dict)
        assert "strategies" in parsed
        assert "count" in parsed

    def test_list_strategies_count_matches(self) -> None:
        result = list_strategies()
        parsed = json.loads(result)
        assert parsed["count"] == len(parsed["strategies"])


# =============================================================================
# Backtest Tools
# =============================================================================


class TestBacktestTools:
    """Test backtest tools return valid JSON."""

    def test_list_backtests_returns_json(self) -> None:
        result = list_backtests()
        parsed = json.loads(result)
        assert isinstance(parsed, list)


# =============================================================================
# Analysis Tools
# =============================================================================


class TestAnalysisTools:
    """Test analysis tools return valid JSON."""

    def test_analyze_performance_returns_json(self) -> None:
        result = analyze_performance()
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_get_trade_history_returns_json(self) -> None:
        result = get_trade_history()
        parsed = json.loads(result)
        assert isinstance(parsed, list)

    def test_get_today_pnl_returns_json(self) -> None:
        result = get_today_pnl()
        parsed = json.loads(result)
        assert "today_pnl" in parsed

    def test_export_analysis_report_returns_json(self) -> None:
        result = export_analysis_report(days=1, include_portfolio=False)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)
        assert parsed["format"] == "json"
        assert "report" in parsed


# =============================================================================
# Indicator Tools
# =============================================================================


class TestIndicatorTools:
    """Test indicator tools."""

    def test_list_indicators_returns_json(self) -> None:
        result = list_indicators()
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) > 0

    def test_describe_indicator_returns_json(self) -> None:
        result = describe_indicator("sma")
        parsed = json.loads(result)
        assert isinstance(parsed, dict)
        assert parsed["name"] == "sma"

    def test_describe_indicator_not_found(self) -> None:
        result = describe_indicator("NONEXISTENT_XYZ")
        parsed = json.loads(result)
        assert "error" in parsed


# =============================================================================
# Safety Tools
# =============================================================================


class TestSafetyTools:
    """Test safety tools return valid JSON."""

    def test_get_safety_status_returns_json(self) -> None:
        result = get_safety_status()
        parsed = json.loads(result)
        assert isinstance(parsed, dict)


# =============================================================================
# CLI Command
# =============================================================================


class TestMCPCLICommand:
    """Test the CLI 'mcp' command is registered."""

    def test_mcp_command_exists(self) -> None:
        from click.testing import CliRunner
        from kodiak_cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["mcp", "--help"])
        assert result.exit_code == 0
        assert "stdio" in result.output.lower()
