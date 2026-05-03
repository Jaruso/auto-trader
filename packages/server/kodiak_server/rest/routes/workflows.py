"""Workflow orchestration REST API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/workflows")


class StepRequest(BaseModel):
    primitive: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    version: str = "latest"
    retry_count: int = Field(default=0, ge=0)
    depends_on: list[int] = Field(default_factory=list)


class RunWorkflowRequest(BaseModel):
    plan_name: str
    steps: list[StepRequest]
    deterministic: bool = True


class WorkflowSpecRequest(BaseModel):
    spec: str = Field(..., description="YAML or JSON workflow spec string.")


@router.post("/run")
def run_workflow(req: RunWorkflowRequest) -> dict[str, Any]:
    """Execute a workflow plan by sequencing registered primitives.

    Steps run in order. If any step fails, execution halts and the response
    includes the partial results with success=false.
    """
    from kodiak.orchestration import WorkflowExecutor, WorkflowPlan, WorkflowStep

    plan = WorkflowPlan(
        name=req.plan_name,
        steps=[
            WorkflowStep(
                primitive=s.primitive,
                inputs=s.inputs,
                version=s.version,
                retry_count=s.retry_count,
                depends_on=s.depends_on,
            )
            for s in req.steps
        ],
        deterministic=req.deterministic,
    )
    result = WorkflowExecutor().execute(plan)
    return result.to_dict()


@router.post("/validate")
def validate_workflow_spec(req: WorkflowSpecRequest) -> dict[str, Any]:
    """Validate a YAML or JSON workflow spec without executing it.

    Returns a validation report with any errors found. An empty errors list
    means the spec is ready to run.
    """
    from kodiak.orchestration import WorkflowSpec, WorkflowSpecError

    try:
        spec = WorkflowSpec.from_yaml(req.spec)
    except WorkflowSpecError:
        try:
            spec = WorkflowSpec.from_json(req.spec)
        except WorkflowSpecError as exc:
            return {"valid": False, "errors": [str(exc)]}

    errors = spec.validate()
    return {"valid": len(errors) == 0, "errors": errors}


@router.post("/run-spec")
def run_workflow_spec(req: WorkflowSpecRequest) -> dict[str, Any]:
    """Parse, validate, and execute a YAML or JSON workflow spec.

    If validation fails, returns errors without executing.
    """
    from kodiak.orchestration import WorkflowExecutor, WorkflowSpec, WorkflowSpecError

    try:
        spec = WorkflowSpec.from_yaml(req.spec)
    except WorkflowSpecError:
        try:
            spec = WorkflowSpec.from_json(req.spec)
        except WorkflowSpecError as exc:
            return {"valid": False, "errors": [str(exc)], "result": None}

    errors = spec.validate()
    if errors:
        return {"valid": False, "errors": errors, "result": None}

    plan = spec.compile()
    result = WorkflowExecutor().execute(plan)
    return {"valid": True, "errors": [], "result": result.to_dict()}
