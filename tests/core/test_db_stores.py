"""Tests for the PostgreSQL-backed strategy and order stores.

Tests that require a live database are skipped unless KODIAK_DATABASE_URL is
set. Tests that cover store routing and YAML fallback always run.

To run against a real database:
    KODIAK_DATABASE_URL=postgresql://user:pass@host/db pytest tests/core/test_db_stores.py
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

POSTGRES_AVAILABLE = bool(os.getenv("KODIAK_DATABASE_URL"))
requires_postgres = pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason="KODIAK_DATABASE_URL not set — skipping Postgres store tests",
)


# ---------------------------------------------------------------------------
# Store routing: _use_postgres() flag
# ---------------------------------------------------------------------------


def test_strategy_loader_routes_to_yaml_without_db_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """When KODIAK_DATABASE_URL is unset, loader uses the YAML path."""
    monkeypatch.delenv("KODIAK_DATABASE_URL", raising=False)
    # Reload to clear cached env check
    import importlib

    from kodiak.strategies import loader
    importlib.reload(loader)

    assert not loader._use_postgres()


def test_strategy_loader_routes_to_postgres_with_db_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """When KODIAK_DATABASE_URL is set, _use_postgres() is True."""
    monkeypatch.setenv("KODIAK_DATABASE_URL", "postgresql://fake/testdb")
    import importlib

    from kodiak.strategies import loader
    importlib.reload(loader)

    assert loader._use_postgres()


def test_strategy_loader_falls_back_to_yaml_when_postgres_unreachable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("KODIAK_DATABASE_URL", "postgresql://fake/testdb")

    from kodiak.db import pg_strategy_store
    from kodiak.strategies import loader
    from kodiak.strategies.models import Strategy, StrategyType

    strategy = Strategy(
        symbol="FALLBACK",
        strategy_type=StrategyType.TRAILING_STOP,
        quantity=3,
        trailing_stop_pct=Decimal("5"),
    )
    strategies_file = loader.get_strategies_file(tmp_path)
    strategies_file.write_text(
        yaml.dump({"strategies": [strategy.to_dict()]}, sort_keys=False),
        encoding="utf-8",
    )

    def _boom() -> list[object]:
        raise ConnectionError("postgres offline")

    monkeypatch.setattr(pg_strategy_store, "load_strategies", _boom)

    loaded = loader.load_strategies(config_dir=tmp_path)
    assert [item.symbol for item in loaded] == ["FALLBACK"]


def test_order_store_routes_to_yaml_without_db_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KODIAK_DATABASE_URL", raising=False)
    import importlib

    from kodiak.oms import store
    importlib.reload(store)

    assert not store._use_postgres()


def test_order_store_routes_to_postgres_with_db_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KODIAK_DATABASE_URL", "postgresql://fake/testdb")
    import importlib

    from kodiak.oms import store
    importlib.reload(store)

    assert store._use_postgres()


def test_order_store_falls_back_to_yaml_when_postgres_unreachable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("KODIAK_DATABASE_URL", "postgresql://fake/testdb")

    from kodiak.db import pg_order_store
    from kodiak.models.order import Order, OrderSide, OrderStatus, OrderType
    from kodiak.oms import store

    order = Order(
        id="fallback-order",
        symbol="AAPL",
        side=OrderSide.BUY,
        qty=Decimal("2"),
        order_type=OrderType.MARKET,
        status=OrderStatus.NEW,
    )
    orders_file = store.get_orders_file(tmp_path)
    orders_file.write_text(
        yaml.dump({"orders": [order.to_dict()]}, sort_keys=False),
        encoding="utf-8",
    )

    def _boom() -> list[object]:
        raise ConnectionError("postgres offline")

    monkeypatch.setattr(pg_order_store, "load_orders", _boom)

    loaded = store.load_orders(config_dir=tmp_path)
    assert [item.id for item in loaded] == ["fallback-order"]


# ---------------------------------------------------------------------------
# connection module
# ---------------------------------------------------------------------------


def test_db_available_false_without_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KODIAK_DATABASE_URL", raising=False)
    from kodiak.db.connection import db_available
    assert not db_available()


def test_db_available_true_with_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KODIAK_DATABASE_URL", "postgresql://user:pass@localhost/db")
    from kodiak.db.connection import db_available
    assert db_available()


def test_get_connection_raises_without_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KODIAK_DATABASE_URL", raising=False)
    from kodiak.db.connection import get_connection

    with pytest.raises(RuntimeError, match="KODIAK_DATABASE_URL"):
        with get_connection():
            pass


# ---------------------------------------------------------------------------
# migrations module: DDL is well-formed
# ---------------------------------------------------------------------------


def test_get_ddl_contains_required_tables() -> None:
    from kodiak.db.migrations import get_ddl

    ddl = get_ddl()
    assert "CREATE TABLE IF NOT EXISTS kodiak.strategies" in ddl
    assert "CREATE TABLE IF NOT EXISTS kodiak.orders" in ddl
    assert "CREATE SCHEMA IF NOT EXISTS kodiak" in ddl


def test_get_ddl_contains_expected_strategy_columns() -> None:
    from kodiak.db.migrations import get_ddl

    ddl = get_ddl()
    for col in ("id", "symbol", "strategy_type", "phase", "quantity", "enabled",
                "trailing_stop_pct", "scale_targets", "grid_config", "exit_order_ids",
                "schedule_at", "created_at", "updated_at"):
        assert col in ddl, f"Expected column '{col}' in strategies DDL"


def test_get_ddl_contains_expected_order_columns() -> None:
    from kodiak.db.migrations import get_ddl

    ddl = get_ddl()
    for col in ("id", "symbol", "side", "qty", "order_type", "status",
                "external_id", "created_at", "updated_at"):
        assert col in ddl, f"Expected column '{col}' in orders DDL"


# ---------------------------------------------------------------------------
# Postgres store tests — skipped without live DB
# ---------------------------------------------------------------------------


@requires_postgres
def test_postgres_ensure_schema() -> None:
    """Applying the schema should not raise."""
    from kodiak.db.migrations import ensure_schema
    ensure_schema()  # idempotent — runs twice in case table already exists
    ensure_schema()


@requires_postgres
def test_postgres_strategy_roundtrip() -> None:
    """Save a strategy, fetch it back, verify fields match."""
    from kodiak.db.pg_strategy_store import delete_strategy, get_strategy, save_strategy
    from kodiak.strategies.models import Strategy, StrategyType

    strat = Strategy(
        symbol="TESTPG",
        strategy_type=StrategyType.TRAILING_STOP,
        quantity=5,
        trailing_stop_pct=Decimal("7.5"),
    )

    try:
        save_strategy(strat)
        fetched = get_strategy(strat.id)
        assert fetched is not None
        assert fetched.id == strat.id
        assert fetched.symbol == "TESTPG"
        assert fetched.quantity == 5
        assert fetched.trailing_stop_pct == Decimal("7.5")
    finally:
        delete_strategy(strat.id)


@requires_postgres
def test_postgres_strategy_upsert() -> None:
    """Saving the same strategy twice updates rather than duplicates."""
    from kodiak.db.pg_strategy_store import (
        delete_strategy,
        get_strategy,
        load_strategies,
        save_strategy,
    )
    from kodiak.strategies.models import Strategy, StrategyPhase, StrategyType

    strat = Strategy(
        symbol="UPSERTPG",
        strategy_type=StrategyType.TRAILING_STOP,
        quantity=1,
        trailing_stop_pct=Decimal("5"),
    )

    try:
        save_strategy(strat)
        strat.phase = StrategyPhase.ENTRY_ACTIVE
        strat.quantity = 2
        save_strategy(strat)

        fetched = get_strategy(strat.id)
        assert fetched is not None
        assert fetched.phase == StrategyPhase.ENTRY_ACTIVE
        assert fetched.quantity == 2

        # Should still be only one row for this id
        all_strats = load_strategies()
        matching = [s for s in all_strats if s.id == strat.id]
        assert len(matching) == 1
    finally:
        delete_strategy(strat.id)


@requires_postgres
def test_postgres_strategy_delete() -> None:
    from kodiak.db.pg_strategy_store import delete_strategy, get_strategy, save_strategy
    from kodiak.strategies.models import Strategy, StrategyType

    strat = Strategy(
        symbol="DELPG",
        strategy_type=StrategyType.TRAILING_STOP,
        quantity=1,
        trailing_stop_pct=Decimal("5"),
    )
    save_strategy(strat)
    assert delete_strategy(strat.id) is True
    assert get_strategy(strat.id) is None
    assert delete_strategy(strat.id) is False  # already gone


@requires_postgres
def test_postgres_order_roundtrip() -> None:
    from decimal import Decimal

    from kodiak.db.pg_order_store import load_orders, save_order
    from kodiak.models.order import Order, OrderSide, OrderStatus, OrderType

    order = Order(
        id="test-pg-order-1",
        symbol="TESTPG",
        side=OrderSide.BUY,
        qty=Decimal("10"),
        order_type=OrderType.MARKET,
        status=OrderStatus.NEW,
    )

    save_order(order)
    orders = load_orders()
    ids = [o.id for o in orders]
    assert "test-pg-order-1" in ids

    # Clean up
    from kodiak.db.connection import get_connection
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM kodiak.orders WHERE id = %s", ("test-pg-order-1",))


# ---------------------------------------------------------------------------
# audit context: client_ip
# ---------------------------------------------------------------------------


def test_audit_context_includes_client_ip() -> None:
    """set_audit_context with client_ip is stored and emitted in log records."""
    import json
    import tempfile
    from pathlib import Path

    from kodiak.audit import log_action, set_audit_context

    set_audit_context(
        actor="test@example.com",
        request_id="req-ip-test",
        role="operator",
        source="rest",
        client_ip="10.0.0.1",
    )

    with tempfile.TemporaryDirectory() as tmp:
        log_action("test_action", {"key": "val"}, log_dir=Path(tmp))
        audit_file = Path(tmp) / "audit.log"
        assert audit_file.exists()
        record = json.loads(audit_file.read_text().strip())

    assert record["actor"] == "test@example.com"
    assert record["request_id"] == "req-ip-test"
    assert record["role"] == "operator"
    assert record["client_ip"] == "10.0.0.1"
    assert record["source"] == "rest"
