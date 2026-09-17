"""Master-side coordinator: dispatch, retry, staleness, result handling.

The coordinator owns every distributed task it has seen and all state
transitions:

- **Submit**: a task is queued (FIFO) at ``QUEUED``.
- **Dispatch**: ``dispatch_next`` pulls the oldest queued task, deterministically
  selects an eligible worker, and creates a ``TaskAssignment`` (one attempt).
- **Execute**: the assignment crosses to the worker via the injected async
  ``WorkerTransport`` (``dispatch_async``).  A worker that is unreachable at
  dispatch releases the assignment and the task is requeued.
- **Result**: ``accept_result`` applies a structured result exactly once
  (duplicate/stale responses are ignored via ``assignment_id``), forwarding a
  failed attempt to a retry within ``max_retries`` or to terminal ``FAILED``.
- **Timeout/staleness**: ``check_in_flight`` finalizes assignments older than
  the dispatch timeout; when the worker is also heartbeat-stale the worker is
  marked ``STALE`` and the task is rerouted, otherwise it is retried/requeued.

The coordinator never executes work itself.  All methods are synchronous and
atomic within the single asyncio event loop that also drives the HTTP handlers
and tests; the only await points are the injected transport calls.
Deterministic tests inject ``now``/``now_fn`` so no real time is needed.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from app.distributed.config import DistributedConfig
from app.distributed.events import DistributedEvent, DistributedEventType
from app.distributed.executor import WorkerExecutor
from app.distributed.models import (
    DistributedTask,
    DistributedTaskResult,
    DistributedTaskStatus,
    TaskAssignment,
    WorkerInfo,
)
from app.distributed.queue import DistributedTaskQueue, DuplicateTaskError
from app.distributed.registry import WorkerRegistry
from app.distributed.scheduler import (
    DistributedScheduler,
    NoEligibleWorkerError,
)
from app.distributed.transport import (
    TransportError,
    WorkerTransport,
    WorkerUnreachableError,
)
from app.security.manager import SecurityManager, as_security_manager
from app.security.models import (
    Permission,
    PermissionCategory,
    SecurityContext,
    SecurityDecision,
)
from app.security.policy import SecurityPolicy


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DistributedCoordinator:
    def __init__(
        self,
        *,
        registry: WorkerRegistry,
        queue: DistributedTaskQueue,
        transport: WorkerTransport,
        config: DistributedConfig | None = None,
        scheduler: DistributedScheduler | None = None,
        executor: WorkerExecutor | None = None,
        security: "SecurityManager | SecurityPolicy | None" = None,
    ) -> None:
        self._registry = registry
        self._queue = queue
        self._transport = transport
        self._config = config or DistributedConfig()
        self._scheduler = scheduler or DistributedScheduler()
        # Accepted for composition parity; the coordinator routes dispatches to
        # the injected transport and never executes directly.
        self._executor = executor
        self._security = as_security_manager(security)
        self._assignments: dict[UUID, TaskAssignment] = {}
        # Owns every task known to this master, queued or assigned.
        self._tasks: dict[UUID, DistributedTask] = {}
        self._results: dict[UUID, DistributedTaskResult] = {}
        self._events: list[DistributedEvent] = []
        self._logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def assignments(self) -> tuple[TaskAssignment, ...]:
        return tuple(self._assignments.values())

    @property
    def completed_results(self) -> tuple[DistributedTaskResult, ...]:
        return tuple(self._results.values())

    @property
    def events(self) -> tuple[DistributedEvent, ...]:
        return tuple(self._events)

    @property
    def registry(self) -> "WorkerRegistry":
        """The worker registry this coordinator drives."""
        return self._registry

    @property
    def queue(self) -> "DistributedTaskQueue":
        """The FIFO task queue this coordinator drives."""
        return self._queue

    @property
    def security(self) -> SecurityManager | None:
        """The security manager gating dispatches, when configured."""
        return self._security

    def task(self, task_id: UUID) -> DistributedTask | None:
        """Live lookup for any task this master has seen."""
        return self._tasks.get(task_id)

    @property
    def known_tasks(self) -> tuple[DistributedTask, ...]:
        """Every task this master has seen, in submission order."""
        return tuple(self._tasks.values())

    def status_for(self, task_id: UUID) -> DistributedTaskStatus | None:
        task = self._tasks.get(task_id)
        return task.status if task is not None else None

    @property
    def queue_depth(self) -> int:
        """Queued-but-not-yet-assigned task count."""
        return self._queue.pending_count

    # ------------------------------------------------------------------
    # Intake
    # ------------------------------------------------------------------

    def submit(self, task: DistributedTask) -> DistributedTask:
        """Queue a task for execution; duplicate task IDs are ignored."""
        existing = self._tasks.get(task.distributed_task_id)
        if existing is not None:
            return existing
        try:
            self._queue.enqueue(task)
        except DuplicateTaskError:
            return self._queue.get(task.distributed_task_id) or task
        self._tasks[task.distributed_task_id] = task
        self._record(
            DistributedEventType.TASK_QUEUED,
            f"Task '{task.task_type}' queued.",
            success=True,
            task_id=task.distributed_task_id,
        )
        return task

    def cancel(self, task_id: UUID) -> bool:
        """Cancel a queued task, or abort an in-flight one immediately."""
        task = self._tasks.get(task_id)
        if task is None:
            return False

        if task.status is DistributedTaskStatus.QUEUED:
            if not self._queue.cancel(task_id):
                return False
            task.change_status(DistributedTaskStatus.CANCELLED)
            self._record(
                DistributedEventType.TASK_CANCELLED,
                "Task cancelled while queued.",
                success=True,
                task_id=task_id,
            )
            return True

        if task.status is DistributedTaskStatus.ASSIGNED:
            assignment = self._find_assignment(task_id)
            worker_id = assignment.worker_id if assignment else task.locked_by
            self._finalize_assignment(task_id)
            task.change_status(DistributedTaskStatus.CANCELLED)
            task.release_worker()
            self._record(
                DistributedEventType.TASK_CANCELLED,
                "Task cancelled while in-flight; assignment aborted.",
                success=True,
                task_id=task_id,
                worker_id=worker_id,
            )
            return True

        return False

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def dispatch_next(
        self,
        *,
        is_stale: Callable[[WorkerInfo], bool] | None = None,
    ) -> TaskAssignment | None:
        """Assign the oldest assignable queued task to an eligible worker.

        Never blocks and never loops indefinitely: each call drains the queue
        exactly once, assigns the first task with an eligible worker, and
        requeues the rest so later calls can retry them.  Tasks already at the
        retry ceiling are failed.  Returns ``None`` when no assignment is made.
        """
        candidates = list(self._queue.take_all())
        if not candidates:
            return None

        for index, task in enumerate(candidates):
            if task.status is DistributedTaskStatus.CANCELLED:
                continue

            if task.attempt_count >= self._config.max_retries:
                self._fail_task(
                    task,
                    "retries exhausted before assignment",
                    worker_id=task.locked_by,
                )
                continue

            try:
                worker = self._scheduler.select_worker(
                    task,
                    self._registry.list_workers(),
                    is_stale=is_stale,
                )
            except NoEligibleWorkerError:
                self._queue.requeue(task)
                self._record(
                    DistributedEventType.TASK_REQUEUED,
                    "No eligible worker yet; task requeued.",
                    success=False,
                    task_id=task.distributed_task_id,
                )
                continue

            if self._security is not None:
                dispatch_decision = self._authorize_dispatch(task, worker)
                if not dispatch_decision.allowed:
                    if dispatch_decision.requires_confirmation:
                        reason = "task requires confirmation at the master"
                    else:
                        reason = (
                            "task denied by security policy: "
                            f"{dispatch_decision.reason_code or 'denied'}"
                        )
                    self._logger.warning(
                        "Dispatch refused by security policy: task_id=%s worker_id=%s reason=%s",
                        task.distributed_task_id,
                        worker.worker_id,
                        dispatch_decision.reason,
                    )
                    self._fail_task(task, reason)
                    continue

            assignment = self._assign_task(task, worker)
            # Everything behind this task must go back into the FIFO so the
            # next dispatch call can assign it.
            for leftover in candidates[index + 1 :]:
                if leftover.status is not DistributedTaskStatus.CANCELLED:
                    self._queue.requeue(leftover)
            return assignment

        return None

    def dispatch_batch(
        self,
        *,
        is_stale: Callable[[WorkerInfo], bool] | None = None,
        max_concurrent: int | None = None,
    ) -> tuple[TaskAssignment, ...]:
        """Dispatch up to ``max_concurrent`` tasks in one pass.

        Honors ``config.max_concurrent_dispatch`` by default.  Deterministic
        and non-blocking: each step assigns the oldest assignable queued task;
        an assignment is created at most once per task per batch, so a worker
        can hold several assignments across the batch without races.
        """
        limit = max_concurrent or self._config.max_concurrent_dispatch
        assignments: list[TaskAssignment] = []
        for _ in range(limit):
            assignment = self.dispatch_next(is_stale=is_stale)
            if assignment is None:
                break
            assignments.append(assignment)
        return tuple(assignments)

    def _assign_task(self, task: DistributedTask, worker: WorkerInfo) -> TaskAssignment:
        task.bump_attempt()
        assignment = TaskAssignment(
            distributed_task_id=task.distributed_task_id,
            worker_id=worker.worker_id,
            worker_name=worker.worker_name,
            attempt=task.attempt_count,
        )
        task.assign_to(worker.worker_id)
        self._assignments[assignment.assignment_id] = assignment
        self._registry.note_assignment(worker.worker_id)
        self._record(
            DistributedEventType.TASK_ASSIGNED,
            f"Task assigned to '{worker.worker_name}' (attempt {task.attempt_count}).",
            success=True,
            task_id=task.distributed_task_id,
            worker_id=worker.worker_id,
            attempt=task.attempt_count,
        )
        return assignment

    def _authorize_dispatch(self, task: DistributedTask, worker: WorkerInfo) -> SecurityDecision:
        """Evaluate a dispatch against the configured security policy.

        The check is fail-closed: unregistered/unknown actor identities and
        unapproved task types must be explicitly allowed by a rule before a
        dispatch proceeds.
        """
        security = self._security  # guaranteed not None by caller
        permission = Permission(
            category=PermissionCategory.DISTRIBUTED,
            resource=task.task_type,
        )
        request = security.create_request(
            permission=permission,
            action="distributed:dispatch",
            task_id=task.distributed_task_id,
            actor=str(worker.worker_id),
            origin="distributed-master",
        )
        context = SecurityContext(
            actor_id=str(worker.worker_id),
            worker_id=worker.worker_id,
            origin="distributed-master",
            capabilities=frozenset(task.required_capabilities),
        )
        return security.check(request, context=context)

    # ------------------------------------------------------------------
    # Async dispatcher over the injected transport
    # ------------------------------------------------------------------

    async def dispatch_async(
        self,
        assignment: TaskAssignment,
        task: DistributedTask,
    ) -> DistributedTaskResult:
        """Ship an assignment to the worker and return its structured result.

        Unreachable/transport errors release the assignment and requeue the
        task; the returned result is a synthetic failure so even callers that
        ignore exceptions observe a consistent outcome.
        """
        try:
            self._record(
                DistributedEventType.TASK_STARTED,
                f"Dispatch {assignment.assignment_id} started.",
                success=True,
                task_id=assignment.task_id,
                worker_id=assignment.worker_id,
                attempt=assignment.attempt,
            )
            result = await self._transport.dispatch_task(assignment, task)
        except WorkerUnreachableError as exc:
            self._logger.warning(
                "Worker unreachable: assignment_id=%s error=%s",
                assignment.assignment_id,
                exc,
            )
            self._release_unreachable(assignment, task)
            return self._synthetic_failure(assignment, "worker unreachable")
        except TransportError as exc:
            self._logger.warning(
                "Transport error during dispatch: assignment_id=%s error=%s",
                assignment.assignment_id,
                exc,
            )
            self._release_unreachable(assignment, task)
            return self._synthetic_failure(assignment, "transport error")
        return result

    def _release_unreachable(self, assignment: TaskAssignment, task: DistributedTask) -> None:
        """Release an unreachable dispatch so the task can be retried later."""
        active = self._assignments.pop(assignment.assignment_id, None)
        if active is None:
            return  # a concurrent finalization already handled this assignment
        task.release_worker()
        task.change_status(DistributedTaskStatus.QUEUED)
        self._record(
            DistributedEventType.TASK_REQUEUED,
            "Worker unreachable at dispatch; assignment released.",
            success=False,
            task_id=task.distributed_task_id,
            worker_id=assignment.worker_id,
            attempt=assignment.attempt,
        )
        if task.status is not DistributedTaskStatus.CANCELLED:
            self._queue.requeue(task)

    def _synthetic_failure(self, assignment: TaskAssignment, error: str) -> DistributedTaskResult:
        return DistributedTaskResult.fail(
            assignment.task_id,
            assignment_id=assignment.assignment_id,
            worker_id=assignment.worker_id,
            error=error,
        )

    # ------------------------------------------------------------------
    # Result handling (idempotent)
    # ------------------------------------------------------------------

    def accept_result(self, result: DistributedTaskResult) -> DistributedTaskResult:
        """Apply a worker's structured result to its assignment exactly once.

        - A duplicate success for an already-terminal task returns the stored
          result.
        - Stale results whose ``assignment_id`` no longer matches the active
          assignment are ignored (a retry may already own the task).
        - A successful result completes the task.
        - A failed result triggers a retry if attempts remain, else FAILED.
        """
        task_id = result.distributed_task_id
        stored = self._results.get(task_id)
        if stored is not None and stored.success:
            return stored

        task = self._tasks.get(task_id)
        if task is None:
            # Result for a task this master never saw: ignore safely.
            return result

        assignment = self._find_assignment(task_id)
        if assignment is None:
            # Either already completed (handled above) or the assignment was
            # released by an unreachable/retry path; treat as stale duplicate.
            return result

        if result.assignment_id is not None and assignment.assignment_id != result.assignment_id:
            return result  # stale duplicate from a previous attempt

        assignment.mark_result_into(result)

        if result.success:
            self._complete(task, assignment, result)
            return result

        if task.attempt_count < self._config.max_retries:
            self._retry(task, assignment, result.error or "task failed")
        else:
            self._fail_task(
                task,
                result.error or f"failed on attempt {assignment.attempt}",
                assignment=assignment,
            )
        return result

    def _complete(self, task, assignment: TaskAssignment, result: DistributedTaskResult) -> None:
        self._results[task.distributed_task_id] = result
        task.complete_with(result)
        task.release_worker()
        self._assignments.pop(assignment.assignment_id, None)
        self._record(
            DistributedEventType.TASK_COMPLETED,
            "Task completed.",
            success=True,
            task_id=task.distributed_task_id,
            worker_id=assignment.worker_id,
            attempt=assignment.attempt,
        )

    def _retry(self, task, assignment: TaskAssignment, error: str) -> None:
        task.last_error = error
        self._assignments.pop(assignment.assignment_id, None)
        task.release_worker()
        task.change_status(DistributedTaskStatus.QUEUED)
        self._queue.requeue(task)
        self._record(
            DistributedEventType.TASK_RETRIED,
            f"Attempt {assignment.attempt} failed; retry queued.",
            success=False,
            task_id=task.distributed_task_id,
            worker_id=assignment.worker_id,
            attempt=assignment.attempt,
        )

    def _fail_task(
        self, task, reason: str, *, assignment: TaskAssignment | None = None, worker_id=None
    ) -> None:
        task.mark_failed(reason)
        task.release_worker()
        if assignment is not None:
            self._assignments.pop(assignment.assignment_id, None)
        failed_result = DistributedTaskResult.fail(
            task.distributed_task_id,
            assignment_id=assignment.assignment_id if assignment else None,
            worker_id=worker_id or (assignment.worker_id if assignment else task.locked_by),
            error=reason,
        )
        self._results[task.distributed_task_id] = failed_result
        self._record(
            DistributedEventType.TASK_FAILED,
            reason,
            success=False,
            task_id=task.distributed_task_id,
            worker_id=worker_id or (assignment.worker_id if assignment else None),
            attempt=assignment.attempt if assignment else None,
        )

    # ------------------------------------------------------------------
    # Timeout / staleness sweep (deterministic, injectable time)
    # ------------------------------------------------------------------

    def check_in_flight(
        self,
        *,
        now: datetime | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> tuple[TaskAssignment, ...]:
        """Release in-flight assignments that have gone too long without a result.

        Returns the assignments retired.  When the assigned worker is no
        longer heartbeat-responsive the worker is marked ``STALE`` and the
        task is rerouted; a plain dispatch timeout retries/requeues without
        blaming the worker.
        """
        moment = now if now is not None else (now_fn() if now_fn else _utc_now())
        retired: list[TaskAssignment] = []
        for assignment in tuple(self._assignments.values()):
            if assignment.is_final:
                continue
            age_seconds = (moment - assignment.assigned_at).total_seconds()
            if age_seconds <= self._config.dispatch_timeout_seconds:
                continue

            task = self._tasks.get(assignment.task_id)
            worker_stale = self._is_worker_stale(assignment, now_fn)
            if worker_stale:
                self._registry.mark_stale(assignment.worker_id)
                self._record(
                    DistributedEventType.WORKER_STALE,
                    "Worker unresponsive mid-task; marked stale.",
                    success=False,
                    task_id=assignment.task_id,
                    worker_id=assignment.worker_id,
                    attempt=assignment.attempt,
                )

            assignment.mark_timed_out()
            self._assignments.pop(assignment.assignment_id, None)

            if task is not None:
                self._retry_after_timeout(task, assignment, worker_stale)
            retired.append(assignment)
        return tuple(retired)

    def _is_worker_stale(self, assignment: TaskAssignment, now_fn) -> bool:
        if now_fn is None:
            return False
        worker = self._registry.lookup(assignment.worker_id)
        return worker is not None and self._registry.is_stale(
            worker,
            timeout=self._config.heartbeat_timeout_seconds,
            now=now_fn(),
        )

    def _retry_after_timeout(self, task, assignment: TaskAssignment, worker_stale: bool) -> None:
        if task.status is DistributedTaskStatus.CANCELLED:
            return  # cancel() already aborted this task
        if task.attempt_count >= self._config.max_retries:
            if worker_stale:
                self._record(
                    DistributedEventType.TASK_REROUTED,
                    f"Task rerouted after worker {assignment.worker_id} became stale.",
                    success=False,
                    task_id=task.distributed_task_id,
                    worker_id=assignment.worker_id,
                    attempt=assignment.attempt,
                )
            self._fail_task(
                task,
                "assignment timed out with retries exhausted",
                worker_id=assignment.worker_id,
            )
            return
        task.release_worker()
        task.change_status(DistributedTaskStatus.QUEUED)
        self._queue.requeue(task)
        if worker_stale:
            self._record(
                DistributedEventType.TASK_REROUTED,
                "Task rerouted to a fresh worker after staleness.",
                success=False,
                task_id=task.distributed_task_id,
                worker_id=assignment.worker_id,
                attempt=assignment.attempt,
            )
        else:
            self._record(
                DistributedEventType.TASK_RETRIED,
                "Assignment timed out; task requeued.",
                success=False,
                task_id=task.distributed_task_id,
                worker_id=assignment.worker_id,
                attempt=assignment.attempt,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_assignment(self, task_id: UUID) -> TaskAssignment | None:
        for assignment in self._assignments.values():
            if assignment.task_id == task_id:
                return assignment
        return None

    def _finalize_assignment(self, task_id: UUID) -> None:
        assignment = self._find_assignment(task_id)
        if assignment is not None:
            self._assignments.pop(assignment.assignment_id, None)

    def _record(
        self,
        event_type: DistributedEventType,
        message: str,
        *,
        success: bool | None,
        task_id: UUID | None = None,
        worker_id: UUID | None = None,
        attempt: int | None = None,
    ) -> None:
        self._events.append(
            DistributedEvent(
                event_type=event_type,
                message=message,
                success=success,
                task_id=task_id,
                worker_id=worker_id,
                attempt=attempt,
            )
        )

    def record_external_event(self, event: DistributedEvent) -> None:
        """Add an externally produced observability event (e.g. registry).

        Used by the master HTTP handlers so worker registration and heartbeat
        traffic appears in the same event stream as coordinator transitions.
        """
        self._events.append(event)
