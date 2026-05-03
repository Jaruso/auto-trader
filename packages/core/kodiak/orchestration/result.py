"""Workflow execution result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepResult:
    """Execution record for a single workflow step.

    Captures what was planned (primitive name, requested inputs) alongside
    what actually happened (resolved version, output, timing, retries).
    """

    step_index: int
    primitive: str
    version_resolved: str
    planned_inputs: dict[str, Any]
    output: Any
    success: bool
    error: str | None
    attempts: int
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "primitive": self.primitive,
            "version_resolved": self.version_resolved,
            "planned_inputs": self.planned_inputs,
            "output": self.output,
            "success": self.success,
            "error": self.error,
            "attempts": self.attempts,
            "duration_ms": self.duration_ms,
        }


@dataclass
class WorkflowResult:
    """Aggregate result of executing a WorkflowPlan."""

    plan_name: str
    success: bool
    steps_completed: int
    steps_total: int
    step_results: list[StepResult] = field(default_factory=list)
    total_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_name": self.plan_name,
            "success": self.success,
            "steps_completed": self.steps_completed,
            "steps_total": self.steps_total,
            "step_results": [r.to_dict() for r in self.step_results],
            "total_duration_ms": self.total_duration_ms,
        }
