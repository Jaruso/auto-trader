"""Kodiak Server entry point.

Runs a FastAPI application with:
- REST API at /api/v1/
- MCP server (streamable HTTP) at /mcp/
- Minimal headless landing page at /
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any


def _run_migrations() -> None:
    """Apply the kodiak schema to Postgres on startup if DB is configured.

    Idempotent — safe to run on every boot. If KODIAK_DATABASE_URL is not
    set, this is a no-op and the YAML stores are used instead.
    """
    from kodiak.db.connection import db_available

    if not db_available():
        return

    try:
        from kodiak.db.migrations import ensure_schema
        ensure_schema()
        print("  DB:        kodiak schema up to date", file=sys.stderr)
    except Exception as e:
        # Log but don't crash — YAML fallback is still available.
        print(f"  DB:        migration warning: {e}", file=sys.stderr)


def create_app() -> Any:
    """Create the combined FastAPI + MCP application."""
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from kodiak.app.signals import get_signal_monitor_config
    from kodiak.utils.config import load_config
    from kodiak.utils.logging import get_logger, setup_logging

    from kodiak_server.monitoring.signals import SignalMonitor
    from kodiak_server.mcp.server import create_mcp_app
    from kodiak_server.rest.app import create_rest_app
    from kodiak_server.web import create_web_app

    config = load_config()
    setup_logging(
        log_dir=config.log_dir,
        log_to_file=os.getenv("KODIAK_LOG_TO_FILE", "true").lower() in {"1", "true", "yes"},
        console_stream=sys.stderr,
        log_format=os.getenv("KODIAK_LOG_FORMAT", "json"),
    )
    logger = get_logger("kodiak_server.main")
    signal_config = get_signal_monitor_config()
    signal_monitor = SignalMonitor(signal_config.poll_interval_seconds) if signal_config.enabled else None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001
        # Startup: apply any pending DB schema migrations.
        _run_migrations()
        if signal_monitor is not None:
            await signal_monitor.start()
            app.state.signal_monitor = signal_monitor
        logger.info("Kodiak server startup complete")
        yield
        # Shutdown: nothing to clean up yet.
        if signal_monitor is not None:
            await signal_monitor.stop()
        logger.info("Kodiak server shutdown complete")

    app = FastAPI(
        title="Kodiak Server",
        description="Automated trading server with REST API and MCP",
        version="2.0.0",
        lifespan=lifespan,
    )

    # API key auth — protects /api/* and /mcp/* routes.
    # Set KODIAK_API_TOKEN in the environment; /health is always exempt.
    @app.middleware("http")
    async def api_key_auth(
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        protected = request.url.path.startswith("/api") or request.url.path.startswith("/mcp")
        if protected:
            token = os.environ.get("KODIAK_API_TOKEN", "")
            auth = request.headers.get("Authorization", "")
            if not token or auth != f"Bearer {token}":
                return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

    # Health endpoint — no auth required, checked by blink and monitoring.
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "kodiak"}

    # Mount REST API
    rest_app = create_rest_app()
    app.mount("/api", rest_app)

    # Mount MCP (streamable HTTP)
    mcp_app = create_mcp_app()
    app.mount("/mcp", mcp_app)

    # Mount landing page (must be last — catches remaining routes)
    web_app = create_web_app()
    app.mount("/", web_app)

    return app


def main() -> None:
    """CLI entry point for kodiak-server."""
    parser = argparse.ArgumentParser(description="Kodiak Trading Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    parser.add_argument("--ssl-certfile", default=None, help="TLS certificate file")
    parser.add_argument("--ssl-keyfile", default=None, help="TLS private key file")
    args = parser.parse_args()

    import uvicorn

    ssl_kwargs = {}
    if args.ssl_certfile and args.ssl_keyfile:
        ssl_kwargs["ssl_certfile"] = args.ssl_certfile
        ssl_kwargs["ssl_keyfile"] = args.ssl_keyfile

    from kodiak.utils.config import load_config
    from kodiak.utils.logging import get_logger, setup_logging

    config = load_config()
    setup_logging(
        log_dir=config.log_dir,
        log_to_file=os.getenv("KODIAK_LOG_TO_FILE", "true").lower() in {"1", "true", "yes"},
        console_stream=sys.stderr,
        log_format=os.getenv("KODIAK_LOG_FORMAT", "json"),
    )
    logger = get_logger("kodiak_server.main")
    logger.info("Starting Kodiak Server on %s:%s", args.host, args.port)
    logger.info("REST API: http://%s:%s/api/v1/", args.host, args.port)
    logger.info("API docs: http://%s:%s/api/docs", args.host, args.port)
    logger.info("Schema: http://%s:%s/api/v1/schema.json", args.host, args.port)
    logger.info("MCP: http://%s:%s/mcp/", args.host, args.port)
    logger.info("Landing page: http://%s:%s/", args.host, args.port)

    uvicorn.run(
        "kodiak_server.main:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        **ssl_kwargs,
    )


if __name__ == "__main__":
    main()
