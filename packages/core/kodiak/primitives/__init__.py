"""Kodiak primitive SDK.

Primitives are typed, versioned descriptors for deterministic financial
actions. Import this package to access the global registry and built-in
primitive definitions.

Usage::

    from kodiak.primitives import list_all, get, register, Primitive

    all_primitives = list_all()
    quote_primitive = get("get_quote")
"""

# Ensure built-ins are registered when this package is imported.
import kodiak.primitives.builtins as _builtins  # noqa: F401, E402
from kodiak.primitives.base import (
    ExecutionMode,
    Primitive,
    PrimitiveRegistry,
    RiskLevel,
    get,
    list_all,
    register,
)

__all__ = [
    "ExecutionMode",
    "Primitive",
    "PrimitiveRegistry",
    "RiskLevel",
    "get",
    "list_all",
    "register",
]
