"""Tests for the Kodiak primitive SDK — registry, versioning, and deprecation."""

from __future__ import annotations

import pytest
from kodiak.primitives import (
    ExecutionMode,
    LatencyClass,
    Primitive,
    PrimitiveRegistry,
    RiskLevel,
    get,
    list_all,
    list_versions,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make(
    name: str,
    version: str = "1.0.0",
    risk: RiskLevel = RiskLevel.READ_ONLY,
    deprecated: bool = False,
    deprecation_message: str | None = None,
    latency_class: LatencyClass | None = None,
) -> Primitive:
    return Primitive(
        name=name,
        version=version,
        description=f"Test primitive: {name} v{version}",
        input_schema={"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
        output_schema={"type": "object"},
        permissions=["test:read"],
        risk_level=risk,
        execution_mode=ExecutionMode.SYNC,
        tags=["test"],
        deprecated=deprecated,
        deprecation_message=deprecation_message,
        latency_class=latency_class,
    )


# ---------------------------------------------------------------------------
# PrimitiveRegistry — basic registration
# ---------------------------------------------------------------------------


class TestPrimitiveRegistry:
    def test_register_and_get(self) -> None:
        reg = PrimitiveRegistry()
        p = _make("test_alpha")
        reg.register(p)
        assert reg.get("test_alpha") is p

    def test_get_missing_returns_none(self) -> None:
        reg = PrimitiveRegistry()
        assert reg.get("nonexistent") is None

    def test_get_pinned_missing_version_returns_none(self) -> None:
        reg = PrimitiveRegistry()
        reg.register(_make("foo", "1.0.0"))
        assert reg.get("foo", "2.0.0") is None

    def test_list_is_sorted_by_name(self) -> None:
        reg = PrimitiveRegistry()
        reg.register(_make("z_last"))
        reg.register(_make("a_first"))
        reg.register(_make("m_middle"))
        names = [p.name for p in reg.list()]
        assert names == sorted(names)

    def test_len_counts_unique_names(self) -> None:
        reg = PrimitiveRegistry()
        reg.register(_make("a", "1.0.0"))
        reg.register(_make("a", "2.0.0"))
        reg.register(_make("b", "1.0.0"))
        assert len(reg) == 2


# ---------------------------------------------------------------------------
# Version resolution
# ---------------------------------------------------------------------------


class TestVersionResolution:
    def test_latest_returns_highest_semver(self) -> None:
        reg = PrimitiveRegistry()
        reg.register(_make("alpha", "1.0.0"))
        reg.register(_make("alpha", "2.0.0"))
        reg.register(_make("alpha", "1.5.0"))
        assert reg.get("alpha").version == "2.0.0"

    def test_pinned_version(self) -> None:
        reg = PrimitiveRegistry()
        reg.register(_make("beta", "1.0.0"))
        reg.register(_make("beta", "2.0.0"))
        assert reg.get("beta", "1.0.0").version == "1.0.0"
        assert reg.get("beta", "2.0.0").version == "2.0.0"

    def test_latest_skips_deprecated(self) -> None:
        reg = PrimitiveRegistry()
        reg.register(_make("gamma", "1.0.0"))
        reg.register(_make("gamma", "2.0.0", deprecated=True))
        assert reg.get("gamma").version == "1.0.0"

    def test_latest_falls_back_to_deprecated_when_all_deprecated(self) -> None:
        reg = PrimitiveRegistry()
        reg.register(_make("delta", "1.0.0", deprecated=True))
        reg.register(_make("delta", "2.0.0", deprecated=True))
        # Falls back to highest deprecated version
        assert reg.get("delta").version == "2.0.0"

    def test_list_versions_newest_first(self) -> None:
        reg = PrimitiveRegistry()
        reg.register(_make("epsilon", "1.0.0"))
        reg.register(_make("epsilon", "3.0.0"))
        reg.register(_make("epsilon", "2.0.0"))
        versions = [p.version for p in reg.list_versions("epsilon")]
        assert versions == ["3.0.0", "2.0.0", "1.0.0"]

    def test_list_versions_unknown_name_returns_empty(self) -> None:
        reg = PrimitiveRegistry()
        assert reg.list_versions("unknown") == []

    def test_list_returns_latest_per_name(self) -> None:
        reg = PrimitiveRegistry()
        reg.register(_make("x", "1.0.0"))
        reg.register(_make("x", "2.0.0"))
        reg.register(_make("y", "1.0.0"))
        result = reg.list()
        assert len(result) == 2
        x_entry = next(p for p in result if p.name == "x")
        assert x_entry.version == "2.0.0"


# ---------------------------------------------------------------------------
# Deprecation
# ---------------------------------------------------------------------------


class TestDeprecation:
    def test_deprecated_flag_in_to_dict(self) -> None:
        p = _make("dep", deprecated=True, deprecation_message="Use v2")
        d = p.to_dict()
        assert d["deprecated"] is True
        assert d["deprecation_message"] == "Use v2"

    def test_non_deprecated_has_no_message_key(self) -> None:
        p = _make("active")
        d = p.to_dict()
        assert d["deprecated"] is False
        assert "deprecation_message" not in d

    def test_registry_list_excludes_deprecated_latest(self) -> None:
        """list() should surface the latest non-deprecated for each name."""
        reg = PrimitiveRegistry()
        reg.register(_make("foo", "1.0.0"))
        reg.register(_make("foo", "2.0.0", deprecated=True))
        result = reg.list()
        assert any(p.name == "foo" and p.version == "1.0.0" for p in result)

    def test_pinned_deprecated_version_still_retrievable(self) -> None:
        reg = PrimitiveRegistry()
        reg.register(_make("bar", "1.0.0", deprecated=True, deprecation_message="old"))
        p = reg.get("bar", "1.0.0")
        assert p is not None
        assert p.deprecated is True
        assert p.deprecation_message == "old"


# ---------------------------------------------------------------------------
# LatencyClass
# ---------------------------------------------------------------------------


class TestLatencyClass:
    def test_latency_class_in_to_dict(self) -> None:
        p = _make("fast_action", latency_class=LatencyClass.REALTIME)
        assert p.to_dict()["latency_class"] == "realtime"

    def test_no_latency_class_omitted_from_dict(self) -> None:
        p = _make("slow_action")
        assert "latency_class" not in p.to_dict()

    def test_latency_class_enum_values(self) -> None:
        assert LatencyClass.REALTIME.value == "realtime"
        assert LatencyClass.FAST.value == "fast"
        assert LatencyClass.BATCH.value == "batch"


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
            latency_class=LatencyClass.FAST,
        )
        d = p.to_dict()
        assert d["name"] == "my_action"
        assert d["version"] == "1.2.3"
        assert d["risk_level"] == "high"
        assert d["execution_mode"] == "deferred"
        assert d["permissions"] == ["scope:write"]
        assert d["tags"] == ["foo", "bar"]
        assert d["latency_class"] == "fast"
        assert "input_schema" in d
        assert "output_schema" in d

    def test_risk_level_serialized_as_string(self) -> None:
        p = _make("x", risk=RiskLevel.READ_ONLY)
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

    def test_get_quote_is_read_only_realtime(self) -> None:
        p = get("get_quote")
        assert p is not None
        assert p.risk_level == RiskLevel.READ_ONLY
        assert p.latency_class == LatencyClass.REALTIME

    def test_place_order_is_high_risk_fast(self) -> None:
        p = get("place_order")
        assert p is not None
        assert p.risk_level == RiskLevel.HIGH
        assert p.latency_class == LatencyClass.FAST
        assert "confirm_execution" in p.permissions

    def test_run_backtest_is_medium_risk_batch(self) -> None:
        p = get("run_backtest")
        assert p is not None
        assert p.risk_level == RiskLevel.MEDIUM
        assert p.latency_class == LatencyClass.BATCH

    def test_get_pinned_version(self) -> None:
        p = get("get_quote", version="1.0.0")
        assert p is not None
        assert p.version == "1.0.0"

    def test_get_unknown_version_returns_none(self) -> None:
        assert get("get_quote", version="99.0.0") is None

    def test_list_versions_returns_all(self) -> None:
        versions = list_versions("get_quote")
        assert len(versions) >= 1
        assert versions[0].name == "get_quote"

    def test_all_builtins_not_deprecated(self) -> None:
        for p in list_all():
            assert not p.deprecated, f"{p.name} should not be deprecated"

    def test_all_builtins_have_description(self) -> None:
        for p in list_all():
            assert p.description, f"{p.name} has no description"

    def test_all_builtins_have_latency_class(self) -> None:
        for p in list_all():
            assert p.latency_class is not None, f"{p.name} has no latency_class"


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
        assert body["latency_class"] == "realtime"

    def test_get_primitive_pinned_version(self, rest_client) -> None:
        resp = rest_client.get("/v1/primitives/get_quote?version=1.0.0")
        assert resp.status_code == 200
        assert resp.json()["version"] == "1.0.0"

    def test_get_unknown_version_returns_404(self, rest_client) -> None:
        resp = rest_client.get("/v1/primitives/get_quote?version=99.0.0")
        assert resp.status_code == 404

    def test_get_missing_primitive_returns_404(self, rest_client) -> None:
        resp = rest_client.get("/v1/primitives/does_not_exist")
        assert resp.status_code == 404

    def test_list_versions_endpoint(self, rest_client) -> None:
        resp = rest_client.get("/v1/primitives/get_quote/versions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "get_quote"
        assert len(body["versions"]) >= 1

    def test_list_versions_unknown_returns_404(self, rest_client) -> None:
        resp = rest_client.get("/v1/primitives/unknown_primitive/versions")
        assert resp.status_code == 404

    def test_rest_primitives_match_registry(self, rest_client) -> None:
        resp = rest_client.get("/v1/primitives/")
        rest_names = {p["name"] for p in resp.json()["primitives"]}
        registry_names = {p.name for p in list_all()}
        assert rest_names == registry_names
