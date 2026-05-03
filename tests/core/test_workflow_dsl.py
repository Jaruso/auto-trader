"""Tests for the workflow DSL — parsing, validation, compilation."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from kodiak.orchestration import WorkflowExecutor, WorkflowSpec, WorkflowSpecError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _yaml(text: str) -> str:
    return textwrap.dedent(text).strip()


def _fake_ok(payload: object):
    serialized = json.dumps(payload)

    def _fn(**kwargs):
        return serialized

    return _fn


# ---------------------------------------------------------------------------
# WorkflowSpec.from_yaml
# ---------------------------------------------------------------------------


class TestFromYaml:
    def test_full_form(self) -> None:
        spec = WorkflowSpec.from_yaml(
            _yaml("""
            name: test-plan
            steps:
              - primitive: get_quote
                inputs:
                  symbol: AAPL
              - primitive: get_balance
            """)
        )
        assert isinstance(spec, WorkflowSpec)

    def test_short_form_steps(self) -> None:
        spec = WorkflowSpec.from_yaml(
            _yaml("""
            name: short-plan
            steps:
              - get_balance
              - get_positions
            """)
        )
        plan = spec.compile()
        assert plan.steps[0].primitive == "get_balance"
        assert plan.steps[1].primitive == "get_positions"

    def test_compact_form(self) -> None:
        spec = WorkflowSpec.from_yaml(
            _yaml("""
            portfolio_review:
              - get_portfolio
              - get_today_pnl
            """)
        )
        plan = spec.compile()
        assert plan.name == "portfolio_review"
        assert len(plan.steps) == 2

    def test_invalid_yaml_raises(self) -> None:
        with pytest.raises(WorkflowSpecError, match="Invalid YAML"):
            WorkflowSpec.from_yaml("{{bad: yaml: :")

    def test_non_mapping_raises(self) -> None:
        with pytest.raises(WorkflowSpecError):
            WorkflowSpec.from_yaml("- just_a_list")


# ---------------------------------------------------------------------------
# WorkflowSpec.from_json
# ---------------------------------------------------------------------------


class TestFromJson:
    def test_full_form_json(self) -> None:
        data = json.dumps(
            {
                "name": "json-plan",
                "steps": [
                    {"primitive": "get_quote", "inputs": {"symbol": "MSFT"}},
                    {"primitive": "get_balance"},
                ],
            }
        )
        spec = WorkflowSpec.from_json(data)
        plan = spec.compile()
        assert plan.name == "json-plan"
        assert len(plan.steps) == 2

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(WorkflowSpecError, match="Invalid JSON"):
            WorkflowSpec.from_json("{not json}")

    def test_non_object_raises(self) -> None:
        with pytest.raises(WorkflowSpecError):
            WorkflowSpec.from_json("[1, 2, 3]")


# ---------------------------------------------------------------------------
# WorkflowSpec.from_file
# ---------------------------------------------------------------------------


class TestFromFile:
    def test_yaml_file(self, tmp_path: Path) -> None:
        f = tmp_path / "plan.yaml"
        f.write_text("name: file-plan\nsteps:\n  - get_balance\n")
        spec = WorkflowSpec.from_file(f)
        plan = spec.compile()
        assert plan.name == "file-plan"

    def test_json_file(self, tmp_path: Path) -> None:
        f = tmp_path / "plan.json"
        f.write_text('{"name": "json-file-plan", "steps": [{"primitive": "get_balance"}]}')
        spec = WorkflowSpec.from_file(f)
        plan = spec.compile()
        assert plan.name == "json-file-plan"

    def test_yml_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "plan.yml"
        f.write_text("name: yml-plan\nsteps:\n  - get_quote\n")
        spec = WorkflowSpec.from_file(f)
        plan = spec.compile()
        assert plan.steps[0].primitive == "get_quote"

    def test_example_market_check_file(self) -> None:
        examples_dir = Path(__file__).resolve().parents[2] / "examples" / "workflows"
        spec = WorkflowSpec.from_file(examples_dir / "market-check.yaml")
        plan = spec.compile()
        assert plan.name == "market-check"
        assert len(plan.steps) >= 1

    def test_example_portfolio_review_file(self) -> None:
        examples_dir = Path(__file__).resolve().parents[2] / "examples" / "workflows"
        spec = WorkflowSpec.from_file(examples_dir / "portfolio-review.yaml")
        plan = spec.compile()
        assert plan.name == "portfolio-review"

    def test_example_research_pipeline_file(self) -> None:
        examples_dir = Path(__file__).resolve().parents[2] / "examples" / "workflows"
        spec = WorkflowSpec.from_file(examples_dir / "research-pipeline.yaml")
        plan = spec.compile()
        assert plan.name == "research-pipeline"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_spec_returns_empty_errors(self) -> None:
        # get_quote and get_balance both have MCP tool executors
        spec = WorkflowSpec.from_yaml(
            _yaml("""
            name: valid-plan
            steps:
              - get_quote
              - get_balance
            """)
        )
        errors = spec.validate()
        assert errors == [], f"Unexpected errors: {errors}"

    def test_unknown_primitive_is_reported(self) -> None:
        spec = WorkflowSpec.from_yaml(
            _yaml("""
            name: bad-plan
            steps:
              - does_not_exist
            """)
        )
        errors = spec.validate()
        assert any("does_not_exist" in e for e in errors)

    def test_empty_steps_is_error(self) -> None:
        spec = WorkflowSpec.from_yaml(
            _yaml("""
            name: empty-plan
            steps: []
            """)
        )
        errors = spec.validate()
        assert any("no steps" in e.lower() for e in errors)

    def test_negative_retry_count_is_error(self) -> None:
        spec = WorkflowSpec.from_yaml(
            _yaml("""
            name: retry-plan
            steps:
              - primitive: get_quote
                inputs:
                  symbol: AAPL
                retry_count: -1
            """)
        )
        errors = spec.validate()
        assert any("retry_count" in e for e in errors)

    def test_mixed_valid_invalid_steps(self) -> None:
        spec = WorkflowSpec.from_yaml(
            _yaml("""
            name: mixed-plan
            steps:
              - get_quote
              - nonexistent_primitive
              - get_balance
            """)
        )
        errors = spec.validate()
        # Only nonexistent_primitive should fail; get_quote and get_balance have executors
        assert len(errors) == 1
        assert "nonexistent_primitive" in errors[0]

    def test_missing_name_key_is_error(self) -> None:
        spec = WorkflowSpec.from_yaml(
            _yaml("""
            steps:
              - get_quote
            """)
        )
        errors = spec.validate()
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


class TestCompilation:
    def test_full_step_fields(self) -> None:
        spec = WorkflowSpec.from_yaml(
            _yaml("""
            name: full-step
            deterministic: false
            steps:
              - primitive: get_quote
                inputs:
                  symbol: AAPL
                version: "1.0.0"
                retry_count: 2
                depends_on: [0]
            """)
        )
        plan = spec.compile()
        assert plan.name == "full-step"
        assert plan.deterministic is False
        step = plan.steps[0]
        assert step.primitive == "get_quote"
        assert step.inputs == {"symbol": "AAPL"}
        assert step.version == "1.0.0"
        assert step.retry_count == 2
        assert step.depends_on == [0]

    def test_short_step_defaults(self) -> None:
        spec = WorkflowSpec.from_yaml("name: t\nsteps:\n  - get_balance\n")
        plan = spec.compile()
        step = plan.steps[0]
        assert step.inputs == {}
        assert step.version == "latest"
        assert step.retry_count == 0

    def test_compact_form_compiles(self) -> None:
        spec = WorkflowSpec.from_yaml("my_workflow:\n  - get_balance\n  - get_positions\n")
        plan = spec.compile()
        assert plan.name == "my_workflow"
        assert len(plan.steps) == 2
        assert plan.deterministic is True


# ---------------------------------------------------------------------------
# End-to-end: spec → execute
# ---------------------------------------------------------------------------


class TestSpecExecution:
    def test_valid_spec_executes_successfully(self) -> None:
        spec = WorkflowSpec.from_yaml(
            _yaml("""
            name: e2e-test
            deterministic: false
            steps:
              - primitive: get_quote
                inputs:
                  symbol: AAPL
              - get_balance
            """)
        )
        dispatch = {
            "get_quote": _fake_ok({"last": 175.0}),
            "get_balance": _fake_ok({"cash": 100000.0}),
        }
        with patch("kodiak.orchestration.dispatch._DISPATCH", dispatch):
            plan = spec.compile()
            result = WorkflowExecutor().execute(plan)

        assert result.success is True
        assert result.steps_completed == 2

    def test_invalid_spec_does_not_execute(self) -> None:
        spec = WorkflowSpec.from_yaml(
            _yaml("""
            name: bad-plan
            steps:
              - does_not_exist
            """)
        )
        errors = spec.validate()
        assert errors  # caller should check errors before compile/execute


# ---------------------------------------------------------------------------
# REST DSL endpoints
# ---------------------------------------------------------------------------


class TestWorkflowDslRest:
    @pytest.fixture()
    def rest_client(self):
        from fastapi.testclient import TestClient
        from kodiak_server.rest.app import create_rest_app

        return TestClient(create_rest_app())

    def test_validate_endpoint_valid_spec(self, rest_client) -> None:
        # Both have MCP tool executors in the dispatch table
        spec_yaml = "name: test\nsteps:\n  - get_quote\n  - get_balance\n"
        resp = rest_client.post("/v1/workflows/validate", json={"spec": spec_yaml})
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True, f"Errors: {body['errors']}"
        assert body["errors"] == []

    def test_validate_endpoint_invalid_spec(self, rest_client) -> None:
        spec_yaml = "name: bad\nsteps:\n  - does_not_exist\n"
        resp = rest_client.post("/v1/workflows/validate", json={"spec": spec_yaml})
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert len(body["errors"]) > 0

    def test_run_spec_endpoint(self, rest_client) -> None:
        spec_yaml = "name: rest-spec-test\ndeterministic: false\nsteps:\n  - get_quote\n"
        with patch(
            "kodiak.orchestration.dispatch._DISPATCH",
            {"get_quote": _fake_ok({"last": 175.0})},
        ):
            resp = rest_client.post("/v1/workflows/run-spec", json={"spec": spec_yaml})

        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["result"]["success"] is True

    def test_run_spec_invalid_spec_returns_errors(self, rest_client) -> None:
        spec_yaml = "name: bad\nsteps:\n  - no_such_prim\n"
        resp = rest_client.post("/v1/workflows/run-spec", json={"spec": spec_yaml})
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert body["result"] is None
