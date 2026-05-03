"""Tests for the Kodiak primitive SDK."""

from __future__ import annotations

import pytest
from kodiak.primitives import ExecutionMode, Primitive, PrimitiveRegistry, RiskLevel, get, list_all

# ---------------------------------------------------------------------------
# PrimitiveRegistry unit tests
# ---------------------------------------------------------------------------


class TestPrimitiveRegistry:
    def _make(self, name: str, risk: RiskLevel = RiskLevel.READ_ONLY) -> Primitive:
        return Primitive(
            name=name,
            version="1.0.0",
            description=f"Test primitive: {name}",
            input_schema={"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
            output_schema={"type": "object"},
            permissions=["test:read"],
            risk_level=risk,
            execution_mode=ExecutionMode.SYNC,
            tags=["test"],
        )

    def test_register_and_get(self) -> None:
        reg = PrimitiveRegistry()
        p = self._make("test_alpha")
        reg.register(p)
        assert reg.get("test_alpha") is p

    def test_get_missing_returns_none(self) -> None:
        reg = PrimitiveRegistry()
        assert reg.get("nonexistent") is None

    def test_list_is_sorted_by_name(self) -> None:
        reg = PrimitiveRegistry()
        reg.register(self._make("z_last"))
        reg.register(self._make("a_first"))
        reg.register(self._make("m_middle"))
        names = [p.name for p in reg.list()]
        assert names == sorted(names)

    def test_register_overwrites(self) -> None:
        reg = PrimitiveRegistry()
        reg.register(self._make("dup"))
        v2 = Primitive(
            name="dup",
            version="2.0.0",
            description="v2",
            input_schema={},
            output_schema={},
            permissions=[],
            risk_level=RiskLevel.LOW,
            execution_mode=ExecutionMode.SYNC,
        )
        reg.register(v2)
        assert reg.get("dup").version == "2.0.0"

    def test_len(self) -> None:
        reg = PrimitiveRegistry()
        reg.register(self._make("a"))
        reg.register(self._make("b"))
        assert len(reg) == 2


# ---------------------------------------------------------------------------
# Primitive.to_dict
# ---------------------------------------------------------------------------


class TestPrimitiveSerialization:
    def test_to_dict_has_all_fields(self) -> None:
        p = Primitive(
            name="my_action",
            version="1.2.3",
            description="Does a thing",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            permissions=["scope:write"],
            risk_level=RiskLevel.HIGH,
            execution_mode=ExecutionMode.DEFERRED,
            tags=["foo", "bar"],
        )
        d = p.to_dict()
        assert d["name"] == "my_action"
        assert d["version"] == "1.2.3"
        assert d["risk_level"] == "high"
        assert d["execution_mode"] == "deferred"
        assert d["permissions"] == ["scope:write"]
        assert d["tags"] == ["foo", "bar"]
        assert "input_schema" in d
        assert "output_schema" in d

    def test_risk_level_serialized_as_string(self) -> None:
        p = Primitive(
            name="x",
            version="1.0.0",
            description="",
            input_schema={},
            output_schema={},
            permissions=[],
            risk_level=RiskLevel.READ_ONLY,
            execution_mode=ExecutionMode.SYNC,
        )
        assert p.to_dict()["risk_level"] == "read_only"


# ---------------------------------------------------------------------------
# Built-in primitives
# ---------------------------------------------------------------------------


class TestBuiltinPrimitives:
    def test_builtins_registered_in_global_registry(self) -> None:
        names = {p.name for p in list_all()}
        assert "get_quote" in names
        assert "place_order" in names
        assert "run_backtest" in names

    def test_get_quote_is_read_only(self) -> None:
        p = get("get_quote")
        assert p is not None
        assert p.risk_level == RiskLevel.READ_ONLY
        assert p.execution_mode == ExecutionMode.SYNC

    def test_place_order_is_high_risk(self) -> None:
        p = get("place_order")
        assert p is not None
        assert p.risk_level == RiskLevel.HIGH
        assert "confirm_execution" in p.permissions

    def test_run_backtest_is_medium_risk(self) -> None:
        p = get("run_backtest")
        assert p is not None
        assert p.risk_level == RiskLevel.MEDIUM
        assert "backtests:run" in p.permissions

    def test_get_quote_input_schema_requires_symbol(self) -> None:
        p = get("get_quote")
        assert p is not None
        assert "symbol" in p.input_schema.get("required", [])

    def test_place_order_input_schema_requires_confirm(self) -> None:
        p = get("place_order")
        assert p is not None
        assert "confirm_execution" in p.input_schema.get("required", [])

    def test_all_builtins_have_version(self) -> None:
        for p in list_all():
            assert p.version, f"{p.name} has no version"

    def test_all_builtins_have_description(self) -> None:
        for p in list_all():
            assert p.description, f"{p.name} has no description"


# ---------------------------------------------------------------------------
# RiskLevel / ExecutionMode enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_risk_level_values(self) -> None:
        assert RiskLevel.READ_ONLY.value == "read_only"
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"

    def test_execution_mode_values(self) -> None:
        assert ExecutionMode.SYNC.value == "sync"
        assert ExecutionMode.DEFERRED.value == "deferred"

    def test_risk_level_from_string(self) -> None:
        assert RiskLevel("high") == RiskLevel.HIGH

    def test_execution_mode_from_string(self) -> None:
        assert ExecutionMode("sync") == ExecutionMode.SYNC


# ---------------------------------------------------------------------------
# REST endpoint parity (via FastAPI test client)
# ---------------------------------------------------------------------------


class TestPrimitivesRestParity:
    @pytest.fixture()
    def rest_client(self):
        from fastapi.testclient import TestClient
        from kodiak_server.rest.app import create_rest_app

        return TestClient(create_rest_app())

    def test_list_primitives_returns_200(self, rest_client) -> None:
        resp = rest_client.get("/v1/primitives/")
        assert resp.status_code == 200
        body = resp.json()
        assert "primitives" in body
        names = {p["name"] for p in body["primitives"]}
        assert "get_quote" in names
        assert "place_order" in names
        assert "run_backtest" in names

    def test_get_primitive_returns_200(self, rest_client) -> None:
        resp = rest_client.get("/v1/primitives/get_quote")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "get_quote"
        assert body["risk_level"] == "read_only"

    def test_get_missing_primitive_returns_404(self, rest_client) -> None:
        resp = rest_client.get("/v1/primitives/does_not_exist")
        assert resp.status_code == 404

    def test_rest_primitives_match_registry(self, rest_client) -> None:
        resp = rest_client.get("/v1/primitives/")
        rest_names = {p["name"] for p in resp.json()["primitives"]}
        registry_names = {p.name for p in list_all()}
        assert rest_names == registry_names
