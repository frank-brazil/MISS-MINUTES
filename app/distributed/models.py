"""Typed data models for the distributed multi-machine layer.

These models describe workers, the typed tasks they accept, assignments to a
specific worker, heartbeats, and structured results.  They deliberately reuse
the project's conventions (Pydantic models with ``validate_assignment=True``,
String enums, ``_utc_now`` timestamps) and the existing capability model from
``app.core.planner`` / ``app.core.task`` (capabilities are plain string tags).

Safety notes:

- **WorkerInfo never carries secrets.**  The endpoint field is a network
  address only; authentication tokens and credentials live in transport
  configuration, never in these models.
- **Capabilities are typed tags, not code.**  A capability (``"coding"``,
  ``"vision"``) tells the scheduler which worker *category* can handle a task.
  It is never executed as a command.
- **Resources are scheduling metadata.**  CPU/memory/GPU/load fields help a
  deterministic scheduler pick a worker; they are never presented as a claim
  about measured performance.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: A capability tag (``"coding"``, ``"vision"``, ...).  Plain strings keep the
#: distributed layer consistent with ``PlanStep.required_capabilities``.
WorkerCapability = str


def _utc_now() -> datetime:
    return datetime.now(UTC)


class WorkerStatus(StrEnum):
    """Lifecycle status of a worker as seen by the master."""

    AVAILABLE = "available"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"
    STALE = "stale"


class WorkerResources(BaseModel):
    """Coarse resource metadata reported by a worker.

    These values are scheduling hints, not performance guarantees.
    """

    model_config = ConfigDict(validate_assignment=True)

    cpu_count: int | None = None
    memory_bytes: int | None = None
    gpu_count: int | None = None
    gpu_available: bool = False
    current_load: float = 0.0
    labels: dict[str, str] = Field(default_factory=dict)

    @field_validator("cpu_count", "gpu_count")
    @classmethod
    def _positive_counts(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("cpu_count and gpu_count must be at least 1")
        return value

    @field_validator("memory_bytes")
    @classmethod
    def _non_negative_memory(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("memory_bytes must not be negative")
        return value

    @field_validator("current_load")
    @classmethod
    def _load_in_range(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("current_load must be between 0 and 1")
        return value


class WorkerInfo(BaseModel):
    """A worker as known to the master.

    Deliberately contains **no secrets**: no token, no password, no
    credential.  ``endpoint`` is a plain network address used by transports.
    """

    model_config = ConfigDict(validate_assignment=True)

    worker_id: UUID = Field(default_factory=uuid4)
    worker_name: str
    host: str | None = None
    platform: str | None = None
    protocol_version: str = "1.0"
    capabilities: frozenset[WorkerCapability] = Field(default_factory=frozenset)
    resources: WorkerResources = Field(default_factory=WorkerResources)
    status: WorkerStatus = WorkerStatus.AVAILABLE
    endpoint: str | None = None
    transport_name: str | None = None
    registered_at: datetime = Field(default_factory=_utc_now)
    last_heartbeat: datetime = Field(default_factory=_utc_now)
    assignment_count: int = 0

    @field_validator("worker_name", "host", "platform", "endpoint", "transport_name")
    @classmethod
    def _optional_blank(
        cls, value: str | None
    ) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("worker_name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("worker_name must not be blank")
        return value

    @field_validator("capabilities")
    @classmethod
    def _capabilities_not_blank(
        cls, value: frozenset[WorkerCapability]
    ) -> frozenset[WorkerCapability]:
        for capability in value:
            if not capability.strip():
                raise ValueError("capabilities must not be blank")
        return value

    @field_validator("assignment_count")
    @classmethod
    def _assignment_count_not_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("assignment_count must not be negative")
        return value


class WorkerHeartbeat(BaseModel):
    """Periodic status report a worker sends to the master."""

    model_config = ConfigDict(validate_assignment=True)

    heartbeat_id: UUID = Field(default_factory=uuid4)
    worker_id: UUID
    status: WorkerStatus = WorkerStatus.AVAILABLE
    capabilities: frozenset[WorkerCapability] | None = None
    resources: WorkerResources | None = None
    timestamp: datetime = Field(default_factory=_utc_now)

    @field_validator("capabilities")
    @classmethod
    def _capabilities_not_blank(
        cls, value: frozenset[WorkerCapability] | None
    ) -> frozenset[WorkerCapability] | None:
        for capability in value or frozenset():
            if not capability.strip():
                raise ValueError("capabilities must not be blank")
        return value


class DistributedTaskStatus(StrEnum):
    """Lifecycle of a distributed task across the cluster."""

    PENDING = "pending"
    QUEUED = "queued"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DistributedTask(BaseModel):
    """A typed task that a worker is allowed to execute.

    ``task_type`` identifies an **approved** typed operation (for example
    ``"analysis"``, ``"research"``, ``"coding"``).  It is not a shell command:
    a worker only runs operations its executor registers for that type and
    capability set.  ``description`` may carry a short human-readable summary;
    it is never logged, and workers never treat it as an instruction.
    """

    model_config = ConfigDict(validate_assignment=True)

    distributed_task_id: UUID = Field(default_factory=uuid4)
    task_type: str
    required_capabilities: frozenset[WorkerCapability] = Field(
        default_factory=frozenset
    )
    description: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    max_retries: int | None = None
    retry_count: int = 0
    status: DistributedTaskStatus = DistributedTaskStatus.PENDING
    last_assigned_worker_id: UUID | None = None
    last_error: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("task_type", "description")
    @classmethod
    def _not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("task_type")
    @classmethod
    def _task_type_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task_type must not be blank")
        return value

    @field_validator("required_capabilities")
    @classmethod
    def _capabilities_not_blank(
        cls, value: frozenset[WorkerCapability]
    ) -> frozenset[WorkerCapability]:
        for capability in value:
            if not capability.strip():
                raise ValueError("required capabilities must not be blank")
        return value

    @field_validator("retry_count", "max_retries")
    @classmethod
    def _retries_not_negative(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("retries must not be negative")
        return value

    def change_status(self, new_status: DistributedTaskStatus) -> None:
        self.status = new_status
        self.updated_at = _utc_now()

    # ------------------------------------------------------------------
    # Lifecycle helpers (used by the master coordinator)
    # ------------------------------------------------------------------

    @property
    def attempt_count(self) -> int:
        """Number of attempts already consumed (alias for ``retry_count``)."""
        return self.retry_count

    @property
    def locked_by(self) -> UUID | None:
        """Worker the task is currently assigned to, if any."""
        return self.last_assigned_worker_id

    def bump_attempt(self) -> None:
        """Consume one attempt when a new assignment is created."""
        self.retry_count += 1
        self.updated_at = _utc_now()

    def assign_to(self, worker_id: UUID) -> None:
        """Bind the task to a worker and move it to ASSIGNED."""
        self.last_assigned_worker_id = worker_id
        self.change_status(DistributedTaskStatus.ASSIGNED)

    def release_worker(self) -> None:
        """Detach the task from its worker without changing task status."""
        self.last_assigned_worker_id = None
        self.updated_at = _utc_now()

    def complete_with(self, result: "DistributedTaskResult") -> None:
        """Mark the task completed with the worker's structured result."""
        self.last_error = result.error
        self.change_status(
            DistributedTaskStatus.COMPLETED
            if result.success
            else DistributedTaskStatus.FAILED
        )

    def mark_failed(self, reason: str) -> None:
        """Mark the task permanently failed."""
        self.last_error = reason
        self.change_status(DistributedTaskStatus.FAILED)


