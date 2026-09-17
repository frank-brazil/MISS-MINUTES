import pytest

from app.distributed.models import DistributedTask, DistributedTaskStatus
from app.distributed.queue import DistributedTaskQueue, DuplicateTaskError


def _task() -> DistributedTask:
    return DistributedTask(task_type="analysis")


def test_enqueue_sets_status_and_counts():
    queue = DistributedTaskQueue()
    task = queue.enqueue(_task())
    assert task.status is DistributedTaskStatus.QUEUED
    assert queue.pending_count == 1
    assert queue.contains(task.distributed_task_id) is True


def test_enqueue_rejects_duplicate_id():
    queue = DistributedTaskQueue()
    task = _task()
    queue.enqueue(task)
    with pytest.raises(DuplicateTaskError):
        queue.enqueue(task)


def test_dequeue_is_fifo():
    queue = DistributedTaskQueue()
    first = queue.enqueue(_task())
    second = queue.enqueue(_task())
    assert queue.dequeue() is first
    assert queue.dequeue() is second
    assert queue.dequeue() is None


def test_dequeue_skips_cancelled_tasks():
    queue = DistributedTaskQueue()
    first = queue.enqueue(_task())
    second = queue.enqueue(_task())
    assert queue.cancel(first.distributed_task_id) is True
    assert first.status is DistributedTaskStatus.CANCELLED
    assert queue.dequeue() is second
    assert queue.dequeue() is None


def test_cancel_unknown_returns_false():
    queue = DistributedTaskQueue()
    assert queue.cancel(_task().distributed_task_id) is False


def test_cancel_is_idempotent():
    queue = DistributedTaskQueue()
    task = queue.enqueue(_task())
    assert queue.cancel(task.distributed_task_id) is True
    assert queue.cancel(task.distributed_task_id) is False


def test_requeue_returns_task_to_queue():
    queue = DistributedTaskQueue()
    task = queue.enqueue(_task())
    assert queue.dequeue() is task
    queue.requeue(task)
    assert queue.pending_count == 1
    assert queue.contains(task.distributed_task_id) is True
    assert queue.dequeue() is task


def test_requeue_does_not_duplicate():
    queue = DistributedTaskQueue()
    task = queue.enqueue(_task())
    queue.requeue(task)  # already queued
    assert queue.pending_count == 1


def test_take_all_drains_queue_excluding_cancelled():
    queue = DistributedTaskQueue()
    first = queue.enqueue(_task())
    second = queue.enqueue(_task())
    third = queue.enqueue(_task())
    queue.cancel(second.distributed_task_id)
    batch = queue.take_all()
    assert batch == (first, third)
    assert queue.pending_count == 0


def test_snapshot_and_queued_ids():
    queue = DistributedTaskQueue()
    first = queue.enqueue(_task())
    second = queue.enqueue(_task())
    assert queue.snapshot() == (first, second)
    assert queue.queued_ids == (first.distributed_task_id, second.distributed_task_id)


def test_get_returns_none_after_dequeue():
    queue = DistributedTaskQueue()
    task = queue.enqueue(_task())
    assert queue.get(task.distributed_task_id) is task
    queue.dequeue()
    assert queue.get(task.distributed_task_id) is None
