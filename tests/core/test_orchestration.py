"""Tests for the Kodiak workflow orchestration engine."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from kodiak.orchestration import WorkflowExecutor, WorkflowPlan, WorkflowResult, WorkflowStep
from kodiak.orchestration.result import StepResult

# ---------------------------------------------------------------------------
# Helpers — fake executors that bypass the real broker
# ---------------------------------------------------------------------------


def _fake_ok(payload: object):
    """Return a dispatch-compatible success executor."""
    serialized = json.dumps(payload)

    def _fn(**kwargs):
        return serialized

    return _fn


def _fake_err(code: str, message: str):
    """Return a dispatch-compatible AppError executor."""
    serialized = json.dumps({"error": code, "message": message})

    def _fn(**kwargs):
        return serialized

    return _fn


def _raising(exc: Exception):
    """Return a dispatch-compatible executor that raises."""

    def _fn(**kwargs):
        raise exc

    return _fn


# ---------------------------------------------------------------------------
# WorkflowStep / WorkflowPlan — serialization
# ---------------------------------------------------------------------------


class TestPlanSerialization:
    def test_step_round_trip(self) -> None:
        step = WorkflowStep(
            primitive="get_quote",
            inputs={"symbol": "AAPL"},
            version="1.0.0",
            retry_count=2,
            depends_on=[0],
        )
        d = step.to_dict()
        restored = WorkflowStep.from_dict(d)
        assert restored.primitive == "get_quote"
        assert restored.inputs == {"symbol": "AAPL"}
        assert restored.version == "1.0.0"
        assert restored.retry_count == 2
        assert restored.depends_on == [0]

    def test_step_defaults(self) -> None:
        step = WorkflowStep.from_dict({"primitive": "get_quote"})
        assert step.inputs == {}
        assert step.version == "latest"
        assert step.retry_count == 0
        assert step.depends_on == []

    def test_plan_round_trip(self) -> None:
        plan = WorkflowPlan(
            name="test-plan",
            steps=[
                WorkflowStep(primitive="get_quote", inputs={"symbol": "MSFT"}),
                WorkflowStep(primitive="get_balance"),
            ],
            deterministic=True,
        )
        d = plan.to_dict()
        restored = WorkflowPlan.from_dict(d)
        assert restored.name == "test-plan"
        assert len(restored.steps) == 2
        assert restored.steps[0].primitive == "get_quote"
        assert restored.deterministic is True


# ---------------------------------------------------------------------------
# WorkflowResult serialization
# ---------------------------------------------------------------------------


class TestResultSerialization:
    def test_to_dict_shape(self) -> None:
        result = WorkflowResult(
            plan_name="my-plan",
            success=True,
            steps_completed=2,
            steps_total=2,
            step_results=[
                StepResult(
                    step_index=0,
                    primitive="get_quote",
                    version_resolved="1.0.0",
                    planned_inputs={"symbol": "AAPL"},
                    output={"last": 175.5},
                    success=True,
                    error=None,
                    attempts=1,
                    duration_ms=12.3,
                )
            ],
            total_duration_ms=45.6,
        )
        d = result.to_dict()
        assert d["plan_name"] == "my-plan"
        assert d["success"] is True
        assert d["steps_completed"] == 2
        assert d["steps_total"] == 2
        assert len(d["step_results"]) == 1
        assert d["total_duration_ms"] == 45.6


# ---------------------------------------------------------------------------
# WorkflowExecutor — happy path
# ---------------------------------------------------------------------------


class TestWorkflowExecutorHappyPath:
    def test_single_step_success(self) -> None:
        plan = WorkflowPlan(
            name="single-step",
            steps=[WorkflowStep(primitive="get_quote", inputs={"symbol": "AAPL"})],
            deterministic=False,
        )
        with patch(
            "kodiak.orchestration.dispatch._DISPATCH",
            {"get_quote": _fake_ok({"symbol": "AAPL", "last": 175.0})},
        ):
            result = WorkflowExecutor().execute(plan)

        assert result.success is True
        assert result.steps_completed == 1
        assert len(result.step_results) == 1
        assert result.step_results[0].success is True
        assert result.step_results[0].primitive == "get_quote"
        assert result.step_results[0].attempts == 1

    def test_multi_step_success(self) -> None:
        plan = WorkflowPlan(
            name="two-steps",
            steps=[
                WorkflowStep(primitive="get_quote", inputs={"symbol": "AAPL"}),
                WorkflowStep(primitive="get_balance"),
            ],
            deterministic=False,
        )
        dispatch = {
            "get_quote": _fake_ok({"last": 175.0}),
            "get_balance": _fake_ok({"cash": 100000.0}),
        }
        with patch("kodiak.orchestration.dispatch._DISPATCH", dispatch):
            result = WorkflowExecutor().execute(plan)

        assert result.success is True
        assert result.steps_completed == 2
        assert result.step_results[0].primitive == "get_quote"
        assert result.step_results[1].primitive == "get_balance"

    def test_step_output_recorded(self) -> None:
        payload = {"symbol": "AAPL", "last": 175.0}
        plan = WorkflowPlan(
            name="output-test",
            steps=[WorkflowStep(primitive="get_quote", inputs={"symbol": "AAPL"})],
            deterministic=False,
        )
        with patch(
            "kodiak.orchestration.dispatch._DISPATCH",
            {"get_quote": _fake_ok(payload)},
        ):
            result = WorkflowExecutor().execute(plan)

        assert result.step_results[0].output == payload
        assert result.step_results[0].planned_inputs == {"symbol": "AAPL"}


# ---------------------------------------------------------------------------
# WorkflowExecutor — failure handling
# ---------------------------------------------------------------------------


class TestWorkflowExecutorFailures:
    def test_app_error_response_fails_step(self) -> None:
        plan = WorkflowPlan(
            name="fail-test",
            steps=[WorkflowStep(primitive="get_quote", inputs={"symbol": "INVALID"})],
            deterministic=False,
        )
        with patch(
            "kodiak.orchestration.dispatch._DISPATCH",
            {"get_quote": _fake_err("SYMBOL_NOT_FOUND", "Symbol not found")},
        ):
            result = WorkflowExecutor().execute(plan)

        assert result.success is False
        assert result.steps_completed == 0
        assert result.step_results[0].success is False
        assert result.step_results[0].error is not None

    def test_second_step_not_run_after_first_failure(self) -> None:
        plan = WorkflowPlan(
            name="halt-test",
            steps=[
                WorkflowStep(primitive="get_quote", inputs={"symbol": "BAD"}),
                WorkflowStep(primitive="get_balance"),
            ],
            deterministic=False,
        )
        dispatch = {
            "get_quote": _fake_err("ERR", "fail"),
            "get_balance": _fake_ok({"cash": 1000.0}),
        }
        with patch("kodiak.orchestration.dispatch._DISPATCH", dispatch):
            result = WorkflowExecutor().execute(plan)

        assert result.success is False
        assert result.steps_completed == 0
        assert len(result.step_results) == 1  # second step never ran

    def test_exception_fails_step(self) -> None:
        plan = WorkflowPlan(
            name="exception-test",
            steps=[WorkflowStep(primitive="get_quote", inputs={})],
            deterministic=False,
        )
        with patch(
            "kodiak.orchestration.dispatch._DISPATCH",
            {"get_quote": _raising(RuntimeError("network timeout"))},
        ):
            result = WorkflowExecutor().execute(plan)

        assert result.success is False
        assert "network timeout" in (result.step_results[0].error or "")


# ---------------------------------------------------------------------------
# WorkflowExecutor — retry
# ---------------------------------------------------------------------------


class TestWorkflowExecutorRetry:
    def test_retries_on_exception(self) -> None:
        call_count = 0

        def flaky(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return json.dumps({"last": 175.0})

        plan = WorkflowPlan(
            name="retry-test",
            steps=[WorkflowStep(primitive="get_quote", inputs={}, retry_count=2)],
            deterministic=False,
        )
        with patch("kodiak.orchestration.dispatch._DISPATCH", {"get_quote": flaky}):
            with patch("kodiak.orchestration.executor.time.sleep"):  # skip actual sleep
                result = WorkflowExecutor().execute(plan)

        assert result.success is True
        assert result.step_results[0].attempts == 3

    def test_max_retries_exceeded_fails(self) -> None:
        calls = []

        def always_fails(**kwargs):
            calls.append(1)
            raise ConnectionError("always bad")

        plan = WorkflowPlan(
            name="retry-exhaust",
            steps=[WorkflowStep(primitive="get_quote", inputs={}, retry_count=1)],
            deterministic=False,
        )
        with patch("kodiak.orchestration.dispatch._DISPATCH", {"get_quote": always_fails}):
            with patch("kodiak.orchestration.executor.time.sleep"):
                result = WorkflowExecutor().execute(plan)

        assert result.success is False
        assert result.step_results[0].attempts == 2  # 1 initial + 1 retry
        assert len(calls) == 2

    def test_no_retry_on_app_error(self) -> None:
        calls = []

        def app_err(**kwargs):
            calls.append(1)
            return json.dumps({"error": "BAD_INPUT", "message": "bad"})

        plan = WorkflowPlan(
            name="no-retry-app-err",
            steps=[WorkflowStep(primitive="get_quote", inputs={}, retry_count=3)],
            deterministic=False,
        )
        with patch("kodiak.orchestration.dispatch._DISPATCH", {"get_quote": app_err}):
            result = WorkflowExecutor().execute(plan)

        assert result.success is False
        assert len(calls) == 1  # no retry on business error


# ---------------------------------------------------------------------------
# WorkflowExecutor — deterministic mode
# ---------------------------------------------------------------------------


class TestDeterministicMode:
    def test_unknown_primitive_aborts(self) -> None:
        plan = WorkflowPlan(
            name="unknown-prim",
            steps=[WorkflowStep(primitive="does_not_exist", inputs={})],
            deterministic=True,
        )
        result = WorkflowExecutor().execute(plan)
        assert result.success is False
        assert result.steps_completed == 0
        assert len(result.step_results) == 0  # aborted before any step ran

    def test_known_primitive_passes_validation(self) -> None:
        plan = WorkflowPlan(
            name="known-prim",
            steps=[WorkflowStep(primitive="get_quote", inputs={"symbol": "AAPL"})],
            deterministic=True,
        )
        with patch(
            "kodiak.orchestration.dispatch._DISPATCH",
            {"get_quote": _fake_ok({"last": 175.0})},
        ):
            result = WorkflowExecutor().execute(plan)

        assert result.success is True

    def test_non_deterministic_skips_validation(self) -> None:
        plan = WorkflowPlan(
            name="non-det",
            steps=[WorkflowStep(primitive="does_not_exist", inputs={})],
            deterministic=False,
        )
        # No executor registered → dispatch returns failure, but no pre-flight abort
        with patch("kodiak.orchestration.dispatch._DISPATCH", {}):
            result = WorkflowExecutor().execute(plan)

        # Fails at execution (no executor) rather than at validation
        assert result.success is False
        assert len(result.step_results) == 1


# ---------------------------------------------------------------------------
# REST endpoint parity
# ---------------------------------------------------------------------------


class TestWorkflowRestParity:
    @pytest.fixture()
    def rest_client(self):
        from fastapi.testclient import TestClient
        from kodiak_server.rest.app import create_rest_app

        return TestClient(create_rest_app())

    def test_run_workflow_endpoint_exists(self, rest_client) -> None:
        payload = {
            "plan_name": "rest-test",
            "steps": [
                {
                    "primitive": "get_quote",
                    "inputs": {"symbol": "AAPL"},
                    "retry_count": 0,
                }
            ],
            "deterministic": False,
        }
        with patch(
            "kodiak.orchestration.dispatch._DISPATCH",
            {"get_quote": _fake_ok({"last": 175.0})},
        ):
            resp = rest_client.post("/v1/workflows/run", json=payload)

        assert resp.status_code == 200
        body = resp.json()
        assert body["plan_name"] == "rest-test"
        assert "success" in body
        assert "step_results" in body

    def test_run_workflow_unknown_primitive_fails(self, rest_client) -> None:
        payload = {
            "plan_name": "bad-plan",
            "steps": [{"primitive": "no_such_primitive", "inputs": {}}],
            "deterministic": True,
        }
        resp = rest_client.post("/v1/workflows/run", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
