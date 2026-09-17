from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.distributed.models import (
    WorkerHeartbeat,
    WorkerInfo,
    WorkerResources,
    WorkerStatus,
)
from app.distributed.registry import (
    DuplicateWorkerError,
    UnknownWorkerError,
    WorkerRegistry,
    register_event,
)


def _worker(**kwargs) -> WorkerInfo:
    return WorkerInfo(worker_name=kwargs.pop("worker_name", "worker-a"), **kwargs)


def test_register_and_lookup():
    registry = WorkerRegistry()
    info = _worker(capabilities=frozenset({"coding"}))
    registered = registry.register(info)
    assert registered is info
    assert registry.worker_count() == 1
    assert registry.lookup(info.worker_id) is info
    assert registry.require(info.worker_id) is info
    assert registry.list_workers() == (info,)


def test_register_rejects_duplicate():
    registry = WorkerRegistry()
    info = _worker()
    registry.register(info)
    with pytest.raises(DuplicateWorkerError):
        registry.register(info)


def test_require_unknown_raises():
    registry = WorkerRegistry()
    with pytest.raises(UnknownWorkerError):
        registry.require(uuid4())


def test_unregister_removes_worker():
    registry = WorkerRegistry()
    info = _worker()
    registry.register(info)
    assert registry.unregister(info.worker_id) is True
    assert registry.unregister(info.worker_id) is False
    assert registry.worker_count() == 0


def test_heartbeat_updates_status_and_timestamp():
    registry = WorkerRegistry()
    info = _worker(status=WorkerStatus.AVAILABLE)
    registry.register(info)

    moment = datetime.now(UTC)
    updated = registry.heartbeat(
        WorkerHeartbeat(worker_id=info.worker_id, status=WorkerStatus.BUSY),
        now=moment,
    )
    assert updated.status is WorkerStatus.BUSY
    assert updated.last_heartbeat == moment


def test_heartbeat_unknown_worker_raises():
    registry = WorkerRegistry()
    with pytest.raises(UnknownWorkerError):
        registry.heartbeat(WorkerHeartbeat(worker_id=uuid4()))


def test_heartbeat_updates_capabilities_and_resources():
    registry = WorkerRegistry()
    info = _worker(capabilities=frozenset({"coding"}))
    registry.register(info)
    resources = WorkerResources(current_load=0.5, cpu_count=4)
    registry.heartbeat(
        WorkerHeartbeat(
            worker_id=info.worker_id,
            capabilities=frozenset({"coding", "vision"}),
            resources=resources,
        )
    )
    assert info.capabilities == frozenset({"coding", "vision"})
    assert info.resources.current_load == 0.5


def test_update_status_and_mark_stale():
    registry = WorkerRegistry()
    info = _worker()
    registry.register(info)
    assert registry.update_status(info.worker_id, WorkerStatus.BUSY) is True
    assert info.status is WorkerStatus.BUSY
    assert registry.mark_stale(info.worker_id) is True
    assert info.status is WorkerStatus.STALE
    assert registry.update_status(uuid4(), WorkerStatus.BUSY) is False


def test_note_assignment_increments_count():
    registry = WorkerRegistry()
    info = _worker()
    registry.register(info)
    assert registry.note_assignment(info.worker_id) is True
    assert info.assignment_count == 1
    assert registry.note_assignment(uuid4()) is False


def test_filter_by_capabilities_is_subset():
    registry = WorkerRegistry()
    full = _worker(worker_name="full", capabilities=frozenset({"coding", "vision"}))
    partial = _worker(worker_name="partial", capabilities=frozenset({"coding"}))
    registry.register(full)
    registry.register(partial)

    matches = registry.filter_by_capabilities(frozenset({"coding", "vision"}))
    assert matches == (full,)
    assert registry.filter_by_capabilities(frozenset({"coding"})) == (full, partial)
    assert registry.filter_by_capabilities(frozenset({"unknown"})) == ()


def test_available_workers_filters_status():
    registry = WorkerRegistry()
    available = _worker(worker_name="a", status=WorkerStatus.AVAILABLE)
    busy = _worker(worker_name="b", status=WorkerStatus.BUSY)
    registry.register(available)
    registry.register(busy)
    assert registry.available_workers() == (available,)


def test_staleness_detection_with_injected_time():
    registry = WorkerRegistry()
    info = _worker()
    registry.register(info)
    now = datetime.now(UTC)
    registry.heartbeat(
        WorkerHeartbeat(worker_id=info.worker_id),
        now=now - timedelta(seconds=100),
    )

    assert registry.is_stale(info, timeout=30, now=now) is True
    assert registry.is_stale(info, timeout=200, now=now) is False
    assert registry.stale_workers(timeout=30, now=now) == (info,)
    assert registry.stale_workers(timeout=200, now=now) == ()


def test_register_event_is_safe():
    info = _worker()
    event = register_event(info)
    assert event.worker_id == info.worker_id
    assert "worker-a" in event.message
    assert event.success is True
