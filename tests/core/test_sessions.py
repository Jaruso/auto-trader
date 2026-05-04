"""Tests for the execution session layer."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from kodiak.app.sessions import (
    get_session_app,
    get_session_store,
    list_sessions_app,
    replay_session_app,
    run_and_save,
)
from kodiak.orchestration import WorkflowPlan, WorkflowStep
from kodiak.orchestration.session import ExecutionSession, SessionStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_ok(payload: object):
    serialized = json.dumps(payload)

    def _fn(**kwargs):
        return serialized

    return _fn


def _make_plan(name: str = "test-plan", primitive: str = "get_balance") -> WorkflowPlan:
    return WorkflowPlan(name=name, steps=[WorkflowStep(primitive=primitive)])


# ---------------------------------------------------------------------------
# ExecutionSession dataclass
# ---------------------------------------------------------------------------


class TestExecutionSession:
    def test_to_dict_round_trip(self) -> None:
        session = ExecutionSession(
            session_id="abc",
            plan_name="my-plan",
            started_at="2026-01-01T00:00:00+00:00",
            completed_at="2026-01-01T00:00:01+00:00",
            success=True,
            steps_completed=2,
            steps_total=2,
            total_duration_ms=123.4,
            plan={"name": "my-plan", "steps": []},
            step_results=[],
        )
        restored = ExecutionSession.from_dict(session.to_dict())
        assert restored.session_id == "abc"
        assert restored.plan_name == "my-plan"
        assert restored.success is True
        assert restored.steps_completed == 2

    def test_from_execution_factory(self) -> None:
        plan = _make_plan()
        result_dict = {
            "plan_name": "test-plan",
            "success": True,
            "steps_completed": 1,
            "steps_total": 1,
            "total_duration_ms": 10.0,
            "step_results": [],
        }
        session = ExecutionSession.from_execution(
            session_id="sess-1",
            started_at="2026-01-01T00:00:00+00:00",
            completed_at="2026-01-01T00:00:01+00:00",
            plan_dict=plan.to_dict(),
            result_dict=result_dict,
        )
        assert session.session_id == "sess-1"
        assert session.plan_name == "test-plan"
        assert session.success is True
        assert session.plan == plan.to_dict()


# ---------------------------------------------------------------------------
# SessionStore
# ---------------------------------------------------------------------------


class TestSessionStore:
    def test_save_and_get(self, tmp_path: Path) -> None:
        store = SessionStore(tmp_path)
        session = ExecutionSession(
            session_id="sess-abc",
            plan_name="plan-a",
            started_at="2026-01-01T00:00:00+00:00",
            completed_at="2026-01-01T00:00:01+00:00",
            success=True,
            steps_completed=1,
            steps_total=1,
            total_duration_ms=5.0,
            plan={},
            step_results=[],
        )
        store.save(session)
        loaded = store.get("sess-abc")
        assert loaded is not None
        assert loaded.session_id == "sess-abc"
        assert loaded.plan_name == "plan-a"

    def test_get_missing_returns_none(self, tmp_path: Path) -> None:
        store = SessionStore(tmp_path)
        assert store.get("does-not-exist") is None

    def test_list_returns_most_recent_first(self, tmp_path: Path) -> None:
        store = SessionStore(tmp_path)
        for i in range(3):
            store.save(
                ExecutionSession(
                    session_id=f"sess-{i}",
                    plan_name="plan-x",
                    started_at=f"2026-01-0{i + 1}T00:00:00+00:00",
                    completed_at=f"2026-01-0{i + 1}T00:00:01+00:00",
                    success=True,
                    steps_completed=1,
                    steps_total=1,
                    total_duration_ms=1.0,
                    plan={},
                    step_results=[],
                )
            )
        sessions = store.list()
        assert sessions[0].session_id == "sess-2"  # most recent
        assert sessions[-1].session_id == "sess-0"

    def test_list_filters_by_plan_name(self, tmp_path: Path) -> None:
        store = SessionStore(tmp_path)
        for name in ("alpha", "beta", "alpha"):
            store.save(
                ExecutionSession(
                    session_id=str(uuid.uuid4()),
                    plan_name=name,
                    started_at="2026-01-01T00:00:00+00:00",
                    completed_at="2026-01-01T00:00:01+00:00",
                    success=True,
                    steps_completed=1,
                    steps_total=1,
                    total_duration_ms=1.0,
                    plan={},
                    step_results=[],
                )
            )
        alpha = store.list(plan_name="alpha")
        assert len(alpha) == 2
        assert all(s.plan_name == "alpha" for s in alpha)

    def test_list_respects_limit(self, tmp_path: Path) -> None:
        store = SessionStore(tmp_path)
        for i in range(10):
            store.save(
                ExecutionSession(
                    session_id=str(uuid.uuid4()),
                    plan_name="p",
                    started_at=f"2026-01-{i + 1:02d}T00:00:00+00:00",
                    completed_at=f"2026-01-{i + 1:02d}T00:00:01+00:00",
                    success=True,
                    steps_completed=1,
                    steps_total=1,
                    total_duration_ms=1.0,
                    plan={},
                    step_results=[],
                )
            )
        assert len(store.list(limit=3)) == 3

    def test_creates_directory_if_absent(self, tmp_path: Path) -> None:
        new_dir = tmp_path / "deep" / "sessions"
        store = SessionStore(new_dir)
        assert new_dir.exists()
        assert store.get("x") is None  # no error on empty dir

    def test_corrupted_file_is_skipped(self, tmp_path: Path) -> None:
        store = SessionStore(tmp_path)
        (tmp_path / "bad.json").write_text("{not valid json")
        assert store.list() == []


# ---------------------------------------------------------------------------
# App service layer
# ---------------------------------------------------------------------------


class TestRunAndSave:
    def test_persists_session_and_returns_result(self, tmp_path: Path) -> None:
        plan = _make_plan()
        dispatch = {"get_balance": _fake_ok({"cash": 50000.0})}
        with patch("kodiak.orchestration.dispatch._DISPATCH", dispatch):
            result, session = run_and_save(plan, sessions_dir=tmp_path)

        assert result.success is True
        assert session.success is True
        assert session.plan_name == "test-plan"
        assert session.session_id  # non-empty UUID
        assert session.plan == plan.to_dict()
        assert len(session.step_results) == 1

        # Verify session was persisted
        store = SessionStore(tmp_path)
        loaded = store.get(session.session_id)
        assert loaded is not None
        assert loaded.success is True

    def test_failed_plan_also_persists(self, tmp_path: Path) -> None:
        plan = _make_plan()
        dispatch: dict = {}
        with patch("kodiak.orchestration.dispatch._DISPATCH", dispatch):
            result, session = run_and_save(plan, sessions_dir=tmp_path)

        assert result.success is False
        assert session.success is False

        store = SessionStore(tmp_path)
        loaded = store.get(session.session_id)
        assert loaded is not None
        assert loaded.success is False


class TestListAndGetSessionApp:
    def test_list_sessions_returns_dicts(self, tmp_path: Path) -> None:
        plan = _make_plan()
        dispatch = {"get_balance": _fake_ok({"cash": 1.0})}
        with patch("kodiak.orchestration.dispatch._DISPATCH", dispatch):
            run_and_save(plan, sessions_dir=tmp_path)

        results = list_sessions_app(sessions_dir=tmp_path)
        assert len(results) == 1
        assert results[0]["plan_name"] == "test-plan"
        assert results[0]["success"] is True

    def test_get_session_app_returns_dict(self, tmp_path: Path) -> None:
        plan = _make_plan()
        dispatch = {"get_balance": _fake_ok({"cash": 1.0})}
        with patch("kodiak.orchestration.dispatch._DISPATCH", dispatch):
            _, session = run_and_save(plan, sessions_dir=tmp_path)

        loaded = get_session_app(session.session_id, sessions_dir=tmp_path)
        assert loaded is not None
        assert loaded["session_id"] == session.session_id

    def test_get_session_app_missing_returns_none(self, tmp_path: Path) -> None:
        assert get_session_app("nonexistent", sessions_dir=tmp_path) is None


class TestReplaySessionApp:
    def test_replay_re_executes_plan(self, tmp_path: Path) -> None:
        plan = _make_plan()
        dispatch = {"get_balance": _fake_ok({"cash": 1.0})}
        with patch("kodiak.orchestration.dispatch._DISPATCH", dispatch):
            _, original_session = run_and_save(plan, sessions_dir=tmp_path)
            outcome = replay_session_app(original_session.session_id, sessions_dir=tmp_path)

        assert outcome is not None
        result, new_session = outcome
        assert result.success is True
        assert new_session.session_id != original_session.session_id
        assert new_session.plan_name == original_session.plan_name

    def test_replay_missing_session_returns_none(self, tmp_path: Path) -> None:
        assert replay_session_app("no-such-session", sessions_dir=tmp_path) is None


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


class TestSessionRestEndpoints:
    @pytest.fixture()
    def rest_client(self, tmp_path: Path):
        from fastapi.testclient import TestClient
        from kodiak_server.rest.app import create_rest_app

        client = TestClient(create_rest_app())
        # Override the session store to use tmp_path for all calls
        with patch("kodiak.app.sessions.get_session_store", lambda *_a, **_kw: SessionStore(tmp_path)):
            yield client, tmp_path

    def test_list_sessions_empty(self, rest_client) -> None:
        client, _ = rest_client
        resp = client.get("/v1/sessions/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []

    def test_get_session_not_found(self, rest_client) -> None:
        client, _ = rest_client
        resp = client.get("/v1/sessions/no-such-id")
        assert resp.status_code == 404

    def test_replay_session_not_found(self, rest_client) -> None:
        client, _ = rest_client
        resp = client.post("/v1/sessions/no-such-id/replay")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


class TestSessionMcpTools:
    def test_list_sessions_tool_returns_list(self) -> None:
        from kodiak.mcp.tools import list_sessions

        result = json.loads(list_sessions())
        assert isinstance(result, list)

    def test_get_session_tool_missing(self) -> None:
        from kodiak.mcp.tools import get_session

        result = json.loads(get_session("no-such-id"))
        # _err returns AppError dict with "error" key
        assert "error" in result

    def test_replay_session_tool_missing(self) -> None:
        from kodiak.mcp.tools import replay_session

        result = json.loads(replay_session("no-such-id"))
        assert "error" in result

    def test_list_sessions_tool_with_session(self, tmp_path: Path) -> None:
        from kodiak.mcp.tools import list_sessions

        plan = _make_plan()
        dispatch = {"get_balance": _fake_ok({"cash": 1.0})}
        with (
            patch("kodiak.orchestration.dispatch._DISPATCH", dispatch),
            patch("kodiak.app.sessions.get_session_store", lambda *_a, **_kw: SessionStore(tmp_path)),
        ):
            run_and_save(plan, sessions_dir=tmp_path)
            with patch("kodiak.app.sessions.get_session_store", lambda *_a, **_kw: SessionStore(tmp_path)):
                result = json.loads(list_sessions())
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["plan_name"] == "test-plan"
