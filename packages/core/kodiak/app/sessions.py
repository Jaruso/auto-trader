"""Application service layer for execution session management.

All workflow executions that go through the app layer are automatically
persisted to the session store. Sessions can then be queried and replayed
by session ID.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kodiak.orchestration.plan import WorkflowPlan
from kodiak.orchestration.result import WorkflowResult
from kodiak.orchestration.session import ExecutionSession, SessionStore


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def get_session_store(sessions_dir: Path | str | None = None) -> SessionStore:
    """Return the default SessionStore, creating it if needed."""
    if sessions_dir is None:
        from kodiak.utils.paths import get_data_dir  # noqa: PLC0415

        sessions_dir = get_data_dir() / "sessions"
    return SessionStore(sessions_dir)


def run_and_save(
    plan: WorkflowPlan,
    sessions_dir: Path | str | None = None,
) -> tuple[WorkflowResult, ExecutionSession]:
    """Execute a workflow plan and persist the session.

    Args:
        plan: Compiled workflow plan to execute.
        sessions_dir: Override the sessions storage directory.

    Returns:
        A tuple of (WorkflowResult, ExecutionSession). The session is
        already saved to disk when this function returns.
    """
    from kodiak.orchestration.executor import WorkflowExecutor  # noqa: PLC0415

    session_id = str(uuid.uuid4())
    started_at = _now_iso()

    result = WorkflowExecutor().execute(plan)

    completed_at = _now_iso()
    session = ExecutionSession.from_execution(
        session_id=session_id,
        started_at=started_at,
        completed_at=completed_at,
        plan_dict=plan.to_dict(),
        result_dict=result.to_dict(),
    )

    store = get_session_store(sessions_dir)
    store.save(session)

    return result, session


def list_sessions_app(
    plan_name: str | None = None,
    limit: int = 50,
    sessions_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    """List execution sessions, most recent first."""
    store = get_session_store(sessions_dir)
    return [s.to_dict() for s in store.list(plan_name=plan_name, limit=limit)]


def get_session_app(
    session_id: str,
    sessions_dir: Path | str | None = None,
) -> dict[str, Any] | None:
    """Return a session by ID, or None if not found."""
    store = get_session_store(sessions_dir)
    session = store.get(session_id)
    return session.to_dict() if session is not None else None


def replay_session_app(
    session_id: str,
    sessions_dir: Path | str | None = None,
) -> tuple[WorkflowResult, ExecutionSession] | None:
    """Replay a stored session by re-executing its saved plan.

    Returns None if the session is not found.
    """
    store = get_session_store(sessions_dir)
    session = store.get(session_id)
    if session is None:
        return None
    plan = WorkflowPlan.from_dict(session.plan)
    return run_and_save(plan, sessions_dir=sessions_dir)
