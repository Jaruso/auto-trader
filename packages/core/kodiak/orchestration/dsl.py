"""Financial workflow DSL — parse, validate, and compile workflow specs.

Supported spec formats
----------------------

**Full form** (YAML or JSON):

.. code-block:: yaml

    name: quote-and-size
    deterministic: true
    steps:
      - primitive: get_quote
        inputs:
          symbol: AAPL
        retry_count: 1
      - primitive: calculate_position_size
        inputs:
          symbol: AAPL
          target_value: 5000.0

**Short form** (steps as bare primitive names):

.. code-block:: yaml

    name: portfolio-check
    steps:
      - get_balance
      - get_positions
      - get_portfolio

**Compact form** (workflow name as top-level key):

.. code-block:: yaml

    portfolio_check:
      - get_balance
      - get_positions
      - get_portfolio

All three forms compile to a ``WorkflowPlan`` and run through
``WorkflowExecutor`` identically.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from kodiak.orchestration.plan import WorkflowPlan, WorkflowStep


class WorkflowSpecError(ValueError):
    """Raised when a workflow spec cannot be parsed or fails validation."""


class WorkflowSpec:
    """Parses YAML/JSON workflow specs and compiles them into WorkflowPlans.

    Usage::

        spec = WorkflowSpec.from_file("workflows/portfolio-check.yaml")
        errors = spec.validate()
        if not errors:
            plan = spec.compile()
            result = WorkflowExecutor().execute(plan)
    """

    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, text: str) -> WorkflowSpec:
        """Parse a YAML string into a WorkflowSpec."""
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise WorkflowSpecError(f"Invalid YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise WorkflowSpecError("Workflow spec must be a YAML/JSON object.")
        return cls(data)

    @classmethod
    def from_json(cls, text: str) -> WorkflowSpec:
        """Parse a JSON string into a WorkflowSpec."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise WorkflowSpecError(f"Invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise WorkflowSpecError("Workflow spec must be a YAML/JSON object.")
        return cls(data)

    @classmethod
    def from_file(cls, path: str | Path) -> WorkflowSpec:
        """Load a workflow spec from a YAML or JSON file."""
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        if path.suffix in {".yaml", ".yml"}:
            return cls.from_yaml(text)
        if path.suffix == ".json":
            return cls.from_json(text)
        # Try YAML first, then JSON for unknown extensions
        try:
            return cls.from_yaml(text)
        except WorkflowSpecError:
            return cls.from_json(text)

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def _normalized(self) -> dict[str, Any]:
        """Convert any supported format into the canonical dict form."""
        raw = self._raw

        # Compact form: {"workflow_name": ["step1", "step2", ...]}
        # Detected when there is exactly one key and its value is a list.
        if len(raw) == 1:
            key, value = next(iter(raw.items()))
            if isinstance(value, list) and key not in ("steps", "name"):
                return {"name": key, "steps": value, "deterministic": True}

        # Full or short form: expects "name" and "steps" keys.
        if "name" not in raw or "steps" not in raw:
            raise WorkflowSpecError(
                "Workflow spec must have 'name' and 'steps' keys, "
                "or use the compact form {workflow_name: [step, ...]}."
            )
        return raw

    def _parse_step(self, raw_step: Any, idx: int) -> WorkflowStep:
        """Parse a single step from a string or dict."""
        if isinstance(raw_step, str):
            return WorkflowStep(primitive=raw_step)
        if isinstance(raw_step, dict):
            if "primitive" not in raw_step:
                raise WorkflowSpecError(
                    f"Step {idx}: dict step must have a 'primitive' key."
                )
            return WorkflowStep.from_dict(raw_step)
        raise WorkflowSpecError(
            f"Step {idx}: expected a primitive name (string) or a step dict, "
            f"got {type(raw_step).__name__}."
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty list means valid).

        Checks performed:
        - Spec structure is parseable
        - Steps list is non-empty
        - Each step has an executor (registered primitive or MCP tool)
        - retry_count is non-negative
        """
        errors: list[str] = []
        try:
            normalized = self._normalized()
        except WorkflowSpecError as exc:
            return [str(exc)]

        steps_raw = normalized.get("steps", [])
        if not steps_raw:
            errors.append("Workflow has no steps.")
            return errors

        from kodiak.mcp.tools import _ALL_TOOLS

        known_primitives = {fn.__name__ for fn in _ALL_TOOLS}

        for idx, raw_step in enumerate(steps_raw):
            try:
                step = self._parse_step(raw_step, idx)
            except WorkflowSpecError as exc:
                errors.append(str(exc))
                continue

            if step.retry_count < 0:
                errors.append(f"Step {idx} ({step.primitive}): retry_count must be >= 0.")

            if step.primitive not in known_primitives:
                errors.append(
                    f"Step {idx}: no executor found for '{step.primitive}'. "
                    "Check that the primitive name matches a registered MCP tool."
                )

        return errors

    # ------------------------------------------------------------------
    # Compilation
    # ------------------------------------------------------------------

    def compile(self) -> WorkflowPlan:
        """Compile the spec into a WorkflowPlan ready for execution.

        Raises WorkflowSpecError if the spec is structurally invalid.
        Call validate() first to get human-readable error messages.
        """
        try:
            normalized = self._normalized()
        except WorkflowSpecError:
            raise

        name = normalized["name"]
        steps_raw = normalized.get("steps", [])
        deterministic = bool(normalized.get("deterministic", True))

        steps = [self._parse_step(raw, idx) for idx, raw in enumerate(steps_raw)]

        return WorkflowPlan(name=name, steps=steps, deterministic=deterministic)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return the raw parsed spec as a dict."""
        return dict(self._raw)
