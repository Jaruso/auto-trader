"""Primitives REST API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/primitives")


@router.get("/")
def list_primitives(
    include_deprecated: bool = Query(False, description="Include deprecated primitives in results"),
) -> dict[str, Any]:
    """List all registered financial action primitives (latest version of each)."""
    from kodiak.primitives import list_all

    primitives = list_all()
    if not include_deprecated:
        primitives = [p for p in primitives if not p.deprecated]
    return {"primitives": [p.to_dict() for p in primitives]}


@router.get("/{name}/versions")
def list_primitive_versions(name: str) -> dict[str, Any]:
    """List all registered versions of a named primitive, newest first."""
    from kodiak.primitives import list_versions

    versions = list_versions(name)
    if not versions:
        raise HTTPException(status_code=404, detail=f"Primitive '{name}' not found.")
    return {"name": name, "versions": [p.to_dict() for p in versions]}


@router.get("/{name}")
def get_primitive(
    name: str,
    version: str = Query("latest", description="Version string or 'latest'"),
) -> dict[str, Any]:
    """Get the descriptor for a single primitive by name and optional version."""
    from kodiak.primitives import get

    primitive = get(name, version=version)
    if primitive is None:
        detail = f"Primitive '{name}' version '{version}' not found."
        raise HTTPException(status_code=404, detail=detail)
    return primitive.to_dict()
