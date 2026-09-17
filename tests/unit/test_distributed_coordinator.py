import asyncio
from datetime import UTC, datetime, timedelta

from app.distributed.config import DistributedConfig
from app.distributed.coordinator import DistributedCoordinator
from app.distributed.events import DistributedEventType
from app.distributed.executor import FakeWorkerExecutor
from app.distributed.fakes import FakeWorkerTransport
from app.distributed.models import (
    DistributedTask,
    DistributedTaskResult,
    DistributedTaskStatus,
    WorkerHeartbeat,
    WorkerInfo,
    WorkerStatus,
)
from app.distributed.queue import DistributedTaskQueue
from app.distributed.registry import WorkerRegistry


def _run(coro):
    return asyncio.run(coro)


def _build(*, max_retries: int = 2, transport=None, executor=None):
    registry = WorkerRegistry()
    queue = DistributedTaskQueue()
    transport = transport or FakeWorkerTransport(executor=executor or FakeWorkerExecutor())
    config = DistributedConfig(max_retries=max_retries)
    coordinator = DistributedCoordinator(
        registry=registry,
        queue=queue,
        transport=transport,
        config=config,
    )
    return registry, queue, coordinator


def _register(registry: WorkerRegistry, capabilities=frozenset({"analysis"})) -> WorkerInfo:
    info = WorkerInfo(worker_name="worker-a", capabilities=capabilities)
    registry.register(info)
    return info


def _task(capabilities=frozenset({"analysis"})) -> DistributedTask:
    return DistributedTask(task_type="analysis", required_capabilities=capabilities)


def _event_types(coordinator) -> list[DistributedEventType]:
    return [event.event_type for event in coordinator.events]


def test_submit_queues_and_records_event():
    _, queue, coordinator = _build()
    task = coordinator.submit(_task())
    assert task.status is DistributedTaskStatus.QUEUED
    assert coordinator.queue_depth == 1
    assert coordinator.task(task.distributed_task_id) is task
    assert coordinator.status_for(task.distributed_task_id) is DistributedTaskStatus.QUEUED
    assert DistributedEventType.TASK_QUEUED in _event_types(coordinator)


def test_submit_is_idempotent_for_same_id():
    _, queue, coordinator = _build()
    task = _task()
    first = coordinator.submit(task)
    second = coordinator.submit(task)
    assert first is second
    assert coordinator.queue_depth == 1


def test_dispatch_assigns_to_eligible_worker():
    registry, _, coordinator = _build()
    worker = _register(registry)
    task = coordinator.submit(_task())

    assignment = coordinator.dispatch_next()
    assert assignment is not None
    assert assignment.worker_id == worker.worker_id
    assert assignment.attempt == 1
    assert task.status is DistributedTaskStatus.ASSIGNED
    assert task.attempt_count == 1
    assert task.locked_by == worker.worker_id
    assert worker.assignment_count == 1
    assert coordinator.queue_depth == 0
    assert DistributedEventType.TASK_ASSIGNED in _event_types(coordinator)


def test_dispatch_without_worker_requeues():
    _, _, coordinator = _build()
    coordinator.submit(_task())
    assert coordinator.dispatch_next() is None
    assert coordinator.queue_depth == 1
    assert DistributedEventType.TASK_REQUEUED in _event_types(coordinator)


def test_dispatch_with_wrong_capability_requeues():
    registry, _, coordinator = _build()
    _register(registry, capabilities=frozenset({"vision"}))
    coordinator.submit(_task(capabilities=frozenset({"coding"})))
    assert coordinator.dispatch_next() is None
    assert coordinator.queue_depth == 1


def test_accept_success_completes_task():
    registry, _, coordinator = _build()
    _register(registry)
    task = coordinator.submit(_task())
    coordinator.dispatch_next()

    result = DistributedTaskResult.ok(task.distributed_task_id, output="done")
    accepted = coordinator.accept_result(result)

    assert accepted is result
    assert task.status is DistributedTaskStatus.COMPLETED
    assert task.locked_by is None
    assert coordinator.assignments == ()
    assert coordinator.completed_results == (result,)
    assert DistributedEventType.TASK_COMPLETED in _event_types(coordinator)


