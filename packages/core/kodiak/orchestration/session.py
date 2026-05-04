"""Execution session persistence for the Kodiak workflow engine.

Each WorkflowExecutor run produces an ExecutionSession record that captures
the full plan spec, all step outputs, timing, and outcome. Sessions are stored
as individual JSON files under data/sessions/ and are indexed by session_id.

This enables:
- Auditability: every execution is recorded with its inputs and outputs
- Reproducibility: plans can be replayed from stored sessions
- Debugging: full step-level output available after the fact
- AI context minimization: agents can query past results instead of re-running
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExecutionSession:
    """Persistent record of a single workflow execution.

    Captures the plan that was run, all step results, and aggregate
    outcome. The stored plan dict allows sessions to be replayed.
    """

    session_id: str
    plan_name: str
    started_at: str
    completed_at: str
    success: bool
    steps_completed: int
    steps_total: int
    total_duration_ms: float
    plan: dict[str, Any]
    step_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "plan_name": self.plan_name,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "success": self.success,
            "steps_completed": self.steps_completed,
            "steps_total": self.steps_total,
            "total_duration_ms": self.total_duration_ms,
            "plan": self.plan,
            "step_results": self.step_results,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionSession:
        return cls(
            session_id=data["session_id"],
            plan_name=data["plan_name"],
            started_at=data["started_at"],
            completed_at=data["completed_at"],
            success=data["success"],
            steps_completed=data["steps_completed"],
            steps_total=data["steps_total"],
            total_duration_ms=data["total_duration_ms"],
            plan=data.get("plan", {}),
            step_results=data.get("step_results", []),
        )

    @classmethod
    def from_execution(
        cls,
        session_id: str,
        started_at: str,
        completed_at: str,
        plan_dict: dict[str, Any],
        result_dict: dict[str, Any],
    ) -> ExecutionSession:
        return cls(
            session_id=session_id,
            plan_name=result_dict["plan_name"],
            started_at=started_at,
            completed_at=completed_at,
            success=result_dict["success"],
            steps_completed=result_dict["steps_completed"],
            steps_total=result_dict["steps_total"],
            total_duration_ms=result_dict["total_duration_ms"],
            plan=plan_dict,
            step_results=result_dict.get("step_results", []),
        )


class SessionStore:
    """File-backed store for ExecutionSession records.

    Stores one JSON file per session under a configurable directory.
    Lists are sorted by started_at descending (most recent first).
    """

    def __init__(self, sessions_dir: Path | str | None = None) -> None:
        if sessions_dir is None:
            from kodiak.utils.paths import get_data_dir  # noqa: PLC0415

            sessions_dir = get_data_dir() / "sessions"
        self._dir = Path(sessions_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, session: ExecutionSession) -> None:
        """Persist a session to disk."""
        path = self._dir / f"{session.session_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, indent=2)

    def get(self, session_id: str) -> ExecutionSession | None:
        """Return the session for the given ID, or None if not found."""
        path = self._dir / f"{session_id}.json"
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return ExecutionSession.from_dict(json.load(f))

    def list(
        self,
        plan_name: str | None = None,
        limit: int = 50,
    ) -> list[ExecutionSession]:
        """Return sessions ordered by started_at descending.

        Args:
            plan_name: When provided, only return sessions for this plan.
            limit: Maximum number of sessions to return (default 50).
        """
        sessions: list[ExecutionSession] = []
        for path in self._dir.glob("*.json"):
            try:
                with open(path, encoding="utf-8") as f:
                    session = ExecutionSession.from_dict(json.load(f))
                if plan_name is None or session.plan_name == plan_name:
                    sessions.append(session)
            except Exception:  # noqa: BLE001
                continue
        sessions.sort(key=lambda s: s.started_at, reverse=True)
        return sessions[:limit]
