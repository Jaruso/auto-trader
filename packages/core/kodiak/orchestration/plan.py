"""Workflow plan types for the Kodiak orchestration engine.

A WorkflowPlan is a named, ordered list of WorkflowSteps. Each step
references a registered primitive by name and carries the inputs to pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowStep:
    """A single primitive invocation within a workflow plan.

    Attributes:
        primitive: Name of a registered Kodiak primitive (e.g. "get_quote").
        inputs: Keyword arguments forwarded to the primitive executor.
        version: Semver string or "latest" for version resolution.
        retry_count: Maximum extra attempts on transient failure (0 = no retry).
        depends_on: Step indices this step requires to complete first.
            Reserved for future DAG execution; sequential executor ignores it.
    """

    primitive: str
    inputs: dict[str, Any] = field(default_factory=dict)
    version: str = "latest"
    retry_count: int = 0
    depends_on: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primitive": self.primitive,
            "inputs": self.inputs,
            "version": self.version,
            "retry_count": self.retry_count,
            "depends_on": self.depends_on,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        return cls(
            primitive=data["primitive"],
            inputs=data.get("inputs", {}),
            version=data.get("version", "latest"),
            retry_count=data.get("retry_count", 0),
            depends_on=data.get("depends_on", []),
        )


@dataclass
class WorkflowPlan:
    """A named, ordered sequence of primitive invocations.

    Attributes:
        name: Human-readable identifier for this workflow.
        steps: Ordered list of steps to execute.
        deterministic: When True, all primitives are validated against the
            registry before execution begins. Unknown primitives abort the run.
    """

    name: str
    steps: list[WorkflowStep]
    deterministic: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "steps": [s.to_dict() for s in self.steps],
            "deterministic": self.deterministic,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowPlan:
        return cls(
            name=data["name"],
            steps=[WorkflowStep.from_dict(s) for s in data.get("steps", [])],
            deterministic=data.get("deterministic", True),
        )
