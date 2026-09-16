import asyncio

from app.distributed.executor import FakeWorkerExecutor
from app.distributed.fakes import FakeMasterTransport
from app.distributed.models import (
    DistributedTask,
    WorkerInfo,
    WorkerResources,
    WorkerStatus,
)
from app.distributed.service import WorkerService


def _run(coro):
    return asyncio.run(coro)


def _service(**kwargs) -> WorkerService:
    info = kwargs.pop(
        "info",
        WorkerInfo(
            worker_name="worker-a",
            capabilities=frozenset({"analysis"}),
            resources=WorkerResources(current_load=0.2),
        ),
    )
    executor = kwargs.pop("executor", FakeWorkerExecutor())
    transport = kwargs.pop("master_transport", None)
    return WorkerService(
        worker_info=info,
        executor=executor,
        master_transport=transport,
    )


def test_worker_properties():
    service = _service()
    assert service.worker_id == service.worker_info.worker_id
    assert service.executor is not None


def test_register_without_transport_returns_false():
    service = _service()
    assert _run(service.register_with_master()) is False


def test_register_with_transport_records_registration():
    transport = FakeMasterTransport()
    service = _service(master_transport=transport)
    assert _run(service.register_with_master()) is True
    assert transport.registrations == (service.worker_info,)


def test_register_with_failing_transport_returns_false():
    transport = FakeMasterTransport(fail_register=True)
    service = _service(master_transport=transport)
    assert _run(service.register_with_master()) is False


def test_send_heartbeat_records_payload():
    transport = FakeMasterTransport()
    service = _service(master_transport=transport)
    assert _run(service.send_heartbeat(status=WorkerStatus.BUSY)) is True
    assert len(transport.heartbeats) == 1
    heartbeat = transport.heartbeats[0]
    assert heartbeat.worker_id == service.worker_id
    assert heartbeat.status is WorkerStatus.BUSY
    assert heartbeat.capabilities == frozenset({"analysis"})
    assert heartbeat.resources.current_load == 0.2


def test_send_heartbeat_without_transport_returns_false():
    service = _service()
    assert _run(service.send_heartbeat()) is False


def test_handle_task_executes_via_executor():
    executor = FakeWorkerExecutor(output="result-text")
    service = _service(executor=executor)
    task = DistributedTask(task_type="analysis", required_capabilities=frozenset({"analysis"}))
    result = _run(service.handle_task(task))
    assert result.success is True
    assert result.output == "result-text"
    assert result.worker_id == service.worker_id


def test_handle_task_propagates_assignment_id():
    service = _service()
    task = DistributedTask(task_type="analysis", required_capabilities=frozenset({"analysis"}))
    from uuid import uuid4

    assignment_id = uuid4()
    result = _run(service.handle_task(task, assignment_id=assignment_id))
    assert result.assignment_id == assignment_id


def test_handle_task_rejects_unapproved_task():
    executor = FakeWorkerExecutor(allowed_task_types=frozenset({"analysis"}))
    service = _service(executor=executor)
    task = DistributedTask(task_type="shell")
    result = _run(service.handle_task(task))
    assert result.success is False
    assert "unsupported task type" in result.error


def test_heartbeat_loop_stops_when_exit_event_set():
    transport = FakeMasterTransport()
    service = _service(master_transport=transport)

    async def run():
        exit_event = asyncio.Event()
        exit_event.set()
        await service.heartbeat_loop(interval=0.001, exit_event=exit_event)

    _run(run())
    # Event was already set, so the loop exits without sending a heartbeat.
    assert transport.heartbeats == ()
