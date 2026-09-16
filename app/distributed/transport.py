"""Provider-independent transport abstractions for the distributed layer.

Two directions are modelled:

- ``WorkerTransport``: the **master → worker** path used to dispatch a typed
  task and receive the structured result (implementations: in-memory fakes
  for tests, an HTTP client for network use).
- ``MasterTransport``: the **worker → master** path used to register a worker
  and send heartbeats (implementations: in-memory fakes, an HTTP client).

Core scheduling/coordination code only depends on these interfaces, never on
HTTP.
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from app.distributed.models import (
    DistributedTask,
    DistributedTaskResult,
    TaskAssignment,
    WorkerHeartbeat,
    WorkerInfo,
)


class TransportError(Exception):
    """Base error for transport failures (network, timeout, protocol)."""


class WorkerUnreachableError(TransportError):
    """A worker could not be reached for dispatch."""


class WorkerTransport(ABC):
    name: ClassVar[str]
    description: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        missing = [
            attribute
            for attribute in ("name", "description")
            if not hasattr(cls, attribute)
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} must define required attribute(s): "
                f"{', '.join(missing)}"
            )

    @abstractmethod
    async def dispatch_task(
        self,
        assignment: TaskAssignment,
        task: DistributedTask,
    ) -> DistributedTaskResult:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError


class MasterTransport(ABC):
    name: ClassVar[str]
    description: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        missing = [
            attribute
            for attribute in ("name", "description")
            if not hasattr(cls, attribute)
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} must define required attribute(s): "
                f"{', '.join(missing)}"
            )

    @abstractmethod
    async def register_worker(self, info: WorkerInfo) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def send_heartbeat(self, heartbeat: WorkerHeartbeat) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError


def transport_error_from(exc: Exception) -> TransportError:
    """Convert an arbitrary exception into a typed transport error."""
    if isinstance(exc, TransportError):
        return exc
    return TransportError(
        f"{type(exc).__name__}: {_safe_message(exc)}"
    )


def _safe_message(exc: Exception) -> str:
    text = str(exc) or type(exc).__name__
    return text[:200]
