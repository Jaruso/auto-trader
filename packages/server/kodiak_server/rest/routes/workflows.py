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
