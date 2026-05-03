"""Workflow executor — runs a WorkflowPlan step by step.

Execution model:
- Steps run sequentially in list order (DAG planned, depends_on reserved).
- On transient failure (exception), retries up to step.retry_count times.
- On AppError response (non-exception failure), the step fails immediately
  without retrying (business errors are deterministic).
- If any step fails, the run halts and WorkflowResult.success is False.
- All step outcomes are recorded in WorkflowResult.step_results.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from kodiak.orchestration.dispatch import has_executor, invoke
from kodiak.orchestration.plan import WorkflowPlan, WorkflowStep
from kodiak.orchestration.result import StepResult, WorkflowResult
from kodiak.primitives import get as get_primitive

logger = logging.getLogger("kodiak.orchestration")


class WorkflowExecutor:
    """Executes a WorkflowPlan and returns a WorkflowResult."""

    def execute(self, plan: WorkflowPlan) -> WorkflowResult:
        logger.info(
            "workflow_start",
            extra={"plan_name": plan.name, "steps_total": len(plan.steps)},
        )

        started = time.perf_counter()

        # Deterministic mode: validate all primitives are known before running.
        if plan.deterministic:
            error = self._validate_plan(plan)
            if error:
                logger.error("workflow_validation_failed", extra={"reason": error})
                return WorkflowResult(
                    plan_name=plan.name,
                    success=False,
                    steps_completed=0,
                    steps_total=len(plan.steps),
                    total_duration_ms=0.0,
                )

        step_results: list[StepResult] = []
        completed = 0

        for idx, step in enumerate(plan.steps):
            result = self._execute_step(idx, step)
            step_results.append(result)

            if result.success:
                completed += 1
                logger.info(
                    "workflow_step_ok",
                    extra={
                        "plan_name": plan.name,
                        "step_index": idx,
                        "primitive": step.primitive,
                        "version": result.version_resolved,
                        "attempts": result.attempts,
                        "duration_ms": result.duration_ms,
                    },
                )
            else:
                logger.warning(
                    "workflow_step_failed",
                    extra={
                        "plan_name": plan.name,
                        "step_index": idx,
                        "primitive": step.primitive,
                        "error": result.error,
                        "attempts": result.attempts,
                    },
                )
                break  # halt on first failure

        total_ms = round((time.perf_counter() - started) * 1000, 2)
        overall_success = completed == len(plan.steps)

        logger.info(
            "workflow_complete",
            extra={
                "plan_name": plan.name,
                "success": overall_success,
                "steps_completed": completed,
                "steps_total": len(plan.steps),
                "total_duration_ms": total_ms,
            },
        )

        return WorkflowResult(
            plan_name=plan.name,
            success=overall_success,
            steps_completed=completed,
            steps_total=len(plan.steps),
            step_results=step_results,
            total_duration_ms=total_ms,
        )

    def _validate_plan(self, plan: WorkflowPlan) -> str | None:
        """Return an error message if any step references an unknown primitive."""
        for idx, step in enumerate(plan.steps):
            primitive = get_primitive(step.primitive, step.version)
            if primitive is None:
                return (
                    f"Step {idx}: primitive '{step.primitive}' version '{step.version}' "
                    "is not registered."
                )
            if not has_executor(step.primitive):
                return f"Step {idx}: no executor registered for primitive '{step.primitive}'."
        return None

    def _execute_step(self, idx: int, step: WorkflowStep) -> StepResult:
        primitive = get_primitive(step.primitive, step.version)
        version_resolved = primitive.version if primitive else step.version

        step_started = time.perf_counter()
        attempts = 0
        last_error: str | None = None
        output: Any = None
        success = False

        max_attempts = 1 + step.retry_count
        for attempt in range(max_attempts):
            attempts = attempt + 1
            try:
                success, output = invoke(step.primitive, step.inputs)
                if success:
                    break
                # AppError response — don't retry business-level errors
                last_error = _extract_error_message(output)
                break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                if attempt < max_attempts - 1:
                    logger.debug(
                        "workflow_step_retry",
                        extra={"step_index": idx, "attempt": attempt + 1, "error": last_error},
                    )
                    time.sleep(0.1 * (attempt + 1))  # linear back-off: 100ms, 200ms, …

        duration_ms = round((time.perf_counter() - step_started) * 1000, 2)
        return StepResult(
            step_index=idx,
            primitive=step.primitive,
            version_resolved=version_resolved,
            planned_inputs=step.inputs,
            output=output,
            success=success,
            error=last_error if not success else None,
            attempts=attempts,
            duration_ms=duration_ms,
        )


def _extract_error_message(output: Any) -> str:
    if isinstance(output, dict):
        return output.get("message") or output.get("error") or str(output)
    return str(output)