def test_accept_failure_retries_within_budget_then_fails():
    registry, _, coordinator = _build(max_retries=2)
    _register(registry)
    task = coordinator.submit(_task())

    # Attempt 1
    coordinator.dispatch_next()
    coordinator.accept_result(DistributedTaskResult.fail(task.distributed_task_id, error="boom"))
    assert task.status is DistributedTaskStatus.QUEUED
    assert task.attempt_count == 1
    assert coordinator.queue_depth == 1

    # Attempt 2
    coordinator.dispatch_next()
    coordinator.accept_result(
        DistributedTaskResult.fail(task.distributed_task_id, error="boom again")
    )
    assert task.status is DistributedTaskStatus.FAILED
    assert task.attempt_count == 2
    assert task.last_error == "boom again"
    assert DistributedEventType.TASK_RETRIED in _event_types(coordinator)
    assert DistributedEventType.TASK_FAILED in _event_types(coordinator)
    assert len(coordinator.completed_results) == 1


def test_zero_retries_fails_on_first_dispatch():
    registry, _, coordinator = _build(max_retries=0)
    _register(registry)
    task = coordinator.submit(_task())
    # A task with zero retries can never be assigned.
    assert coordinator.dispatch_next() is None
    assert task.status is DistributedTaskStatus.FAILED
    assert DistributedEventType.TASK_FAILED in _event_types(coordinator)


def test_duplicate_success_result_is_ignored():
    registry, _, coordinator = _build()
    _register(registry)
    task = coordinator.submit(_task())
    coordinator.dispatch_next()
    success = DistributedTaskResult.ok(task.distributed_task_id, output="done")
    coordinator.accept_result(success)

    duplicate = DistributedTaskResult.fail(task.distributed_task_id, error="late")
    accepted = coordinator.accept_result(duplicate)
    assert accepted is success  # stored success returned
    assert task.status is DistributedTaskStatus.COMPLETED


def test_stale_assignment_result_is_ignored():
    registry, _, coordinator = _build(max_retries=3)
    _register(registry)
    task = coordinator.submit(_task())

    first_assignment = coordinator.dispatch_next()
    coordinator.accept_result(DistributedTaskResult.fail(task.distributed_task_id, error="first"))
    second_assignment = coordinator.dispatch_next()
    assert second_assignment.assignment_id != first_assignment.assignment_id

    # A late duplicate from the first attempt must not affect attempt 2.
    stale = DistributedTaskResult.fail(
        task.distributed_task_id,
        assignment_id=first_assignment.assignment_id,
        error="stale",
    )
    coordinator.accept_result(stale)
    assert task.status is DistributedTaskStatus.ASSIGNED
    assert task.attempt_count == 2


def test_result_for_unknown_task_is_ignored():
    _, _, coordinator = _build()
    orphan = DistributedTaskResult.ok(DistributedTask(task_type="analysis").distributed_task_id)
    assert coordinator.accept_result(orphan) is orphan


def test_dispatch_async_success_round_trip():
    registry, _, coordinator = _build()
    _register(registry)
    task = coordinator.submit(_task())
    assignment = coordinator.dispatch_next()

    result = _run(coordinator.dispatch_async(assignment, task))
    assert result.success is True
    assert result.assignment_id == assignment.assignment_id

    coordinator.accept_result(result)
    assert task.status is DistributedTaskStatus.COMPLETED


def test_dispatch_async_unreachable_requeues_task():
    transport = FakeWorkerTransport(fail=True)
    registry, _, coordinator = _build(transport=transport)
    _register(registry)
    task = coordinator.submit(_task())
    assignment = coordinator.dispatch_next()

    result = _run(coordinator.dispatch_async(assignment, task))
    assert result.success is False
    assert result.error == "worker unreachable"
    assert task.status is DistributedTaskStatus.QUEUED
    assert task.locked_by is None
    assert coordinator.assignments == ()
    assert coordinator.queue_depth == 1
    assert DistributedEventType.TASK_REQUEUED in _event_types(coordinator)


