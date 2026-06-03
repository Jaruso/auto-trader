"""FastAPI REST application for Kodiak Server.

All routes live under /v1/* (this app is mounted at /api in main.py, so the
full paths are /api/v1/engine/status, /api/v1/portfolio/balance, etc.).

Every response uses the standard envelope from rest/response.py:
  success: {"data": ..., "error": null,  "meta": {"request_id": "...", "version": "v1"}}
  error:   {"data": null, "error": {...}, "meta": {"request_id": "...", "version": "v1"}}

Actor and role identity from X-Kodiak-Actor / X-Kodiak-Role headers are
captured by the request context middleware and threaded into the audit log
automatically for every request.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from kodiak.audit import clear_audit_context, set_audit_context
from kodiak.errors import AppError, NotFoundError, ValidationError
from kodiak.utils.logging import clear_log_context, get_logger, log_event, set_log_context

from kodiak_server.rest.context import get_current_request_id, set_request_context
from kodiak_server.rest.response import err
from kodiak_server.rest.routes import (
    engine,
    orders,
    portfolio,
    primitives,
    reports,
    research,
    safety,
    sessions,
    signals,
    signals_x_oauth,
    strategies,
    workflows,
)


def create_rest_app() -> FastAPI:
    """Create and configure the versioned REST API application."""
    logger = get_logger("kodiak_server.rest")
    app = FastAPI(
        title="Kodiak REST API",
        version="2.0.0",
        description=(
            "Kodiak headless trading and research API. "
            "All endpoints live under /v1/. "
            "Authenticate with: Authorization: Bearer <KODIAK_API_TOKEN>."
        ),
    )

    # ------------------------------------------------------------------
    # Middleware: generate request ID, capture actor/role, set audit ctx
    # ------------------------------------------------------------------

    @app.middleware("http")
    async def request_context_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started_at = time.perf_counter()
        request_id = str(uuid.uuid4())
        actor = request.headers.get("X-Kodiak-Actor")
        role = request.headers.get("X-Kodiak-Role")
        client_ip = request.client.host if request.client else None

        # Store in async-local context vars so handlers and exception
        # handlers can read them without explicit parameter threading.
        set_request_context(request_id, actor, role)

        # Mirror into audit context so log_action() picks them up
        # automatically for any action fired during this request.
        set_audit_context(
            actor=actor,
            request_id=request_id,
            role=role,
            source="rest",
            client_ip=client_ip,
        )
        set_log_context(
            request_id=request_id,
            actor=actor,
            role=role,
            client_ip=client_ip,
            method=request.method,
            path=request.url.path,
        )

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
            log_event(
                logger,
                logging.INFO,
                "http_request_complete",
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            return response
        finally:
            clear_log_context()
            clear_audit_context()

    # ------------------------------------------------------------------
    # Exception handlers
    # ------------------------------------------------------------------

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:  # noqa: ARG001
        request_id = get_current_request_id()
        status = 400
        if isinstance(exc, NotFoundError):
            status = 404
        elif isinstance(exc, ValidationError):
            status = 422
        return JSONResponse(
            err(exc.code, exc.message, request_id, exc.details or None, exc.suggestion),
            status_code=status,
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
        request_id = get_current_request_id()
        log_event(
            logger,
            logging.ERROR,
            "http_request_error",
            status_code=500,
        )
        return JSONResponse(
            err("INTERNAL_ERROR", "An unexpected error occurred.", request_id),
            status_code=500,
        )

    # ------------------------------------------------------------------
    # v1 router — all business routes live here
    # ------------------------------------------------------------------

    v1 = APIRouter(prefix="/v1")
    v1.include_router(engine.router, tags=["engine"])
    v1.include_router(portfolio.router, tags=["portfolio"])
    v1.include_router(primitives.router, tags=["primitives"])
    v1.include_router(reports.router, tags=["reports"])
    v1.include_router(research.router, tags=["research"])
    v1.include_router(orders.router, tags=["orders"])
    v1.include_router(safety.router, tags=["safety"])
    v1.include_router(sessions.router, tags=["sessions"])
    v1.include_router(signals.router, tags=["signals"])
    v1.include_router(signals_x_oauth.router, tags=["signals"])
    v1.include_router(strategies.router, tags=["strategies"])
    v1.include_router(workflows.router, tags=["workflows"])

    # Schema export: GET /api/v1/schema.json returns the OpenAPI spec.
    # Useful for generating typed clients and contract validators.
    @v1.get("/schema.json", include_in_schema=False)
    async def schema_json() -> dict[str, Any]:
        return app.openapi()

    app.include_router(v1)

    return app
