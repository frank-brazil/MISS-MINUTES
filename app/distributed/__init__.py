"""MISSMINUTES distributed multi-machine layer (CHUNK 29).

A master coordinator dispatches typed tasks to workers across machines.
Workers only ever execute their registered, approved, typed operations; the
layered boundaries (authenticated HTTP transports, capability-gated
executors, deduplicated result handling) keep untrusted network surface away
from core orchestration.

Public surface (imports below) is stable; internals (registry/queue internals,
configuration constants) are not.

Typical wiring (offline, deterministic):

    registry = WorkerRegistry()
    queue = DistributedTaskQueue()
    transport = FakeWorkerTransport(executor=FakeWorkerExecutor())
    coordinator = DistributedCoordinator(registry=..., queue=..., transport=...)

For network use, swap ``transport`` for ``HttpWorkerTransport`` /
``EndpointAwareWorkerTransport`` and the worker for ``WorkerService`` behind
``create_worker_app``.
"""

from app.distributed.adapter import DistributedAdapter, DistributedExecutionResult
from app.distributed.auth import build_auth_dependency, request_headers
from app.distributed.config import DistributedConfig
from app.distributed.coordinator import DistributedCoordinator
from app.distributed.events import (
    DistributedEvent,
    DistributedEventType,
)
from app.distributed.executor import (
    FakeWorkerExecutor,
    WorkerExecutor,
)
from app.distributed.fakes import FakeMasterTransport, FakeWorkerTransport
from app.distributed.httpapi import create_master_app, create_worker_app
from app.distributed.httptransports import (
    EndpointAwareWorkerTransport,
    HttpMasterTransport,
    HttpWorkerTransport,
)
from app.distributed.models import (
    AssignmentStatus,
    DistributedTask,
    DistributedTaskResult,
    DistributedTaskStatus,
    TaskAssignment,
    WorkerCapability,
    WorkerHeartbeat,
    WorkerInfo,
    WorkerResources,
    WorkerStatus,
)
from app.distributed.queue import (
    DistributedTaskQueue,
    DuplicateTaskError,
)
from app.distributed.registry import (
    DuplicateWorkerError,
    UnknownWorkerError,
    WorkerRegistry,
)
from app.distributed.scheduler import (
    DistributedScheduler,
    NoEligibleWorkerError,
)
from app.distributed.service import WorkerService
from app.distributed.transport import (
    MasterTransport,
    TransportError,
    WorkerTransport,
    WorkerUnreachableError,
)

__all__ = [
    "AssignmentStatus",
    "DistributedAdapter",
    "DistributedConfig",
    "DistributedCoordinator",
    "DistributedEvent",
    "DistributedEventType",
    "DistributedExecutionResult",
    "DistributedScheduler",
    "DistributedTask",
    "DistributedTaskQueue",
    "DistributedTaskResult",
    "DistributedTaskStatus",
    "DuplicateTaskError",
    "DuplicateWorkerError",
    "EndpointAwareWorkerTransport",
    "FakeMasterTransport",
    "FakeWorkerExecutor",
    "FakeWorkerTransport",
    "HttpMasterTransport",
    "HttpWorkerTransport",
    "MasterTransport",
    "NoEligibleWorkerError",
    "TaskAssignment",
    "TransportError",
    "UnknownWorkerError",
    "WorkerCapability",
    "WorkerExecutor",
    "WorkerHeartbeat",
    "WorkerInfo",
    "WorkerRegistry",
    "WorkerResources",
    "WorkerService",
    "WorkerStatus",
    "WorkerTransport",
    "WorkerUnreachableError",
    "build_auth_dependency",
    "create_master_app",
    "create_worker_app",
    "request_headers",
]