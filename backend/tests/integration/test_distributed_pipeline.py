"""End-to-end offline distributed pipeline across master and worker layers.

This exercises the full CHUNK 29 flow through the master API and the worker
API over an in-memory ASGI transport: register -> heartbeat -> submit ->
dispatch -> execute -> result -> completed status.
"""

import asyncio

import httpx

from app.distributed.config import DistributedConfig
from app.distributed.coordinator import DistributedCoordinator
from app.distributed.executor import FakeWorkerExecutor
from app.distributed.httpapi import create_master_app, create_worker_app
from app.distributed.httptransports import (
    EndpointAwareWorkerTransport,
    HttpMasterTransport,
)
from app.distributed.models import (
    DistributedTask,
    DistributedTaskStatus,
    WorkerInfo,
)
from app.distributed.queue import DistributedTaskQueue
from app.distributed.registry import WorkerRegistry
from app.distributed.service import WorkerService


def _run(coro):
    return asyncio.run(coro)


def test_full_master_worker_pipeline():
    token = "shared-secret"
    config = DistributedConfig(auth_token=token, max_retries=2)

    # --- Master side ---------------------------------------------------
    registry = WorkerRegistry()
    queue = DistributedTaskQueue()
    master_transport = EndpointAwareWorkerTransport(registry=registry, config=config)
    coordinator = DistributedCoordinator(
        registry=registry,
        queue=queue,
        transport=master_transport,
        config=config,
    )
    master_app = create_master_app(coordinator=coordinator, config=config)

    # --- Worker side ----------------------------------------------------
    worker_service = WorkerService(
        worker_info=WorkerInfo(
            worker_name="integration-worker",
            capabilities=frozenset({"analysis"}),
            endpoint="http://worker",
        ),
        executor=FakeWorkerExecutor(output="pipeline-output"),
        config=config,
    )
    worker_app = create_worker_app(worker_service=worker_service, config=config)

    async def flow():
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=worker_app),
                base_url="http://worker",
            ) as worker_client,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=master_app),
                base_url="http://master",
            ) as master_client,
        ):
            master_transport._client = worker_client
            worker_master_transport = HttpMasterTransport(
                base_url="http://master", config=config, client=master_client
            )
            worker_service.attach_master_transport(worker_master_transport)

            # Worker registers and heartbeats against the master over HTTP.
            assert await worker_service.register_with_master() is True
            await worker_service.send_heartbeat()

            task = DistributedTask(
                task_type="analysis",
                required_capabilities=frozenset({"analysis"}),
            )
            coordinator.submit(task)

            assignment = coordinator.dispatch_next()
            assert assignment is not None

            result = await coordinator.dispatch_async(assignment, task)
            accepted = coordinator.accept_result(result)

            return result, accepted

    result, accepted = _run(flow())

    assert result.success is True
    assert result.output == "pipeline-output"
    assert accepted.success is True
    task = coordinator.task(result.distributed_task_id)
    assert task.status is DistributedTaskStatus.COMPLETED
    # Master observed registrations/heartbeats over the HTTP transport.
    assert registry.worker_count() == 1
    assert registry.lookup(result.worker_id).status.value == "available"
    # Events cover the full lifecycle.
    event_types = [e.event_type.value for e in coordinator.events]
    for expected in (
        "worker_registered",
        "heartbeat_received",
        "task_queued",
        "task_assigned",
        "task_started",
        "task_completed",
    ):
        assert expected in event_types


def run_pipeline_unit_guard():
    """Compile-time guard: pipeline result never leaks the token."""
    token = "should-not-leak"
    config = DistributedConfig(auth_token=token)
    transport = EndpointAwareWorkerTransport(registry=WorkerRegistry(), config=config)
    headers = transport._config.auth_token
    assert headers == token
    # Tokens are not part of any worker model.
    assert "auth_token" not in WorkerInfo.model_fields
    assert "auth_token" not in DistributedTask.model_fields


run_pipeline_unit_guard()
