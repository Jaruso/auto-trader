"""Order persistence for the OMS.

Routes to the PostgreSQL store when KODIAK_DATABASE_URL is configured,
otherwise falls back to YAML (config/orders.yaml) for local dev and CI.
If PostgreSQL is configured but unavailable, Kodiak degrades back to YAML so
inspection and local state recovery remain available.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import yaml
from kodiak.models.order import Order
from kodiak.utils.logging import get_logger

_LOGGER = get_logger("kodiak.oms.store")
_T = TypeVar("_T")


def _use_postgres() -> bool:
    """True when KODIAK_DATABASE_URL is set — use the Postgres store."""
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
            "PostgreSQL order store unavailable during %s; falling back to YAML: %s",
            operation,
            exc,
        )
        return yaml_operation()


def get_orders_file(config_dir: Path | None = None) -> Path:
    if config_dir is None:
        from kodiak.utils.paths import get_config_dir
        config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "orders.yaml"


def _save_orders_yaml(orders: list[Order], config_dir: Path | None = None) -> None:
    path = get_orders_file(config_dir)
    data = {"orders": [o.to_dict() for o in orders]}
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def save_orders(orders: list[Order], config_dir: Path | None = None) -> None:
    """Batch save orders (Postgres if configured, else YAML)."""
    return _run_with_postgres_fallback(
        "save_orders",
        lambda: __import__("kodiak.db.pg_order_store", fromlist=["save_orders"]).save_orders(orders),
        lambda: _save_orders_yaml(orders, config_dir),
    )


def _load_orders_yaml(config_dir: Path | None = None) -> list[Order]:
    path = get_orders_file(config_dir)
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    items = data.get("orders", [])
    return [Order.from_dict(i) for i in items]


def load_orders(config_dir: Path | None = None) -> list[Order]:
    """Load orders (Postgres if configured, else YAML)."""
    return _run_with_postgres_fallback(
        "load_orders",
        lambda: __import__("kodiak.db.pg_order_store", fromlist=["load_orders"]).load_orders(),
        lambda: _load_orders_yaml(config_dir),
    )


def _to_local_order(order_obj: object) -> Order:
    """Convert a broker.Order-like object or local Order dict to local `Order` model."""
    # Import local enums
    from kodiak.models.order import Order as LocalOrder
    from kodiak.models.order import OrderSide as LocalSide
    from kodiak.models.order import OrderStatus as LocalStatus
    from kodiak.models.order import OrderType as LocalType

    # Extract fields with fallbacks
    oid = getattr(order_obj, "id", getattr(order_obj, "order_id", ""))
    symbol = getattr(order_obj, "symbol")
    qty = getattr(order_obj, "qty")
    # Side may be enum or string
    side_raw = getattr(order_obj, "side")
    try:
        side = LocalSide(side_raw.value) if hasattr(side_raw, "value") else LocalSide(side_raw)
    except Exception:
        side = LocalSide.BUY

    ot_raw = getattr(order_obj, "order_type", getattr(order_obj, "orderType", None))
    try:
        order_type = LocalType(ot_raw.value) if hasattr(ot_raw, "value") else LocalType(ot_raw)
    except Exception:
        order_type = LocalType.MARKET

    limit_price = getattr(order_obj, "limit_price", None)
    external_id = getattr(order_obj, "external_id", None)

    status_raw = getattr(order_obj, "status", None)
    try:
        status = LocalStatus(status_raw.value) if hasattr(status_raw, "value") else LocalStatus(status_raw)
    except Exception:
        status = LocalStatus.NEW

    return LocalOrder(
        id=oid or "",
        symbol=symbol,
        side=side,
        qty=qty,
        order_type=order_type,
        limit_price=limit_price,
        external_id=external_id,
        status=status,
    )


def save_order(order_obj: object, config_dir: Path | None = None) -> None:
    """Save or update a single order (Postgres if configured, else YAML).

    Accepts either a local `Order` instance or a broker-like Order object.
    """
    def _save_yaml() -> None:
        orders = _load_orders_yaml(config_dir)
        local = order_obj if isinstance(order_obj, Order) else _to_local_order(order_obj)

        # Replace existing by id if found
        replaced = False
        for i, o in enumerate(orders):
            # Replace when IDs match, or when external IDs match (broker vs local mapping)
            if (
                (o.id and local.id and o.id == local.id)
                or (o.external_id and local.external_id and o.external_id == local.external_id)
                or (o.external_id and local.id and o.external_id == local.id)
                or (o.id and local.external_id and o.id == local.external_id)
            ):
                orders[i] = local
                replaced = True
                break

        if not replaced:
            orders.append(local)

        _save_orders_yaml(orders, config_dir)

    return _run_with_postgres_fallback(
        "save_order",
        lambda: __import__("kodiak.db.pg_order_store", fromlist=["save_order"]).save_order(order_obj),
        _save_yaml,
    )
