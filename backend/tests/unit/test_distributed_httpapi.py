from fastapi.testclient import TestClient

from app.distributed.auth import AUTH_HEADER
from app.distributed.config import DistributedConfig
from app.distributed.coordinator import DistributedCoordinator
from app.distributed.executor import FakeWorkerExecutor
from app.distributed.fakes import FakeWorkerTransport
from app.distributed.httpapi import create_master_app, create_worker_app
from app.distributed.models import (
    DistributedTask,
    WorkerHeartbeat,
    WorkerInfo,
)
from app.distributed.queue import DistributedTaskQueue
from app.distributed.registry import WorkerRegistry
from app.distributed.service import WorkerService


def _master_client(*, token=None, max_retries=2):
    config = DistributedConfig(auth_token=token, max_retries=max_retries)
    registry = WorkerRegistry()
    coordinator = DistributedCoordinator(
        registry=registry,
        queue=DistributedTaskQueue(),
        transport=FakeWorkerTransport(executor=FakeWorkerExecutor()),
        config=config,
    )
    app = create_master_app(coordinator=coordinator, config=config)
    return TestClient(app), coordinator, config


def _worker_client(*, token=None):
    config = DistributedConfig(auth_token=token)
    service = WorkerService(
        worker_info=WorkerInfo(worker_name="api-worker", capabilities=frozenset({"analysis"})),
        executor=FakeWorkerExecutor(output="api-output"),
        config=config,
    )
    app = create_worker_app(worker_service=service, config=config)
    return TestClient(app), service


# ----------------------------------------------------------------------
# Master API
# ----------------------------------------------------------------------


def test_register_worker_and_list():
    client, coordinator, _ = _master_client()
    info = WorkerInfo(worker_name="w1", capabilities=frozenset({"analysis"}))
    response = client.post("/distributed/workers/register", json=info.model_dump(mode="json"))
    assert response.status_code == 201
    assert coordinator.registry.worker_count() == 1

    listed = client.get("/distributed/workers")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_register_duplicate_returns_conflict():
    client, _, _ = _master_client()
    info = WorkerInfo(worker_name="w1")
    payload = info.model_dump(mode="json")
    assert client.post("/distributed/workers/register", json=payload).status_code == 201
    assert client.post("/distributed/workers/register", json=payload).status_code == 409


def test_heartbeat_unknown_worker_returns_404():
    client, _, _ = _master_client()
    heartbeat = WorkerHeartbeat(worker_id=WorkerInfo(worker_name="x").worker_id)
    response = client.post("/distributed/workers/heartbeat", json=heartbeat.model_dump(mode="json"))
    assert response.status_code == 404


def test_heartbeat_known_worker_succeeds():
    client, coordinator, _ = _master_client()
    info = WorkerInfo(worker_name="w1")
    client.post("/distributed/workers/register", json=info.model_dump(mode="json"))
    response = client.post(
        "/distributed/workers/heartbeat",
        json=WorkerHeartbeat(worker_id=info.worker_id).model_dump(mode="json"),
    )
    assert response.status_code == 200


def test_submit_and_list_and_cancel_task():
    client, coordinator, _ = _master_client()
    task = DistributedTask(task_type="analysis", required_capabilities=frozenset({"analysis"}))
    created = client.post("/distributed/tasks", json=task.model_dump(mode="json"))
    assert created.status_code == 202

    listed = client.get("/distributed/tasks")
    assert listed.status_code == 200
    body = listed.json()
    assert body[0]["status"] == "queued"

    cancelled = client.delete(f"/distributed/tasks/{task.distributed_task_id}")
    assert cancelled.status_code == 204
    assert coordinator.status_for(task.distributed_task_id).value == "cancelled"

    missing = client.delete(f"/distributed/tasks/{WorkerInfo(worker_name='x').worker_id}")
    assert missing.status_code == 404


def test_events_and_health():
    client, _, _ = _master_client()
    task = DistributedTask(task_type="analysis")
    client.post("/distributed/tasks", json=task.model_dump(mode="json"))

    events = client.get("/distributed/events")
    assert events.status_code == 200
    assert any(e["event_type"] == "task_queued" for e in events.json())

    health = client.get("/distributed/health")
    assert health.status_code == 200
    assert health.json()["role"] == "master"
    assert health.json()["queued"] == "1"


def test_master_auth_enforced_when_token_set():
    client, _, _ = _master_client(token="shared")
    # No token -> unauthorized
    assert client.get("/distributed/workers").status_code == 401
    # Correct token -> ok
    ok = client.get("/distributed/workers", headers={AUTH_HEADER: "shared"})
    assert ok.status_code == 200


# ----------------------------------------------------------------------
# Worker API
# ----------------------------------------------------------------------


def test_worker_execute_returns_result():
    client, _ = _worker_client()
    task = DistributedTask(task_type="analysis", required_capabilities=frozenset({"analysis"}))
    payload = {
        "assignment_id": str(WorkerInfo(worker_name="x").worker_id),
        "task": task.model_dump(mode="json"),
    }
    response = client.post("/distributed/execute", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["output"] == "api-output"


def test_worker_rejects_unapproved_task_type():
    client, _ = _worker_client()
    task = DistributedTask(task_type="shell")
    payload = {
        "assignment_id": str(WorkerInfo(worker_name="x").worker_id),
        "task": task.model_dump(mode="json"),
    }
    response = client.post("/distributed/execute", json=payload)
    assert response.status_code == 200
    assert response.json()["success"] is False


def test_worker_auth_enforced_when_token_set():
    client, _ = _worker_client(token="shared")
    task = DistributedTask(task_type="analysis")
    payload = {
        "assignment_id": str(WorkerInfo(worker_name="x").worker_id),
        "task": task.model_dump(mode="json"),
    }
    assert client.post("/distributed/execute", json=payload).status_code == 401
    ok = client.post(
        "/distributed/execute",
        json=payload,
        headers={AUTH_HEADER: "shared"},
    )
    assert ok.status_code == 200
