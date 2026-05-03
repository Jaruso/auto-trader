"""Kodiak primitive SDK.

Primitives are typed, versioned descriptors for deterministic financial
actions. The registry supports multiple versions per primitive and resolves
"latest" to the highest semver non-deprecated version.

Usage::

    from kodiak.primitives import list_all, list_versions, get, register, Primitive

    all_latest = list_all()
    all_quote_versions = list_versions("get_quote")
    quote_v1 = get("get_quote", version="1.0.0")
    quote_latest = get("get_quote")  # equivalent to version="latest"
"""

# Ensure built-ins are registered when this package is imported.
import kodiak.primitives.builtins as _builtins  # noqa: F401
from kodiak.primitives.base import (
    ExecutionMode,
    LatencyClass,
    Primitive,
    PrimitiveRegistry,
    RiskLevel,
    get,
    list_all,
    list_versions,
    register,
)

__all__ = [
    "ExecutionMode",
    "LatencyClass",
    "Primitive",
    "PrimitiveRegistry",
    "RiskLevel",
    "get",
    "list_all",
    "list_versions",
    "register",
]
