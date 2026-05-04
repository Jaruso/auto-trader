"""Execution session REST API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from kodiak.app.sessions import get_session_app, list_sessions_app, replay_session_app
from kodiak.errors import NotFoundError

from kodiak_server.rest.context import RequestContext, get_request_context
from kodiak_server.rest.response import ok

router = APIRouter(prefix="/sessions")


@router.get("/")
def list_sessions(
    plan_name: str | None = Query(None, description="Filter by workflow plan name"),
    limit: int = Query(50, ge=1, le=500),
    ctx: RequestContext = Depends(get_request_context),
) -> dict[str, Any]:
    """List execution sessions, most recent first.

    Sessions are created automatically whenever a workflow is run through
    the run or run-spec endpoints. Each session records the full plan spec
    and all step outputs, enabling audit and replay.
    """
    sessions = list_sessions_app(plan_name=plan_name, limit=limit)
    return ok(sessions, ctx.request_id)


@router.get("/{session_id}")
def get_session(
    session_id: str,
    ctx: RequestContext = Depends(get_request_context),
) -> dict[str, Any]:
    """Get a single execution session by ID.

    Returns the full session record including the stored plan spec and
    per-step outputs (primitive name, version, inputs, output, timing).
    """
    session = get_session_app(session_id)
    if session is None:
        raise NotFoundError(f"Session '{session_id}' not found.")
    return ok(session, ctx.request_id)


@router.post("/{session_id}/replay")
def replay_session(
    session_id: str,
    ctx: RequestContext = Depends(get_request_context),
) -> dict[str, Any]:
    """Re-execute a stored session's workflow plan.

    Retrieves the saved plan from the session and runs it again through
    the workflow executor. The new execution is persisted as a separate
    session with its own session_id and timestamps.
    """
    outcome = replay_session_app(session_id)
    if outcome is None:
        raise NotFoundError(f"Session '{session_id}' not found.")
    result, new_session = outcome
    return ok(
        {
            "replayed_from": session_id,
            "session_id": new_session.session_id,
            "result": result.to_dict(),
        },
        ctx.request_id,
    )
