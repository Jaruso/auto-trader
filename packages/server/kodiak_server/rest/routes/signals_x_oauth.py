"""X OAuth routes for signal-monitor authentication state."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from kodiak.signals.x_auth import (
    delete_x_oauth_credentials,
    save_x_oauth_credentials,
    x_oauth_status,
)
from kodiak_server.rest.context import RequestContext, get_request_context
from kodiak_server.rest.response import ok

router = APIRouter(prefix="/signals/x/oauth")


class ConnectXOAuthRequest(BaseModel):
    x_user_id: str
    username: str
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    scope: str = ""
    expires_in: int | None = None


@router.get("/status")
def status(ctx: RequestContext = Depends(get_request_context)) -> dict[str, Any]:
    """Return the non-secret X OAuth connection status."""
    return ok(x_oauth_status(), ctx.request_id)


@router.post("/connect")
def connect(
    req: ConnectXOAuthRequest,
    ctx: RequestContext = Depends(get_request_context),
) -> dict[str, Any]:
    """Persist X OAuth credentials for Kodiak's signal monitor."""
    credentials = save_x_oauth_credentials(**req.model_dump())
    return ok(
        {
            "connected": True,
            "x_user_id": credentials.x_user_id,
            "username": credentials.username,
            "expires_at": credentials.expires_at.isoformat() if credentials.expires_at else None,
        },
        ctx.request_id,
    )


@router.delete("")
def disconnect(ctx: RequestContext = Depends(get_request_context)) -> dict[str, Any]:
    """Delete stored X OAuth credentials."""
    return ok({"deleted": delete_x_oauth_credentials()}, ctx.request_id)
