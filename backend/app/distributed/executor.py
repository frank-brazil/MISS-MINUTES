"""Worker executor boundary.

A worker executes **only registered/approved typed operations**.  The
executor validates the task's ``task_type`` and capability requirements
against its declared allowed set and capabilities, then runs the matching
deterministic operation.  It never executes shell commands or arbitrary
payloads, and it never lets a distributed task bypass the existing
Tool/Agent abstractions.
"""

import logging
from abc import ABC, abstractmethod
from typing import ClassVar
from uuid import UUID

from app.distributed.models import (
    DistributedTask,
    DistributedTaskResult,
    WorkerCapability,
)


class UnsupportedCapabilityError(Exception):
    """A task requires capabilities the worker does not declare."""


class UnsupportedTaskError(Exception):
    """A task_type is not among the worker's approved operations."""


class WorkerExecutor(ABC):
    name: ClassVar[str]
    description: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        missing = [
            attribute for attribute in ("name", "description") if not hasattr(cls, attribute)
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} must define required attribute(s): {', '.join(missing)}"
            )

    @property
    def capabilities(self) -> frozenset[WorkerCapability]:
        raise NotImplementedError

    @property
    def allowed_task_types(self) -> frozenset[str]:
        raise NotImplementedError

    def validate(self, task: DistributedTask) -> str | None:
        """Return a human-readable error when the task is not approved."""
        unsupported = task.required_capabilities - self.capabilities
        if unsupported:
            return f"unsupported capability: {sorted(unsupported)[0]}"
        if task.task_type not in self.allowed_task_types:
            return f"unsupported task type: {task.task_type}"
        return None

    @abstractmethod
    async def execute(self, task: DistributedTask) -> DistributedTaskResult:
        raise NotImplementedError


class FakeWorkerExecutor(WorkerExecutor):
    """Deterministic, offline worker executor for tests and safe defaults.

    The fake accepts only its declared capabilities and task types, records
    every request, and produces scripted outcomes.  It never performs real
    work and never touches the network, screen, terminal or file system.
    """

    name = "fake-worker-executor"
    description = (
        "Deterministic worker executor that performs no real actions; used offline and in tests."
    )

    def __init__(
        self,
        *,
        capabilities: frozenset[WorkerCapability] = frozenset({"analysis", "research", "coding"}),
        allowed_task_types: frozenset[str] = frozenset({"analysis", "research", "coding", "test"}),
        output: str = "Task completed by fake worker executor.",
        fail_task_ids: frozenset[UUID] = frozenset(),
        fail_once_task_ids: frozenset[UUID] = frozenset(),
        raise_error: Exception | None = None,
    ) -> None:
        self._capabilities = frozenset(capabilities)
        self._allowed_task_types = frozenset(allowed_task_types)
        self._output = output
        self._fail_task_ids = frozenset(fail_task_ids)
        self._fail_once_task_ids = frozenset(fail_once_task_ids)
        self._raise_error = raise_error
        self._fail_attempts: dict[UUID, int] = {}
        self._requests: list[DistributedTask] = []
        self._logger = logging.getLogger(__name__)

    @property
    def capabilities(self) -> frozenset[WorkerCapability]:
        return self._capabilities

    @property
    def allowed_task_types(self) -> frozenset[str]:
        return self._allowed_task_types

    @property
    def requests(self) -> tuple[DistributedTask, ...]:
        return tuple(self._requests)

    async def execute(self, task: DistributedTask) -> DistributedTaskResult:
        self._requests.append(task)
        validation_error = self.validate(task)
        if validation_error is not None:
            self._logger.warning(
                "Fake worker executor rejected task: task_id=%s error=%s",
                task.distributed_task_id,
                validation_error,
            )
            return DistributedTaskResult.fail(task.distributed_task_id, error=validation_error)
        if self._raise_error is not None:
            self._logger.error(
                "Fake worker executor raising: %s",
                type(self._raise_error).__name__,
            )
            raise self._raise_error

        attempts = self._fail_attempts.get(task.distributed_task_id, 0)
        self._fail_attempts[task.distributed_task_id] = attempts + 1

        if task.distributed_task_id in self._fail_task_ids:
            return DistributedTaskResult.fail(
                task.distributed_task_id, error="simulated worker failure"
            )
        if task.distributed_task_id in self._fail_once_task_ids and attempts == 0:
            return DistributedTaskResult.fail(
                task.distributed_task_id, error="simulated first-attempt failure"
            )
        self._logger.info(
            "Fake worker executor executed: task_id=%s task_type=%s",
            task.distributed_task_id,
            task.task_type,
        )
        return DistributedTaskResult.ok(task.distributed_task_id, output=self._output)
