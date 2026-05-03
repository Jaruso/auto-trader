"""Primitive dispatch table for the workflow executor.

Maps primitive names to their callable MCP tool functions. Built lazily
on first use to avoid circular imports and slow startup.

The executor calls dispatch.invoke(name, inputs) which:
1. Looks up the MCP tool function by primitive name
2. Calls it with **inputs
3. Parses the JSON result and detects AppError responses
4. Returns (success: bool, output: Any)
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

_DISPATCH: dict[str, Callable[..., str]] = {}
_initialized = False


def _build_dispatch() -> None:
    """Populate dispatch table from all MCP tool functions."""
    global _initialized
    if _initialized:
        return
    from kodiak.mcp.tools import _ALL_TOOLS

    for fn in _ALL_TOOLS:
        _DISPATCH[fn.__name__] = fn

    _initialized = True


def register_executor(name: str, fn: Callable[..., str]) -> None:
    """Register a custom executor for a primitive name.

    Use this to override the default MCP-tool-based dispatch.
    """
    _DISPATCH[name] = name  # type: ignore[assignment]
    _DISPATCH[name] = fn


def has_executor(name: str) -> bool:
    """Return True if an executor is registered for the given primitive name."""
    _build_dispatch()
    return name in _DISPATCH


def invoke(name: str, inputs: dict[str, Any]) -> tuple[bool, Any]:
    """Invoke a primitive executor and return (success, parsed_output).

    Success is False if:
    - No executor is registered for the name
    - The executor raises an exception (propagated to caller)
    - The executor returns AppError JSON (has "error" + "message" keys)
    """
    _build_dispatch()
    fn = _DISPATCH.get(name)
    if fn is None:
        return False, {"error": "NO_EXECUTOR", "message": f"No executor registered for primitive '{name}'."}

    result_str = fn(**inputs)
    try:
        output = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        output = result_str

    # AppError responses have a string "error" key + "message" key
    success = not (
        isinstance(output, dict)
        and isinstance(output.get("error"), str)
        and "message" in output
    )
    return success, output
