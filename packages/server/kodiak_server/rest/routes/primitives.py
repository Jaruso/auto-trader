"""Primitives REST API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/primitives")


@router.get("/")
def list_primitives() -> dict[str, Any]:
    """List all registered financial action primitives."""
    from kodiak.primitives import list_all

    return {"primitives": [p.to_dict() for p in list_all()]}


@router.get("/{name}")
def get_primitive(name: str) -> dict[str, Any]:
    """Get the descriptor for a single primitive by name."""
    from kodiak.primitives import get

    primitive = get(name)
    if primitive is None:
        raise HTTPException(status_code=404, detail=f"Primitive '{name}' not found.")
    return primitive.to_dict()
