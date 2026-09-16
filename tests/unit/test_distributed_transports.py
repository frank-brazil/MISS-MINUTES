import asyncio
from uuid import uuid4

import httpx
import pytest

from app.distributed.config import DistributedConfig
from app.distributed.coordinator import DistributedCoordinator
from app.distributed.executor import FakeWorkerExecutor
from app.distributed.fakes import FakeMasterTransport, FakeWorkerTransport
from app.distributed.httpapi import create_master_app, create_worker_app
from app.distributed.httptransports import (
    EndpointAwareWorkerTransport,
    HttpMasterTransport,
    HttpWorkerTransport,
)
from app.distributed.models import (
    DistributedTask,
    TaskAssignment,
    WorkerHeartbeat,
    WorkerInfo,
)
from app.distributed.queue import DistributedTaskQueue
from app.distributed.registry import WorkerRegistry
from app.distributed.service import WorkerService
from app.distributed.transport import (
    TransportError,
    WorkerUnreachableError,
    transport_error_from,
)


def _run(coro):
    return asyncio.run(coro)


def _task() -> DistributedTask:
    return DistributedTask(task_type="analysis", required_capabilities=frozenset({"analysis"}))


def _assignment(task: DistributedTask, worker_id=None) -> TaskAssignment:
    return TaskAssignment(
        distributed_task_id=task.distributed_task_id,
        worker_id=worker_id or uuid4(),
    )


# ----------------------------------------------------------------------
# In-memory fakes
# ----------------------------------------------------------------------


def test_fake_worker_transport_records_and_executes():
    transport = FakeWorkerTransport(executor=FakeWorkerExecutor(output="ok"))
    task = _task()
    assignment = _assignment(task)
    result = _run(transport.dispatch_task(assignment, task))
    assert result.success is True
    assert result.output == "ok"
    assert result.assignment_id == assignment.assignment_id
    assert transport.dispatch_count == 1


def test_fake_worker_transport_unreachable():
    transport = FakeWorkerTransport(fail=True, fail_message="down")
    with pytest.raises(WorkerUnreachableError) as excinfo:
        _run(transport.dispatch_task(_assignment(_task()), _task()))
    assert "down" in str(excinfo.value)


def test_fake_worker_transport_fail_once():
    transport = FakeWorkerTransport(fail_once=True)
    task = _task()
    with pytest.raises(WorkerUnreachableError):
        _run(transport.dispatch_task(_assignment(task), task))
    result = _run(transport.dispatch_task(_assignment(task), task))
    assert result.success is True


def test_fake_worker_transport_fails_specific_task():
    task = _task()
    transport = FakeWorkerTransport(fail_task_ids=frozenset({task.distributed_task_id}))
    result = _run(transport.dispatch_task(_assignment(task), task))
    assert result.success is False


def test_fake_worker_transport_raises_scripted_error():
    transport = FakeWorkerTransport(raise_error=RuntimeError("nope"))
    with pytest.raises(RuntimeError):
        _run(transport.dispatch_task(_assignment(_task()), _task()))


def test_fake_worker_transport_close_blocks_dispatch():
    transport = FakeWorkerTransport()
    _run(transport.close())
    with pytest.raises(WorkerUnreachableError):
        _run(transport.dispatch_task(_assignment(_task()), _task()))


def test_fake_master_transport_records_and_flags():
    transport = FakeMasterTransport()
    info = WorkerInfo(worker_name="w")
    heartbeat = WorkerHeartbeat(worker_id=info.worker_id)
    assert _run(transport.register_worker(info)) is True
    assert _run(transport.send_heartbeat(heartbeat)) is True
    assert transport.registrations == (info,)
    assert transport.heartbeats == (heartbeat,)

    failing = FakeMasterTransport(fail_register=True, fail_heartbeat=True)
    assert _run(failing.register_worker(info)) is False
    assert _run(failing.send_heartbeat(heartbeat)) is False


def test_transport_error_from_wraps_exceptions():
    original = TransportError("already typed")
    assert transport_error_from(original) is original
    wrapped = transport_error_from(ValueError("bad"))
    assert isinstance(wrapped, TransportError)
    assert "ValueError" in str(wrapped)


# ----------------------------------------------------------------------
# HTTP transports (offline, via ASGI transport)
# ----------------------------------------------------------------------