class AssignmentStatus(StrEnum):
    PENDING = "pending"
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class TaskAssignment(BaseModel):
    """Binding of a distributed task to one worker for one attempt."""

    model_config = ConfigDict(validate_assignment=True)

    assignment_id: UUID = Field(default_factory=uuid4)
    distributed_task_id: UUID
    worker_id: UUID
    worker_name: str | None = None
    attempt: int = 0
    status: AssignmentStatus = AssignmentStatus.PENDING
    assigned_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = None

    @property
    def task_id(self) -> UUID:
        """Alias so the coordinator reads uniformly."""
        return self.distributed_task_id

    @property
    def is_final(self) -> bool:
        return self.status in (
            AssignmentStatus.COMPLETED,
            AssignmentStatus.FAILED,
            AssignmentStatus.TIMED_OUT,
        )

    def mark_result_into(self, result: "DistributedTaskResult") -> None:
        """Finalize this assignment from the worker's structured result."""
        self.completed_at = _utc_now()
        self.status = (
            AssignmentStatus.COMPLETED
            if result.success
            else AssignmentStatus.FAILED
        )

    def mark_timed_out(self) -> None:
        self.completed_at = _utc_now()
        self.status = AssignmentStatus.TIMED_OUT


class DistributedTaskResult(BaseModel):
    """Structured result a worker returns for a typed distributed task.

    ``assignment_id`` lets the master deduplicate duplicate worker responses:
    a completed assignment is applied exactly once.
    """

    model_config = ConfigDict(validate_assignment=True)

    distributed_task_id: UUID
    assignment_id: UUID | None = None
    worker_id: UUID | None = None
    success: bool
    output: str | None = None
    output_reference: str | None = None
    error: str | None = None
    started_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime = Field(default_factory=_utc_now)

    @field_validator("output", "output_reference", "error")
    @classmethod
    def _optional_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value

    @classmethod
    def ok(
        cls,
        distributed_task_id: UUID,
        *,
        assignment_id: UUID | None = None,
        worker_id: UUID | None = None,
        output: str | None = None,
        output_reference: str | None = None,
    ) -> "DistributedTaskResult":
        return cls(
            distributed_task_id=distributed_task_id,
            assignment_id=assignment_id,
            worker_id=worker_id,
            success=True,
            output=output,
            output_reference=output_reference,
        )

    @classmethod
    def fail(
        cls,
        distributed_task_id: UUID,
        *,
        assignment_id: UUID | None = None,
        worker_id: UUID | None = None,
        error: str,
        output: str | None = None,
    ) -> "DistributedTaskResult":
        return cls(
            distributed_task_id=distributed_task_id,
            assignment_id=assignment_id,
            worker_id=worker_id,
            success=False,
            error=error,
            output=output,
        )
