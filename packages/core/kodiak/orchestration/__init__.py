"""Kodiak workflow orchestration engine.

The orchestration layer executes WorkflowPlans — ordered sequences of
registered primitive invocations — with retry logic, structured logging
of plan intent vs actual execution, and failure handling.

Usage::

    from kodiak.orchestration import WorkflowPlan, WorkflowStep, WorkflowExecutor

    plan = WorkflowPlan(
        name="quote-then-size",
        steps=[
            WorkflowStep(primitive="get_quote", inputs={"symbol": "AAPL"}),
            WorkflowStep(
                primitive="calculate_position_size",
                inputs={"symbol": "AAPL", "target_value": 5000.0},
            ),
        ],
    )
    result = WorkflowExecutor().execute(plan)
"""

from kodiak.orchestration.executor import WorkflowExecutor
from kodiak.orchestration.plan import WorkflowPlan, WorkflowStep
from kodiak.orchestration.result import StepResult, WorkflowResult

__all__ = [
    "StepResult",
    "WorkflowExecutor",
    "WorkflowPlan",
    "WorkflowResult",
    "WorkflowStep",
]
