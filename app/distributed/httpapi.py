"""HTTP entrypoints for the distributed layer (master and worker apps).

- ``create_master_app`` exposes worker registration, heartbeats, typed-task
  intake (submit/cancel/snapshot) and observability events.
- ``create_worker_app`` exposes the single ``/distributed/execute`` endpoint
  the master calls to run one typed, approved task.

Both apps are protected by the shared-token dependency from ``auth`` (unless
the config has no token, in which case the loopback-only bind default
applies).  Neither app ever reveals the auth token, worker resources are
coarse metadata, and the worker only runs approved typed operations through
its injected ``WorkerExecutor``.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from app.distributed.auth import build_auth_dependency
from app.distributed.config import DistributedConfig
from app.distributed.coordinator import DistributedCoordinator
from app.distributed.events import DistributedEvent
from app.distributed.models import (
    DistributedTask,
    DistributedTaskResult,
    WorkerHeartbeat,
    WorkerInfo,
)
from app.distributed.registry import DuplicateWorkerError, UnknownWorkerError
from app.distributed.service import WorkerService


class WorkerExecuteRequest(BaseModel):
    """Body for master → worker dispatch."""

    model_config = ConfigDict(validate_assignment=True)

    assignment_id: UUID
    task: DistributedTask


class TaskSummary(BaseModel):
    """Lightweight, serializable snapshot of a distributed task."""

    model_config = ConfigDict(validate_assignment=True)

    distributed_task_id: UUID
    task_type: str
    status: str
    attempt_count: int
    worker_id: UUID | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_task(cls, task: DistributedTask) -> "TaskSummary":
        return cls(
            distributed_task_id=task.distributed_task_id,
            task_type=task.task_type,
            status=task.status.value,
            attempt_count=task.attempt_count,
            worker_id=task.last_assigned_worker_id,
            error=task.last_error,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=409, detail=message)


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


def create_worker_app(
    *,
    worker_service: WorkerService,
    config: DistributedConfig | None = None,
) -> FastAPI:
    """Build the worker-side FastAPI application.

    Exposes ``POST /distributed/execute`` which executes one typed task via
    the injected service (which validates it against the approving executor).
    """
    resolved = config or DistributedConfig()
    auth = build_auth_dependency(resolved)

    router = APIRouter(prefix="/distributed", dependencies=[Depends(auth)])

    @router.post(
        "/execute",
        response_model=DistributedTaskResult,
        status_code=200,
    )
    async def execute(req: WorkerExecuteRequest) -> DistributedTaskResult:
        """Run one typed task; only approved worker operations execute."""
        return await worker_service.handle_task(
            req.task, assignment_id=req.assignment_id
        )

    app = FastAPI(
        title="MISSMINUTES distributed worker",
        version="1.0",
        description=(
            "Executes approved typed distributed tasks submitted by a master."
        ),
    )
    app.include_router(router)
    return app


def create_master_app(
    *,
    coordinator: DistributedCoordinator,
    config: DistributedConfig | None = None,
) -> FastAPI:
    """Build the master-side FastAPI application.

    Exposes worker registration/heartbeats, typed task intake, cancellation
    and task/event introspection.  Dispatch to actual workers is performed by
    the coordinator's injected transport, not by this API layer.
    """
    resolved = config or DistributedConfig()
    auth = build_auth_dependency(resolved)
    registry = coordinator.registry

    router = APIRouter(prefix="/distributed", dependencies=[Depends(auth)])

    @router.post(
        "/workers/register",
        response_model=WorkerInfo,
        status_code=201,
    )
    async def register_worker(info: WorkerInfo) -> WorkerInfo:
        try:
            registered = registry.register(info)
        except DuplicateWorkerError as exc:
            raise _conflict(str(exc)) from exc
        coordinator.record_external_event(
            DistributedEvent(
                event_type="worker_registered",
                message=f"Worker '{info.worker_name}' registered over HTTP.",
                success=True,
                worker_id=info.worker_id,
            )
        )
        return registered

    @router.post(
        "/workers/heartbeat",
        response_model=WorkerInfo,
        status_code=200,
    )
    async def worker_heartbeat(heartbeat: WorkerHeartbeat) -> WorkerInfo:
        try:
            updated = registry.heartbeat(heartbeat)
        except UnknownWorkerError as exc:
            raise _not_found(str(exc)) from exc
        coordinator.record_external_event(
            DistributedEvent(
                event_type="heartbeat_received",
                message=f"Heartbeat from '{updated.worker_name}' over HTTP.",
                success=True,
                worker_id=updated.worker_id,
            )
        )
        return updated

    @router.get("/workers", response_model=list[WorkerInfo])
    async def list_workers() -> list[WorkerInfo]:
        return list(registry.list_workers())

    @router.post("/tasks", response_model=DistributedTask, status_code=202)
    async def submit_task(task: DistributedTask) -> DistributedTask:
        return coordinator.submit(task)

    @router.get("/tasks", response_model=list[TaskSummary])
    async def list_tasks() -> list[TaskSummary]:
        return [
            TaskSummary.from_task(task) for task in coordinator.known_tasks
        ]

    @router.delete("/tasks/{task_id}", status_code=204)
    async def cancel_task(task_id: UUID) -> None:
        cancelled = coordinator.cancel(task_id)
        if not cancelled:
            raise _not_found(f"task {task_id} is not cancellable")
        return None

    @router.get("/events", response_model=list[DistributedEvent])
    async def list_events() -> list[DistributedEvent]:
        return list(coordinator.events)

    @router.get("/health", status_code=200)
    async def health() -> dict[str, str]:
        return {
            "role": "master",
            "status": "ready",
            "workers": str(registry.worker_count()),
            "queued": str(coordinator.queue_depth),
        }

    app = FastAPI(
        title="MISSMINUTES distributed master",
        version="1.0",
        description=(
            "Coordinates typed distributed tasks across registered workers."
        ),
    )
    app.include_router(router)
    return app
