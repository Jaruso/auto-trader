"""Regression tests for degraded-mode analytics and summary behavior."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from kodiak.app.backtests import list_backtests_app
from kodiak.app.portfolio import _load_portfolio_history
from kodiak.backtest.results import BacktestResult
from kodiak.backtest.store import save_backtest
from kodiak.utils.config import (
    Config,
    DataCacheConfig,
    DataConfig,
    Environment,
    Service,
    StrategyDefaults,
)


def _config(tmp_path: Path) -> Config:
    return Config(
        env=Environment.PAPER,
        service=Service.ALPACA,
        alpaca_api_key="key",
        alpaca_secret_key="secret",
        base_url="https://paper-api.alpaca.markets",
        data_dir=tmp_path,
        log_dir=tmp_path / "logs",
        strategy_defaults=StrategyDefaults(),
        data=DataConfig(
            source="csv",
            csv_dir=tmp_path / "historical",
            alpaca_feed=None,
            cache=DataCacheConfig(
                enabled=True,
                backend="parquet",
                directory=tmp_path / "cache",
                ttl_minutes=60,
            ),
        ),
    )


def test_portfolio_history_falls_back_to_alpaca(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    calls: list[str] = []

    def fake_load_data_for_backtest(*, data_source: str, **_: object) -> dict[str, object]:
        calls.append(data_source)
        if data_source == "csv":
            raise FileNotFoundError("csv missing")
        return {"AAPL": object(), "SPY": object()}

    monkeypatch.setattr("kodiak.app.portfolio.load_data_for_backtest", fake_load_data_for_backtest)

    history, selected_source, attempts = _load_portfolio_history(
        config=config,
        symbols=["AAPL", "SPY"],
        start_date=datetime(2026, 1, 1),
        end_date=datetime(2026, 3, 31),
    )

    assert selected_source == "alpaca"
    assert calls == ["csv", "alpaca"]
    assert history.keys() == {"AAPL", "SPY"}
    assert attempts == [{"source": "csv", "reason": "csv missing"}]


def test_list_backtests_marks_duplicates_and_open_positions(tmp_path: Path) -> None:
    shared_config = {
        "symbol": "AAPL",
        "strategy_type": "trailing_stop",
        "quantity": 10,
        "trailing_stop_pct": "5.0",
    }
    older = BacktestResult(
        id="older123",
        strategy_type="trailing_stop",
        symbol="AAPL",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 31),
        created_at=datetime(2026, 2, 1, 12, 0, 0),
        strategy_config=shared_config,
        initial_capital=Decimal("100000"),
        total_return=Decimal("50"),
        total_return_pct=Decimal("0.05"),
        win_rate=Decimal("100"),
        profit_factor=Decimal("1.5"),
        max_drawdown=Decimal("10"),
        max_drawdown_pct=Decimal("0.01"),
        total_trades=1,
        winning_trades=1,
        losing_trades=0,
        trades=[
            {"side": "buy", "qty": "10"},
            {"side": "sell", "qty": "10"},
        ],
    )
    newer = BacktestResult(
        id="newer123",
        strategy_type="trailing_stop",
        symbol="AAPL",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 31),
        created_at=datetime(2026, 2, 2, 12, 0, 0),
        strategy_config=shared_config,
        initial_capital=Decimal("100000"),
        total_return=Decimal("75"),
        total_return_pct=Decimal("0.075"),
        win_rate=Decimal("0"),
        profit_factor=Decimal("0"),
        max_drawdown=Decimal("15"),
        max_drawdown_pct=Decimal("0.015"),
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        trades=[{"side": "buy", "qty": "10"}],
    )

    save_backtest(older, data_dir=tmp_path)
    save_backtest(newer, data_dir=tmp_path)

    summaries = list_backtests_app(data_dir=str(tmp_path))

    assert [summary.id for summary in summaries] == ["newer123", "older123"]
    assert summaries[0].duplicate_group_size == 2
    assert summaries[0].duplicate_rank == 1
    assert summaries[0].position_state == "open"
    assert summaries[1].duplicate_group_size == 2
    assert summaries[1].duplicate_rank == 2
    assert summaries[1].position_state == "flat"
