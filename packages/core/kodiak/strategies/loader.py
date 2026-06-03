"""Strategy loading and persistence.

Routes to the PostgreSQL store when KODIAK_DATABASE_URL is configured,
otherwise falls back to YAML (config/strategies.yaml) for local dev and CI.
If PostgreSQL is configured but unavailable, Kodiak degrades back to YAML so
read-only inspection and local operation remain usable.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TypeVar

import yaml

from kodiak.strategies.models import Strategy
from kodiak.utils.logging import get_logger

_LOGGER = get_logger("kodiak.strategies.loader")
_T = TypeVar("_T")


def _use_postgres() -> bool:
    """True when KODIAK_DATABASE_URL is set — use the Postgres store."""
    import os
    return bool(os.getenv("KODIAK_DATABASE_URL"))


def _run_with_postgres_fallback(
    operation: str,
    pg_operation: Callable[[], _T],
    yaml_operation: Callable[[], _T],
) -> _T:
    if not _use_postgres():
        return yaml_operation()

    try:
        return pg_operation()
    except Exception as exc:
        _LOGGER.warning(
            "PostgreSQL strategy store unavailable during %s; falling back to YAML: %s",
            operation,
            exc,
        )
        return yaml_operation()


def get_strategies_file(config_dir: Path | None = None) -> Path:
    """Get path to strategies file."""
    if config_dir is None:
        from kodiak.utils.paths import get_config_dir
        config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "strategies.yaml"


def _load_strategies_yaml(config_dir: Path | None = None) -> list[Strategy]:
    strategies_file = get_strategies_file(config_dir)
    if not strategies_file.exists():
        return []
    with open(strategies_file) as f:
        data = yaml.safe_load(f)
    if not data or "strategies" not in data:
        return []
    return [Strategy.from_dict(s) for s in data["strategies"]]


def load_strategies(config_dir: Path | None = None) -> list[Strategy]:
    """Load all strategies (Postgres if configured, else YAML)."""
    return _run_with_postgres_fallback(
        "load_strategies",
        lambda: __import__("kodiak.db.pg_strategy_store", fromlist=["load_strategies"]).load_strategies(),
        lambda: _load_strategies_yaml(config_dir),
    )


def _save_strategies_yaml(strategies: list[Strategy], config_dir: Path | None = None) -> None:
    strategies_file = get_strategies_file(config_dir)
    data = {"strategies": [s.to_dict() for s in strategies]}
    with open(strategies_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def save_strategies(strategies: list[Strategy], config_dir: Path | None = None) -> None:
    """Batch save strategies (Postgres if configured, else YAML)."""
    return _run_with_postgres_fallback(
        "save_strategies",
        lambda: __import__("kodiak.db.pg_strategy_store", fromlist=["save_strategies"]).save_strategies(strategies),
        lambda: _save_strategies_yaml(strategies, config_dir),
    )


def _save_strategy_yaml(strategy: Strategy, config_dir: Path | None = None) -> None:
    strategies = _load_strategies_yaml(config_dir)
    existing_idx = None
    for i, s in enumerate(strategies):
        if s.id == strategy.id:
            existing_idx = i
            break
    strategy.updated_at = datetime.now()
    if existing_idx is not None:
        strategies[existing_idx] = strategy
    else:
        strategies.append(strategy)
    _save_strategies_yaml(strategies, config_dir)


def save_strategy(strategy: Strategy, config_dir: Path | None = None) -> None:
    """Add or update a single strategy (Postgres if configured, else YAML)."""
    return _run_with_postgres_fallback(
        "save_strategy",
        lambda: __import__("kodiak.db.pg_strategy_store", fromlist=["save_strategy"]).save_strategy(strategy),
        lambda: _save_strategy_yaml(strategy, config_dir),
    )


def _delete_strategy_yaml(strategy_id: str, config_dir: Path | None = None) -> bool:
    strategies = _load_strategies_yaml(config_dir)
    original_count = len(strategies)
    strategies = [s for s in strategies if s.id != strategy_id]
    if len(strategies) == original_count:
        return False
    _save_strategies_yaml(strategies, config_dir)
    return True


def delete_strategy(strategy_id: str, config_dir: Path | None = None) -> bool:
    """Delete a strategy by ID. Returns True if deleted."""
    return _run_with_postgres_fallback(
        "delete_strategy",
        lambda: __import__("kodiak.db.pg_strategy_store", fromlist=["delete_strategy"]).delete_strategy(strategy_id),
        lambda: _delete_strategy_yaml(strategy_id, config_dir),
    )


def _get_strategy_yaml(strategy_id: str, config_dir: Path | None = None) -> Strategy | None:
    strategies = _load_strategies_yaml(config_dir)
    for s in strategies:
        if s.id == strategy_id:
            return s
    return None


def get_strategy(strategy_id: str, config_dir: Path | None = None) -> Strategy | None:
    """Get a strategy by ID, or None if not found."""
    return _run_with_postgres_fallback(
        "get_strategy",
        lambda: __import__("kodiak.db.pg_strategy_store", fromlist=["get_strategy"]).get_strategy(strategy_id),
        lambda: _get_strategy_yaml(strategy_id, config_dir),
    )


def _enable_strategy_yaml(
    strategy_id: str,
    enabled: bool = True,
    config_dir: Path | None = None,
) -> bool:
    strategy = _get_strategy_yaml(strategy_id, config_dir)
    if strategy is None:
        return False
    strategy.enabled = enabled
    _save_strategy_yaml(strategy, config_dir)
    return True


def enable_strategy(strategy_id: str, enabled: bool = True, config_dir: Path | None = None) -> bool:
    """Enable or disable a strategy. Returns True if found and updated."""
    return _run_with_postgres_fallback(
        "enable_strategy",
        lambda: __import__("kodiak.db.pg_strategy_store", fromlist=["enable_strategy"]).enable_strategy(
            strategy_id,
            enabled,
        ),
        lambda: _enable_strategy_yaml(strategy_id, enabled, config_dir),
    )


def _get_active_strategies_yaml(config_dir: Path | None = None) -> list[Strategy]:
    strategies = _load_strategies_yaml(config_dir)
    now = datetime.now()
    active = []
    for s in strategies:
        if not s.enabled:
            continue
        if s.schedule_enabled and s.schedule_at and s.schedule_at > now:
            continue
        if not s.is_active():
            continue
        active.append(s)
    return active


def get_active_strategies(config_dir: Path | None = None) -> list[Strategy]:
    """Get all active (non-terminal, enabled, schedule-ready) strategies."""
    return _run_with_postgres_fallback(
        "get_active_strategies",
        lambda: __import__("kodiak.db.pg_strategy_store", fromlist=["get_active_strategies"]).get_active_strategies(),
        lambda: _get_active_strategies_yaml(config_dir),
    )
