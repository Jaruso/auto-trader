"""Market-signal REST API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from kodiak.app.signals import (
    get_market_signal_overview,
    list_market_signal_alerts,
    list_market_signal_sources,
    poll_market_signals,
)
from pydantic import BaseModel

from kodiak_server.rest.context import RequestContext, get_request_context
from kodiak_server.rest.response import ok

router = APIRouter(prefix="/signals")


@router.get("/overview")
def overview(ctx: RequestContext = Depends(get_request_context)) -> dict[str, Any]:
    """Summarize signal-monitor state and recent alert volume."""
    return ok(get_market_signal_overview(), ctx.request_id)


@router.get("/alerts")
def alerts(
    limit: int = Query(20, ge=1, le=200),
    bucket: str | None = Query(None),
    ctx: RequestContext = Depends(get_request_context),
) -> dict[str, Any]:
    """List recent source-driven alerts."""
    return ok(list_market_signal_alerts(limit=limit, bucket=bucket), ctx.request_id)


@router.get("/sources")
def sources(ctx: RequestContext = Depends(get_request_context)) -> dict[str, Any]:
    """List configured sources and runtime status."""
    return ok(list_market_signal_sources(), ctx.request_id)


class PollSignalsRequest(BaseModel):
    source_id: str | None = None


@router.post("/poll")
def poll(
    req: PollSignalsRequest,
    ctx: RequestContext = Depends(get_request_context),
) -> dict[str, Any]:
    """Trigger an immediate polling pass."""
    return ok(poll_market_signals(source_id=req.source_id), ctx.request_id)