def _worker_app_and_config(token=None):
    config = DistributedConfig(auth_token=token)
    service = WorkerService(
        worker_info=WorkerInfo(
            worker_name="http-worker",
            capabilities=frozenset({"analysis"}),
        ),
        executor=FakeWorkerExecutor(output="http-output"),
        config=config,
    )
    return create_worker_app(worker_service=service, config=config), config


def test_http_worker_transport_round_trip():
    app, config = _worker_app_and_config()
    task = _task()
    assignment = _assignment(task)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://worker",
        ) as client:
            transport = HttpWorkerTransport(
                base_url="http://worker", config=config, client=client
            )
            return await transport.dispatch_task(assignment, task)

    result = _run(run())
    assert result.success is True
    assert result.output == "http-output"
    assert result.assignment_id == assignment.assignment_id


def test_http_worker_transport_sends_auth_token():
    app, config = _worker_app_and_config(token="shared")
    task = _task()

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://worker",
        ) as client:
            good = HttpWorkerTransport(
                base_url="http://worker",
                config=DistributedConfig(auth_token="shared"),
                client=client,
            )
            bad = HttpWorkerTransport(
                base_url="http://worker",
                config=DistributedConfig(auth_token="wrong"),
                client=client,
            )
            ok = await good.dispatch_task(_assignment(task), task)
            with pytest.raises(TransportError):
                await bad.dispatch_task(_assignment(task), task)
            return ok

    assert _run(run()).success is True


def test_http_worker_transport_unreachable_endpoint():
    config = DistributedConfig()

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_worker_app_and_config()[0]),
            base_url="http://worker",
        ) as client:
            transport = HttpWorkerTransport(
                base_url="http://worker", config=config, client=client
            )
            # The worker app has no /unknown/execute path; force 404 behaviour
            # by pointing at a non-existent base path.
            transport._base_url = "http://worker/missing"  # noqa: SLF001
            with pytest.raises(WorkerUnreachableError):
                await transport.dispatch_task(_assignment(_task()), _task())

    _run(run())


def _master_setup():
    config = DistributedConfig(max_retries=2)
    registry = WorkerRegistry()
    queue = DistributedTaskQueue()
    coordinator = DistributedCoordinator(
        registry=registry,
        queue=queue,
        transport=FakeWorkerTransport(),
        config=config,
    )
    app = create_master_app(coordinator=coordinator, config=config)
    return app, coordinator, config


def test_http_master_transport_registers_and_heartbeats():
    app, coordinator, config = _master_setup()
    info = WorkerInfo(worker_name="remote", capabilities=frozenset({"analysis"}))

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://master",
        ) as client:
            transport = HttpMasterTransport(
                base_url="http://master", config=config, client=client
            )
            registered = await transport.register_worker(info)
            heartbeat = await transport.send_heartbeat(
                WorkerHeartbeat(worker_id=info.worker_id)
            )
            return registered, heartbeat

    registered, heartbeat = _run(run())
    assert registered is True
    assert heartbeat is True
    assert coordinator.registry.worker_count() == 1


def test_endpoint_aware_transport_uses_registry_endpoint():
    worker_app, config = _worker_app_and_config()
    registry = WorkerRegistry()
    info = WorkerInfo(
        worker_name="endpoint-worker",
        capabilities=frozenset({"analysis"}),
        endpoint="http://worker",
    )
    registry.register(info)
    task = _task()
    assignment = _assignment(task, worker_id=info.worker_id)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=worker_app),
            base_url="http://worker",
        ) as client:
            transport = EndpointAwareWorkerTransport(
                registry=registry, config=config, client=client
            )
            return await transport.dispatch_task(assignment, task)

    result = _run(run())
    assert result.success is True
    assert result.output == "http-output"


def test_endpoint_aware_transport_unknown_worker():
    registry = WorkerRegistry()
    transport = EndpointAwareWorkerTransport(
        registry=registry,
        config=DistributedConfig(),
        client=httpx.AsyncClient(transport=httpx.ASGITransport(app=create_master_app(
            coordinator=DistributedCoordinator(
                registry=registry,
                queue=DistributedTaskQueue(),
                transport=FakeWorkerTransport(),
            )
        ))),
    )

    async def run():
        with pytest.raises(WorkerUnreachableError):
            await transport.dispatch_task(_assignment(_task()), _task())

    _run(run())
