"""Primitive SDK base types and registry.

A Primitive is a typed, versioned descriptor for a deterministic financial
action. It carries metadata (risk level, permissions, execution mode) that
lets AI agents select the right tool and operators audit what ran.

The registry stores all registered versions of each primitive and resolves
"latest" to the highest semver non-deprecated version.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ExecutionMode(str, Enum):
    SYNC = "sync"
    DEFERRED = "deferred"


class LatencyClass(str, Enum):
    REALTIME = "realtime"    # sub-second
    FAST = "fast"            # < 5 s
    BATCH = "batch"          # seconds to minutes


def _semver_key(version_str: str) -> tuple[int, ...]:
    """Parse a semver string into a comparable tuple. Non-semver maps to (0,)."""
    try:
        return tuple(int(x) for x in version_str.split("."))
    except ValueError:
        return (0,)


@dataclass(frozen=True)
class Primitive:
    """Descriptor for a deterministic financial action primitive.

    Attributes:
        name: Unique snake_case identifier (e.g. "get_quote").
        version: Semver string (e.g. "1.0.0").
        description: Human/agent-readable description.
        input_schema: JSON Schema dict describing accepted parameters.
        output_schema: JSON Schema dict describing the returned payload.
        permissions: Scopes required to invoke this primitive.
        risk_level: Indicates side-effect severity for agent routing.
        execution_mode: Whether the call blocks until complete.
        tags: Optional free-form labels for grouping.
        deprecated: When True, prefer a newer version of this primitive.
        deprecation_message: Optional migration hint shown alongside deprecated primitives.
        latency_class: Expected latency profile for agent orchestration planning.
    """

    name: str
    version: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permissions: list[str]
    risk_level: RiskLevel
    execution_mode: ExecutionMode
    tags: list[str] = field(default_factory=list)
    deprecated: bool = False
    deprecation_message: str | None = None
    latency_class: LatencyClass | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "permissions": self.permissions,
            "risk_level": self.risk_level.value,
            "execution_mode": self.execution_mode.value,
            "tags": self.tags,
            "deprecated": self.deprecated,
        }
        if self.deprecation_message:
            d["deprecation_message"] = self.deprecation_message
        if self.latency_class is not None:
            d["latency_class"] = self.latency_class.value
        return d


class PrimitiveRegistry:
    """In-process registry of Primitive descriptors.

    Stores all registered versions of each primitive. Version resolution:
    - "latest" → highest semver among non-deprecated versions; falls back to
      deprecated if every version is deprecated.
    - Pinned → exact match on the version string (e.g. "1.0.0").
    """

    def __init__(self) -> None:
        # name → {version_str → Primitive}
        self._store: dict[str, dict[str, Primitive]] = {}

    def register(self, primitive: Primitive) -> None:
        if primitive.name not in self._store:
            self._store[primitive.name] = {}
        self._store[primitive.name][primitive.version] = primitive

    def get(self, name: str, version: str = "latest") -> Primitive | None:
        versions = self._store.get(name)
        if not versions:
            return None
        if version == "latest":
            return self._resolve_latest(versions)
        return versions.get(version)

    def _resolve_latest(self, versions: dict[str, Primitive]) -> Primitive:
        non_deprecated = {v: p for v, p in versions.items() if not p.deprecated}
        pool = non_deprecated if non_deprecated else versions
        best = max(pool, key=_semver_key)
        return pool[best]

    def list(self) -> list[Primitive]:
        """Return the latest version of each registered primitive, sorted by name."""
        result = [self._resolve_latest(versions) for versions in self._store.values()]
        return sorted(result, key=lambda p: p.name)

    def list_versions(self, name: str) -> list[Primitive]:
        """Return all registered versions of a primitive, newest first."""
        versions = self._store.get(name)
        if not versions:
            return []
        return sorted(versions.values(), key=lambda p: _semver_key(p.version), reverse=True)

    def __len__(self) -> int:
        return len(self._store)


# Module-level singleton
_registry = PrimitiveRegistry()


def register(primitive: Primitive) -> None:
    """Register a primitive version in the global registry."""
    _registry.register(primitive)


def get(name: str, version: str = "latest") -> Primitive | None:
    """Look up a primitive by name and optional version (default: latest)."""
    return _registry.get(name, version)


def list_all() -> list[Primitive]:
    """Return the latest version of all registered primitives, sorted by name."""
    return _registry.list()


def list_versions(name: str) -> list[Primitive]:
    """Return all registered versions of a named primitive, newest first."""
    return _registry.list_versions(name)
