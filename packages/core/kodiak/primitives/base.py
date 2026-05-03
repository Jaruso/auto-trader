"""Primitive SDK base types and registry.

A Primitive is a typed, versioned descriptor for a deterministic financial
action. It carries metadata (risk level, permissions, execution mode) that
lets AI agents select the right tool and operators audit what ran.

The implementation of each primitive lives in the existing app/MCP/REST
layer; the primitive is the contract that describes it.
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "permissions": self.permissions,
            "risk_level": self.risk_level.value,
            "execution_mode": self.execution_mode.value,
            "tags": self.tags,
        }


class PrimitiveRegistry:
    """In-process registry of Primitive descriptors."""

    def __init__(self) -> None:
        self._primitives: dict[str, Primitive] = {}

    def register(self, primitive: Primitive) -> None:
        self._primitives[primitive.name] = primitive

    def get(self, name: str) -> Primitive | None:
        return self._primitives.get(name)

    def list(self) -> list[Primitive]:
        return sorted(self._primitives.values(), key=lambda p: p.name)

    def __len__(self) -> int:
        return len(self._primitives)


# Module-level singleton
_registry = PrimitiveRegistry()


def register(primitive: Primitive) -> None:
    """Register a primitive in the global registry."""
    _registry.register(primitive)


def get(name: str) -> Primitive | None:
    """Look up a primitive by name."""
    return _registry.get(name)


def list_all() -> list[Primitive]:
    """Return all registered primitives, sorted by name."""
    return _registry.list()
