"""Optional adapter: bridge planner steps to distributed workers.

``DistributedAdapter`` sits between the orchestrator's ``PlanStep`` (or any
caller) and the master coordinator, providing a simple ``submit_and_await``
loop that submits a typed task and polls coordinator dispatches until the
task completes, fails with retries exhausted, or is cancelled.  It never
executes work itself: the coordinator's injected transport handles I/O.

Deterministic offline tests submit one task, advance the coordinator, and
call ``accept_result`` directly; this adapter is only needed when a single
async entry-point is more natural (API integration, scripted runs).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from app.core.planner import PlanStep
from app.distributed.coordinator import DistributedCoordinator
from app.distributed.models import (
    DistributedTask,
    DistributedTaskStatus,
)

_poll_interval: float = 0.02
_max_polls: int = 500


@dataclass(frozen=True)
class DistributedExecutionResult:
    """Returned to the orchestrator/adapter caller for one task execution."""

    success: bool
    output: str | None = None
    error: str | None = None
    task_id: UUID | None = None
    worker_id: UUID | None = None
    attempts: int = 0

    @classmethod
    def ok(
        cls,
        *,
        output: str | None = None,
        task_id: UUID | None = None,
        worker_id: UUID | None = None,
        attempts: int = 1,
    ) -> "DistributedExecutionResult":
        return cls(
            success=True,
            output=output,
            task_id=task_id,
            worker_id=worker_id,
            attempts=attempts,
        )

    @classmethod
    def fail(
        cls,
        *,
        error: str,
        task_id: UUID | None = None,
        worker_id: UUID | None = None,
        attempts: int = 0,
    ) -> "DistributedExecutionResult":
        return cls(
            success=False,
            error=error,
            task_id=task_id,
            worker_id=worker_id,
            attempts=attempts,
        )


class DistributedAdapter:
    """Optional convenience: ``submit_and_await`` performs one bounded loop.

    The adapter is a thin boundary that never owns the coordinator, transport
    or scheduler.  It documents the pattern but does not replace the master's
    own loop (``dispatch_next`` → ``dispatch_async`` → ``accept_result``).
    """

    def __init__(
        self,
        coordinator: DistributedCoordinator,
        *,
        poll_interval: float = _poll_interval,
        max_polls: int = _max_polls,
        enabled: bool = True,
    ) -> None:
        self._coordinator = coordinator
        self._poll_interval = poll_interval
        self._max_polls = max_polls
        self._enabled = enabled
        self._logger = logging.getLogger(__name__)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def coordinator(self) -> DistributedCoordinator:
        return self._coordinator

    # ------------------------------------------------------------------
    # Public convenience API
    # ------------------------------------------------------------------

    def task_for_step(self, step: PlanStep) -> DistributedTask:
        """Create a typed distributed task from a planner step."""
        return DistributedTask(
            task_type="analysis",
            description=step.description,
            required_capabilities=step.required_capabilities,
            context={
                "step_id": str(step.step_id),
                "description": step.description,
            },
        )

    async def submit_and_await_async(
        self,
        task: DistributedTask,
        *,
        poll_interval: float | None = None,
        max_polls: int | None = None,
    ) -> DistributedExecutionResult:
        """Async version of ``submit_and_await`` for integration use."""
        interval = poll_interval if poll_interval is not None else self._poll_interval
        budget = max_polls if max_polls is not None else self._max_polls

        if not self._enabled:
            return DistributedExecutionResult.fail(
                error="distributed execution is disabled",
                task_id=task.distributed_task_id,
            )

        self._coordinator.submit(task)
        polls = 0

        while polls < budget:
            status = self._coordinator.status_for(task.distributed_task_id)

            if status in (
                DistributedTaskStatus.COMPLETED,
                DistributedTaskStatus.FAILED,
                DistributedTaskStatus.CANCELLED,
            ):
                return self._make_result(task)

            assignment = self._coordinator.dispatch_next()
            if assignment is None:
                polls += 1
                await asyncio.sleep(interval)
                continue

            result = await self._coordinator.dispatch_async(assignment, task)
            self._coordinator.accept_result(result)

        self._logger.warning(
            "poll budget exhausted for task %s after %d polls",
            task.distributed_task_id,
            polls,
        )
        return DistributedExecutionResult.fail(
            error="poll budget exhausted",
            task_id=task.distributed_task_id,
        )

    def _make_result(self, task: DistributedTask) -> DistributedExecutionResult:
        if task.status is DistributedTaskStatus.COMPLETED:
            # Walk completed_results to find the outcome for this task.
            result = next(
                (
                    r
                    for r in self._coordinator.completed_results
                    if r.distributed_task_id == task.distributed_task_id
                ),
                None,
            )
            return DistributedExecutionResult.ok(
                output=result.output if result else None,
                task_id=task.distributed_task_id,
                worker_id=task.last_assigned_worker_id,
                attempts=task.attempt_count,
            )
        return DistributedExecutionResult.fail(
            error=task.last_error or "task failed",
            task_id=task.distributed_task_id,
            worker_id=task.last_assigned_worker_id,
            attempts=task.attempt_count,
        )