def test_check_in_flight_retries_timed_out_assignment():
    registry, _, coordinator = _build(max_retries=2)
    _register(registry)
    task = coordinator.submit(_task())
    assignment = coordinator.dispatch_next()

    later = assignment.assigned_at + timedelta(seconds=31)
    retired = coordinator.check_in_flight(now=later)
    assert len(retired) == 1
    assert retired[0].status.value == "timed_out"
    assert task.status is DistributedTaskStatus.QUEUED
    assert coordinator.queue_depth == 1
    assert DistributedEventType.TASK_RETRIED in _event_types(coordinator)


def test_check_in_flight_ignores_fresh_assignment():
    registry, _, coordinator = _build()
    _register(registry)
    coordinator.submit(_task())
    assignment = coordinator.dispatch_next()
    retired = coordinator.check_in_flight(now=assignment.assigned_at)
    assert retired == ()


def test_check_in_flight_marks_stale_worker_and_reroutes():
    registry, _, coordinator = _build(max_retries=3)
    worker = _register(registry)
    now = datetime.now(UTC)
    registry.heartbeat(
        WorkerHeartbeat(worker_id=worker.worker_id),
        now=now - timedelta(seconds=100),
    )
    task = coordinator.submit(_task())
    assignment = coordinator.dispatch_next()

    later = assignment.assigned_at + timedelta(seconds=31)
    retired = coordinator.check_in_flight(now=later, now_fn=lambda: now)

    assert len(retired) == 1
    assert worker.status is WorkerStatus.STALE
    assert task.status is DistributedTaskStatus.QUEUED
    assert DistributedEventType.WORKER_STALE in _event_types(coordinator)
    assert DistributedEventType.TASK_REROUTED in _event_types(coordinator)


def test_cancel_queued_task():
    _, _, coordinator = _build()
    task = coordinator.submit(_task())
    assert coordinator.cancel(task.distributed_task_id) is True
    assert task.status is DistributedTaskStatus.CANCELLED
    assert coordinator.queue_depth == 0
    assert DistributedEventType.TASK_CANCELLED in _event_types(coordinator)


def test_cancel_in_flight_task_aborts_assignment():
    registry, _, coordinator = _build()
    _register(registry)
    task = coordinator.submit(_task())
    coordinator.dispatch_next()

    assert coordinator.cancel(task.distributed_task_id) is True
    assert task.status is DistributedTaskStatus.CANCELLED
    assert coordinator.assignments == ()


def test_cancel_unknown_task_returns_false():
    _, _, coordinator = _build()
    assert coordinator.cancel(_task().distributed_task_id) is False


def test_known_tasks_in_submission_order():
    _, _, coordinator = _build()
    first = coordinator.submit(_task())
    second = coordinator.submit(_task())
    assert coordinator.known_tasks == (first, second)


def test_dispatch_assigns_one_and_preserves_others_in_fifo():
    registry, _, coordinator = _build()
    _register(registry)
    first = coordinator.submit(_task())
    second = coordinator.submit(_task())
    third = coordinator.submit(_task())

    coordinator.dispatch_next()
    assert first.status is DistributedTaskStatus.ASSIGNED
    # The remaining two tasks stay queued (not stranded/lost).
    assert coordinator.queue_depth == 2
    assert second.status is DistributedTaskStatus.QUEUED
    assert third.status is DistributedTaskStatus.QUEUED

    # Both remaining tasks are still assignable on later calls.
    assert coordinator.dispatch_next() is not None
    assert coordinator.dispatch_next() is not None
    assert coordinator.queue_depth == 0


def test_dispatch_batch_honours_concurrency_cap():
    registry, _, coordinator = _build()
    _register(registry)
    coordinator.submit(_task())
    coordinator.submit(_task())
    coordinator.submit(_task())

    assignments = coordinator.dispatch_batch(max_concurrent=2)
    assert len(assignments) == 2
    assert coordinator.queue_depth == 1

    # A fresh pass grabs the remainder.
    rest = coordinator.dispatch_batch(max_concurrent=2)
    assert len(rest) == 1
    assert coordinator.queue_depth == 0


def test_dispatch_batch_returns_empty_when_no_work_or_no_workers():
    registry, _, coordinator = _build()
    _register(registry)
    coordinator.submit(_task(capabilities=frozenset({"coding"})))
    assert coordinator.dispatch_batch() == ()
