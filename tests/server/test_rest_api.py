"""REST API contract tests.

Validates:
- Route versioning: all business endpoints live under /api/v1/
- Response envelope: every response has data/error/meta with request_id
- Auth enforcement: /api/v1/* requires Bearer token, /health does not
- Actor propagation: X-Kodiak-Actor header is accepted without error
- Schema export: GET /api/v1/schema.json returns valid OpenAPI JSON
- X-Request-ID header is returned on every response
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

TEST_TOKEN = "test-token-k1"


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Test client with auth configured."""
    monkeypatch.setenv("KODIAK_API_TOKEN", TEST_TOKEN)
    from kodiak_server.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture()
def authed(client: TestClient) -> dict[str, str]:
    """Convenience: auth headers for the test token."""
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


# ---------------------------------------------------------------------------
# Health — always public
# ---------------------------------------------------------------------------


def test_health_no_auth(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_web_root_serves_headless_landing_page(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "Kodiak Headless Server" in r.text
    assert "/api/docs" in r.text
    assert "/api/v1/schema.json" in r.text
    assert "/mcp/" in r.text
    assert "KODIAK_API_TOKEN" not in r.text


def test_dashboard_route_not_exposed(client: TestClient) -> None:
    r = client.get("/dashboard")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------


def test_api_requires_auth(client: TestClient) -> None:
    r = client.get("/api/v1/engine/status")
    assert r.status_code == 401


def test_api_wrong_token_rejected(client: TestClient) -> None:
    r = client.get("/api/v1/engine/status", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Route versioning: /api/v1/* must exist
# ---------------------------------------------------------------------------


def test_versioned_engine_route_exists(client: TestClient, authed: dict) -> None:
    r = client.get("/api/v1/engine/status", headers=authed)
    # 200 (running) or 400 (AppError — no broker) — both are valid business responses
    assert r.status_code in (200, 400)


def test_versioned_portfolio_route_exists(client: TestClient, authed: dict) -> None:
    r = client.get("/api/v1/portfolio/summary", headers=authed)
    assert r.status_code in (200, 400)


def test_versioned_portfolio_analytics_route_exists(client: TestClient, authed: dict) -> None:
    r = client.get(
        "/api/v1/portfolio/analytics?lookback_days=30&benchmark_symbol=SPY&end_date=2024-12-31",
        headers=authed,
    )
    assert r.status_code in (200, 400, 422)


def test_analysis_report_route_exists(client: TestClient, authed: dict) -> None:
    r = client.post(
        "/api/v1/reports/analysis",
        headers=authed,
        json={"days": 1, "include_portfolio": False},
    )
    assert r.status_code in (200, 400, 422)


def test_position_size_route_exists(client: TestClient, authed: dict) -> None:
    r = client.post(
        "/api/v1/portfolio/position-size",
        headers=authed,
        json={"symbol": "AAPL", "method": "target_weight", "target_weight_pct": 10},
    )
    assert r.status_code in (200, 400, 422)


def test_rebalance_plan_route_exists(client: TestClient, authed: dict) -> None:
    r = client.post(
        "/api/v1/portfolio/rebalance-plan",
        headers=authed,
        json={"target_weights": {"AAPL": 10, "MSFT": 10}},
    )
    assert r.status_code in (200, 400, 422)


def test_research_fundamentals_route_exists(client: TestClient, authed: dict) -> None:
    r = client.get("/api/v1/research/fundamentals/AAPL", headers=authed)
    assert r.status_code in (200, 400, 422)


def test_research_benchmark_route_exists(client: TestClient, authed: dict) -> None:
    r = client.get(
        "/api/v1/research/benchmark/SPY?start=2024-01-01&end=2024-01-31",
        headers=authed,
    )
    assert r.status_code in (200, 400, 422)


def test_safety_status_route_exists(client: TestClient, authed: dict) -> None:
    r = client.get("/api/v1/safety/status", headers=authed)
    assert r.status_code in (200, 400)


def test_signal_overview_route_exists(client: TestClient, authed: dict) -> None:
    r = client.get("/api/v1/signals/overview", headers=authed)
    assert r.status_code == 200
    _assert_envelope(r.json())


def test_signal_alerts_route_exists(client: TestClient, authed: dict) -> None:
    r = client.get("/api/v1/signals/alerts?limit=5", headers=authed)
    assert r.status_code == 200
    _assert_envelope(r.json())


def test_signal_sources_route_exists(client: TestClient, authed: dict) -> None:
    r = client.get("/api/v1/signals/sources", headers=authed)
    assert r.status_code == 200
    _assert_envelope(r.json())


def test_signal_poll_route_exists(client: TestClient, authed: dict) -> None:
    r = client.post("/api/v1/signals/poll", headers=authed, json={})
    assert r.status_code in (200, 400)
    _assert_envelope(r.json())


def test_x_oauth_status_route_exists(client: TestClient, authed: dict) -> None:
    r = client.get("/api/v1/signals/x/oauth/status", headers=authed)
    assert r.status_code == 200
    _assert_envelope(r.json())


def test_x_oauth_connect_and_disconnect_routes_work(
    client: TestClient,
    authed: dict,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("KODIAK_SIGNAL_ENCRYPTION_SECRET", "encryption-secret")

    from kodiak.signals import x_auth as x_auth_module
    monkeypatch.setattr(x_auth_module, "get_signals_data_dir", lambda data_dir=None: tmp_path)

    connect = client.post(
        "/api/v1/signals/x/oauth/connect",
        headers=authed,
        json={
            "x_user_id": "42",
            "username": "signaldesk",
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "token_type": "bearer",
            "scope": "tweet.read users.read offline.access",
            "expires_in": 3600,
        },
    )
    assert connect.status_code == 200
    _assert_envelope(connect.json())

    status = client.get("/api/v1/signals/x/oauth/status", headers=authed)
    assert status.status_code == 200
    _assert_envelope(status.json())
    assert status.json()["data"]["connected"] is True

    disconnect = client.delete("/api/v1/signals/x/oauth", headers=authed)
    assert disconnect.status_code == 200
    _assert_envelope(disconnect.json())

def test_engine_stop_requires_execution_confirmation(
    client: TestClient,
    authed: dict,
) -> None:
    r = client.post("/api/v1/engine/stop", headers=authed, json={"force": False})
    assert r.status_code == 400
    body = r.json()
    _assert_envelope(body)
    assert body["error"]["code"] == "POLICY_BLOCKED"


def test_engine_stop_with_confirmation_reaches_engine_state(
    client: TestClient,
    authed: dict,
) -> None:
    r = client.post(
        "/api/v1/engine/stop",
        headers=authed,
        json={"force": False, "confirm_execution": True},
    )
    assert r.status_code == 400
    body = r.json()
    _assert_envelope(body)
    assert body["error"]["code"] == "ENGINE_NOT_RUNNING"


def test_engine_start_requires_execution_confirmation(
    client: TestClient,
    authed: dict,
) -> None:
    r = client.post("/api/v1/engine/start", headers=authed, json={"dry_run": True})
    assert r.status_code == 400
    body = r.json()
    _assert_envelope(body)
    assert body["error"]["code"] == "POLICY_BLOCKED"


def test_order_create_requires_execution_confirmation(
    client: TestClient,
    authed: dict,
) -> None:
    r = client.post(
        "/api/v1/orders/",
        headers=authed,
        json={"symbol": "AAPL", "qty": 1, "side": "buy", "price": 100},
    )
    assert r.status_code == 400
    body = r.json()
    _assert_envelope(body)
    assert body["error"]["code"] == "POLICY_BLOCKED"
    assert body["error"]["details"]["policy"]["action"] == "place_order"


def test_order_create_with_confirmation_reaches_broker_or_safety_layer(
    client: TestClient,
    authed: dict,
) -> None:
    r = client.post(
        "/api/v1/orders/",
        headers=authed,
        json={
            "symbol": "AAPL",
            "qty": 1,
            "side": "buy",
            "price": 6000,
            "confirm_execution": True,
        },
    )
    assert r.status_code in (200, 400, 422)
    body = r.json()
    _assert_envelope(body)
    if body["error"]:
        assert body["error"]["code"] != "POLICY_BLOCKED"


def test_order_cancel_requires_execution_confirmation(
    client: TestClient,
    authed: dict,
) -> None:
    r = client.delete("/api/v1/orders/order-123", headers=authed)
    assert r.status_code == 400
    body = r.json()
    _assert_envelope(body)
    assert body["error"]["code"] == "POLICY_BLOCKED"
    assert body["error"]["details"]["policy"]["action"] == "cancel_order"


def test_order_cancel_with_confirmation_reaches_broker_layer(
    client: TestClient,
    authed: dict,
) -> None:
    r = client.delete("/api/v1/orders/order-123?confirm_execution=true", headers=authed)
    assert r.status_code in (200, 400)
    body = r.json()
    _assert_envelope(body)
    if body["error"]:
        assert body["error"]["code"] != "POLICY_BLOCKED"


def test_blocked_rest_execution_audit_includes_request_context(
    client: TestClient,
    authed: dict,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from kodiak.audit import log_action as real_log_action

    def capture_log_action(
        action: str,
        details: dict[str, Any],
        *,
        error: str | None = None,
        log_dir: Path | None = None,
    ) -> None:
        real_log_action(action, details, error=error, log_dir=tmp_path)

    monkeypatch.setattr("kodiak.policy.log_action", capture_log_action)
    headers = {**authed, "X-Kodiak-Actor": "operator@example.com", "X-Kodiak-Role": "operator"}

    r = client.post(
        "/api/v1/orders/",
        headers=headers,
        json={"symbol": "AAPL", "qty": 1, "side": "buy", "price": 100},
    )

    body = r.json()
    assert r.status_code == 400
    assert body["error"]["code"] == "POLICY_BLOCKED"
    record = json.loads((tmp_path / "audit.log").read_text().strip())
    assert record["source"] == "rest"
    assert record["actor"] == "operator@example.com"
    assert record["role"] == "operator"
    assert record["request_id"] == body["meta"]["request_id"]
    assert record["request_id"] == r.headers["x-request-id"]
    assert record["details"]["policy"]["action"] == "place_order"
    assert record["details"]["policy"]["allowed"] is False


def test_versioned_orders_route_exists(client: TestClient, authed: dict) -> None:
    r = client.get("/api/v1/orders/", headers=authed)
    assert r.status_code in (200, 400)


def test_versioned_strategies_route_exists(client: TestClient, authed: dict) -> None:
    r = client.get("/api/v1/strategies/", headers=authed)
    assert r.status_code in (200, 400)


# ---------------------------------------------------------------------------
# Response envelope contract
# ---------------------------------------------------------------------------


def _assert_envelope(body: dict[str, Any]) -> None:
    """Every response must carry the standard envelope shape."""
    assert "data" in body, "envelope missing 'data'"
    assert "error" in body, "envelope missing 'error'"
    assert "meta" in body, "envelope missing 'meta'"
    meta = body["meta"]
    assert "request_id" in meta, "meta missing 'request_id'"
    assert "version" in meta, "meta missing 'version'"
    assert meta["version"] == "v1"
    # Exactly one of data/error must be non-null
    assert (body["data"] is None) != (body["error"] is None), (
        "envelope must have exactly one of data or error non-null"
    )


def test_success_response_has_envelope(client: TestClient, authed: dict) -> None:
    r = client.get("/api/v1/strategies/", headers=authed)
    assert r.status_code in (200, 400)
    _assert_envelope(r.json())


def test_error_response_has_envelope(client: TestClient, authed: dict) -> None:
    # Fetch a non-existent strategy — guaranteed NotFoundError (404)
    r = client.get("/api/v1/strategies/nonexistent-xyz", headers=authed)
    assert r.status_code == 404
    body = r.json()
    _assert_envelope(body)
    assert body["data"] is None
    error = body["error"]
    assert "code" in error
    assert "message" in error


def test_x_request_id_header_on_response(client: TestClient, authed: dict) -> None:
    r = client.get("/api/v1/strategies/", headers=authed)
    assert "x-request-id" in r.headers, "X-Request-ID header missing from response"


def test_x_process_time_header_on_response(client: TestClient, authed: dict) -> None:
    r = client.get("/api/v1/strategies/", headers=authed)
    assert "x-process-time-ms" in r.headers, "X-Process-Time-Ms header missing from response"
    assert float(r.headers["x-process-time-ms"]) >= 0


def test_request_id_matches_meta(client: TestClient, authed: dict) -> None:
    r = client.get("/api/v1/strategies/", headers=authed)
    header_id = r.headers.get("x-request-id")
    meta_id = r.json()["meta"]["request_id"]
    assert header_id == meta_id, "X-Request-ID header must match meta.request_id"


# ---------------------------------------------------------------------------
# Actor propagation
# ---------------------------------------------------------------------------


def test_actor_header_accepted(client: TestClient, authed: dict) -> None:
    headers = {**authed, "X-Kodiak-Actor": "joe@example.com", "X-Kodiak-Role": "operator"}
    r = client.get("/api/v1/strategies/", headers=headers)
    # Just verify the headers don't cause a 4xx/5xx
    assert r.status_code in (200, 400)
    _assert_envelope(r.json())


# ---------------------------------------------------------------------------
# Schema export (K1-D)
# ---------------------------------------------------------------------------


def test_schema_json_returns_openapi(client: TestClient, authed: dict) -> None:
    r = client.get("/api/v1/schema.json", headers=authed)
    assert r.status_code == 200
    schema = r.json()
    assert "openapi" in schema, "schema.json must contain 'openapi' key"
    assert "paths" in schema, "schema.json must contain 'paths' key"
    assert "info" in schema, "schema.json must contain 'info' key"


def test_schema_contains_v1_paths(client: TestClient, authed: dict) -> None:
    r = client.get("/api/v1/schema.json", headers=authed)
    schema = r.json()
    paths = list(schema.get("paths", {}).keys())
    v1_paths = [p for p in paths if p.startswith("/v1/")]
    assert len(v1_paths) > 0, f"No /v1/ paths found in schema. Got: {paths}"
