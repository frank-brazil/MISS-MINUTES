"""Typed, in-memory distributed task queue.

FIFO only for this chunk.  The queue is intentionally backend-free (no
Redis/Kafka); the interface is the seam a durable store can slot into later.
Cancellation only affects tasks that are still queued; assigned tasks are
owned by the coordinator.
"""

from collections import deque
from uuid import UUID

from app.distributed.models import DistributedTask, DistributedTaskStatus


class DuplicateTaskError(Exception):
    """Raised when enqueuing a task ID that is already tracked."""


class DistributedTaskQueue:
    def __init__(self) -> None:
        self._queue: deque[DistributedTask] = deque()
        self._by_id: dict[UUID, DistributedTask] = {}
        self._cancelled: set[UUID] = set()

    @property
    def pending_count(self) -> int:
        """Number of queued (non-cancelled) tasks."""
        return sum(1 for task in self._queue if task.status is not DistributedTaskStatus.CANCELLED)

    def enqueue(self, task: DistributedTask) -> DistributedTask:
        """Queue a task; duplicate task IDs are rejected."""
        if task.distributed_task_id in self._by_id:
            raise DuplicateTaskError(f"task {task.distributed_task_id} is already queued")
        task.change_status(DistributedTaskStatus.QUEUED)
        self._by_id[task.distributed_task_id] = task
        self._queue.append(task)
        return task

    def dequeue(self) -> DistributedTask | None:
        """Pop the oldest queued task, skipping cancelled ones."""
        while self._queue:
            task = self._queue.popleft()
            self._by_id.pop(task.distributed_task_id, None)
            if task.status is DistributedTaskStatus.CANCELLED:
                continue
            return task
        return None

    def take_all(self) -> tuple[DistributedTask, ...]:
        """Pop every currently queued task as a batch."""
        tasks: list[DistributedTask] = []
        while self._queue:
            task = self._queue.popleft()
            self._by_id.pop(task.distributed_task_id, None)
            if task.status is not DistributedTaskStatus.CANCELLED:
                tasks.append(task)
        return tuple(tasks)

    def requeue(self, task: DistributedTask) -> DistributedTask:
        """Return a task to the queue (used when no worker is eligible)."""
        if task.distributed_task_id in self._by_id:
            return task
        task.change_status(DistributedTaskStatus.QUEUED)
        self._by_id[task.distributed_task_id] = task
        self._queue.append(task)
        return task

    def cancel(self, task_id: UUID) -> bool:
        """Cancel a queued task; returns False if it is not queued."""
        task = self._by_id.get(task_id)
        if task is None:
            return False
        if task.status is DistributedTaskStatus.CANCELLED:
            return False
        task.change_status(DistributedTaskStatus.CANCELLED)
        self._cancelled.add(task_id)
        # Leave it in the deque; dequeue()/take_all() skip cancelled tasks.
        return True

    def get(self, task_id: UUID) -> DistributedTask | None:
        return self._by_id.get(task_id)

    def contains(self, task_id: UUID) -> bool:
        return task_id in self._by_id and task_id not in self._cancelled

    def snapshot(self) -> tuple[DistributedTask, ...]:
        return tuple(self._queue)

    @property
    def queued_ids(self) -> tuple[UUID, ...]:
        return tuple(task.distributed_task_id for task in self._queue)
