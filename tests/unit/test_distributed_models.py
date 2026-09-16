from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.distributed.models import (
    AssignmentStatus,
    DistributedTask,
    DistributedTaskResult,
    DistributedTaskStatus,
    TaskAssignment,
    WorkerHeartbeat,
    WorkerInfo,
    WorkerResources,
    WorkerStatus,
)

# ----------------------------------------------------------------------
# WorkerResources
# ----------------------------------------------------------------------


def test_resources_defaults_are_safe():
    resources = WorkerResources()
    assert resources.cpu_count is None
    assert resources.memory_bytes is None
    assert resources.gpu_count is None
    assert resources.gpu_available is False
    assert resources.current_load == 0.0
    assert resources.labels == {}


def test_resources_reject_invalid_values():
    with pytest.raises(ValidationError):
        WorkerResources(cpu_count=0)
    with pytest.raises(ValidationError):
        WorkerResources(gpu_count=0)
    with pytest.raises(ValidationError):
        WorkerResources(memory_bytes=-1)
    with pytest.raises(ValidationError):
        WorkerResources(current_load=1.5)
    with pytest.raises(ValidationError):
        WorkerResources(current_load=-0.1)


def test_resources_load_accepts_bounds():
    assert WorkerResources(current_load=0.0).current_load == 0.0
    assert WorkerResources(current_load=1.0).current_load == 1.0


# ----------------------------------------------------------------------
# WorkerInfo
# ----------------------------------------------------------------------


def test_worker_info_defaults():
    info = WorkerInfo(worker_name="worker-a")
    assert info.worker_id is not None
    assert info.status is WorkerStatus.AVAILABLE
    assert info.capabilities == frozenset()
    assert info.protocol_version == "1.0"
    assert info.assignment_count == 0
    assert isinstance(info.registered_at, datetime)
    assert isinstance(info.last_heartbeat, datetime)


def test_worker_info_never_has_secret_fields():
    field_names = set(WorkerInfo.model_fields)
    for forbidden in ("token", "auth_token", "password", "secret", "credential"):
        assert forbidden not in field_names


def test_worker_info_rejects_blank_name():
    with pytest.raises(ValidationError):
        WorkerInfo(worker_name="   ")


def test_worker_info_rejects_blank_capability():
    with pytest.raises(ValidationError):
        WorkerInfo(worker_name="w", capabilities=frozenset({"ok", "  "}))


def test_worker_info_rejects_negative_assignment_count():
    with pytest.raises(ValidationError):
        WorkerInfo(worker_name="w", assignment_count=-1)


# ----------------------------------------------------------------------
# WorkerHeartbeat
# ----------------------------------------------------------------------


def test_heartbeat_defaults_and_optional_fields():
    heartbeat = WorkerHeartbeat(worker_id=uuid4())
    assert heartbeat.status is WorkerStatus.AVAILABLE
    assert heartbeat.capabilities is None
    assert heartbeat.resources is None
    assert isinstance(heartbeat.timestamp, datetime)


def test_heartbeat_rejects_blank_capability():
    with pytest.raises(ValidationError):
        WorkerHeartbeat(worker_id=uuid4(), capabilities=frozenset({""}))


# ----------------------------------------------------------------------
# DistributedTask
# ----------------------------------------------------------------------


def test_task_defaults_and_validation():
    task = DistributedTask(task_type="analysis")
    assert task.status is DistributedTaskStatus.PENDING
    assert task.retry_count == 0
    assert task.attempt_count == 0
    assert task.required_capabilities == frozenset()

    with pytest.raises(ValidationError):
        DistributedTask(task_type="   ")
    with pytest.raises(ValidationError):
        DistributedTask(task_type="analysis", retry_count=-1)
    with pytest.raises(ValidationError):
        DistributedTask(task_type="analysis", required_capabilities=frozenset({""}))


def test_task_lifecycle_helpers():
    task = DistributedTask(task_type="coding", required_capabilities=frozenset({"coding"}))
    assert task.locked_by is None

    task.bump_attempt()
    assert task.attempt_count == 1
    task.bump_attempt()
    assert task.attempt_count == 2

    worker_id = uuid4()
    task.assign_to(worker_id)
    assert task.status is DistributedTaskStatus.ASSIGNED
    assert task.locked_by == worker_id

    task.release_worker()
    assert task.locked_by is None

    result = DistributedTaskResult.ok(task.distributed_task_id, output="done")
    task.complete_with(result)
    assert task.status is DistributedTaskStatus.COMPLETED

    task2 = DistributedTask(task_type="coding")
    task2.complete_with(DistributedTaskResult.fail(task2.distributed_task_id, error="boom"))
    assert task2.status is DistributedTaskStatus.FAILED
    assert task2.last_error == "boom"

    task3 = DistributedTask(task_type="coding")
    task3.mark_failed("dead")
    assert task3.status is DistributedTaskStatus.FAILED
    assert task3.last_error == "dead"


def test_task_change_status_updates_timestamp():
    task = DistributedTask(task_type="analysis")
    before = task.updated_at
    task.change_status(DistributedTaskStatus.RUNNING)
    assert task.status is DistributedTaskStatus.RUNNING
    assert task.updated_at >= before


# ----------------------------------------------------------------------
# TaskAssignment
# ----------------------------------------------------------------------


def test_task_assignment_helpers():
    assignment = TaskAssignment(distributed_task_id=uuid4(), worker_id=uuid4(), attempt=1)
    assert assignment.task_id == assignment.distributed_task_id
    assert assignment.attempt == 1
    assert assignment.is_final is False

    result = DistributedTaskResult.ok(assignment.task_id)
    assignment.mark_result_into(result)
    assert assignment.status is AssignmentStatus.COMPLETED
    assert assignment.is_final is True
    assert assignment.completed_at is not None

    failed = TaskAssignment(distributed_task_id=uuid4(), worker_id=uuid4())
    failed.mark_result_into(
        DistributedTaskResult.fail(failed.task_id, error="x")
    )
    assert failed.status is AssignmentStatus.FAILED

    timed = TaskAssignment(distributed_task_id=uuid4(), worker_id=uuid4())
    timed.mark_timed_out()
    assert timed.status is AssignmentStatus.TIMED_OUT
    assert timed.is_final is True


# ----------------------------------------------------------------------
# DistributedTaskResult
# ----------------------------------------------------------------------


def test_result_factories():
    task_id = uuid4()
    ok = DistributedTaskResult.ok(task_id, output="hello", output_reference="ref")
    assert ok.success is True
    assert ok.output == "hello"
    assert ok.output_reference == "ref"
    assert ok.error is None

    failed = DistributedTaskResult.fail(task_id, error="nope")
    assert failed.success is False
    assert failed.error == "nope"


def test_result_rejects_blank_strings():
    with pytest.raises(ValidationError):
        DistributedTaskResult(distributed_task_id=uuid4(), success=True, output="   ")
    with pytest.raises(ValidationError):
        DistributedTaskResult(distributed_task_id=uuid4(), success=False, error="")
