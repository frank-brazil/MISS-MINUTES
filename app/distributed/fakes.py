"""Deterministic in-memory transport fakes for the distributed layer.

Used throughout the offline test suite and as safe defaults.  These fakes
perform no network I/O; they route dispatches to injected executors and
record everything they see.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from app.distributed.executor import FakeWorkerExecutor, WorkerExecutor
from app.distributed.models import (
    DistributedTask,
    DistributedTaskResult,
    TaskAssignment,
    WorkerHeartbeat,
    WorkerInfo,
)
from app.distributed.transport import (
    MasterTransport,
    TransportError,
    WorkerTransport,
    WorkerUnreachableError,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class FakeWorkerTransport(WorkerTransport):
    """Master→worker in-memory transport wrapping a :class:`WorkerExecutor`.

    Failure behaviour is scriptable: a transport can always be unreachable,
    fail specific task IDs / assignment IDs, or raise one-shot.
    """

    name = "fake-worker-transport"
    description = "In-memory transport that dispatches to a local executor."

    def __init__(
        self,
        executor: WorkerExecutor | None = None,
        *,
        worker_id: UUID | None = None,
        fail: bool = False,
        fail_once: bool = False,
        fail_message: str = "worker unreachable",
        fail_task_ids: frozenset[UUID] = frozenset(),
        fail_assignment_ids: frozenset[UUID] = frozenset(),
        raise_error: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        self._executor = executor or FakeWorkerExecutor()
        self._worker_id = worker_id
        self._fail = fail
        self._fail_once = fail_once  # fail on the first dispatch only
        self._fail_message = fail_message
        self._fail_task_ids = frozenset(fail_task_ids)
        self._fail_assignment_ids = frozenset(fail_assignment_ids)
        self._raise_error = raise_error
        self._delay = delay
        self._dispatches: list[tuple[TaskAssignment, DistributedTask]] = []
        self._closed = False
        self._logger = logging.getLogger(__name__)

    @property
    def dispatches(self) -> tuple[tuple[TaskAssignment, DistributedTask], ...]:
        return tuple(self._dispatches)

    @property
    def dispatch_count(self) -> int:
        return len(self._dispatches)

    async def dispatch_task(
        self,
        assignment: TaskAssignment,
        task: DistributedTask,
    ) -> DistributedTaskResult:
        if self._closed:
            raise WorkerUnreachableError("transport is closed")
        self._dispatches.append((assignment, task))
        if self._delay:
            import asyncio

            await asyncio.sleep(self._delay)
        if self._raise_error is not None:
            raise self._raise_error
        if self._fail or (
            self._fail_once and self.dispatch_count == 1
        ):
            self._logger.warning(
                "Fake worker transport unreachable: assignment_id=%s",
                assignment.assignment_id,
            )
            raise WorkerUnreachableError(self._fail_message)
        if (
            task.distributed_task_id in self._fail_task_ids
            or assignment.assignment_id in self._fail_assignment_ids
        ):
            return DistributedTaskResult.fail(
                task.distributed_task_id,
                assignment_id=assignment.assignment_id,
                worker_id=self._worker_id or assignment.worker_id,
                error=self._fail_message,
            )
        try:
            result = await self._executor.execute(task)
        except Exception as exc:
            raise TransportError(
                f"worker crashed during execution: {type(exc).__name__}"
            ) from exc
        result.assignment_id = assignment.assignment_id
        result.worker_id = self._worker_id or assignment.worker_id
        return result

    async def close(self) -> None:
        self._closed = True


class FakeMasterTransport(MasterTransport):
    """Worker→master in-memory transport that records registrations/heartbeats.

    The master side references (registry, coordinator) are provided by the
    caller; the fake only records the traffic for assertions.
    """

    name = "fake-master-transport"
    description = "In-memory transport that records worker→master traffic."

    def __init__(
        self,
        *,
        fail_register: bool = False,
        fail_heartbeat: bool = False,
    ) -> None:
        self._fail_register = fail_register
        self._fail_heartbeat = fail_heartbeat
        self._registrations: list[WorkerInfo] = []
        self._heartbeats: list[WorkerHeartbeat] = []
        self._closed = False

    @property
    def registrations(self) -> tuple[WorkerInfo, ...]:
        return tuple(self._registrations)

    @property
    def heartbeats(self) -> tuple[WorkerHeartbeat, ...]:
        return tuple(self._heartbeats)

    async def register_worker(self, info: WorkerInfo) -> bool:
        if self._closed:
            return False
        if self._fail_register:
            return False
        self._registrations.append(info)
        return True

    async def send_heartbeat(self, heartbeat: WorkerHeartbeat) -> bool:
        if self._closed:
            return False
        if self._fail_heartbeat:
            return False
        self._heartbeats.append(heartbeat)
        return True

    async def close(self) -> None:
        self._closed = True
