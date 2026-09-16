"""Worker registry: the master's source of truth about connected workers.

The registry is a plain in-memory map keyed by worker ID.  All callers run
inside the same asyncio event loop (the coordinator, HTTP handlers, tests),
so its synchronous methods are atomic between awaits and safe in that model.
No global mutable singleton is used: the registry is always injected.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from app.distributed.events import DistributedEvent, DistributedEventType
from app.distributed.models import (
    WorkerCapability,
    WorkerHeartbeat,
    WorkerInfo,
    WorkerStatus,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DuplicateWorkerError(Exception):
    """Raised when registering a worker ID that already exists."""


class UnknownWorkerError(Exception):
    """Raised when an operation refers to a worker the registry does not know."""


class WorkerRegistry:
    def __init__(self) -> None:
        self._workers: dict[UUID, WorkerInfo] = {}
        self._logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, info: WorkerInfo) -> WorkerInfo:
        """Register a worker, rejecting duplicate IDs.

        The registration timestamp doubles as the first heartbeat so a
        freshly registered worker is not immediately stale.
        """
        if info.worker_id in self._workers:
            raise DuplicateWorkerError(
                f"worker {info.worker_id} is already registered"
            )
        self._workers[info.worker_id] = info
        self._logger.info(
            "Worker registered: worker_id=%s name=%s capabilities=%s",
            info.worker_id,
            info.worker_name,
            sorted(info.capabilities),
        )
        return info

    def unregister(self, worker_id: UUID) -> bool:
        removed = self._workers.pop(worker_id, None) is not None
        if removed:
            self._logger.info("Worker removed: worker_id=%s", worker_id)
        return removed

    # ------------------------------------------------------------------
    # Heartbeats and status
    # ------------------------------------------------------------------

    def heartbeat(self, heartbeat: WorkerHeartbeat, *, now: datetime | None = None) -> WorkerInfo:
        """Apply a worker heartbeat, updating status/resources/load.

        Raises :class:`UnknownWorkerError` for heartbeats from workers the
        master never registered (a registration boundary is required).
        """
        worker = self._workers.get(heartbeat.worker_id)
        if worker is None:
            raise UnknownWorkerError(
                f"heartbeat for unknown worker {heartbeat.worker_id}"
            )
        timestamp = now if now is not None else _utc_now()
        worker.status = heartbeat.status
        worker.last_heartbeat = timestamp
        if heartbeat.capabilities is not None:
            worker.capabilities = heartbeat.capabilities
        if heartbeat.resources is not None:
            worker.resources = heartbeat.resources
        self._logger.info(
            "Heartbeat received: worker_id=%s status=%s",
            heartbeat.worker_id,
            heartbeat.status.value,
        )
        return worker

    def update_status(self, worker_id: UUID, status: WorkerStatus) -> bool:
        worker = self._workers.get(worker_id)
        if worker is None:
            return False
        worker.status = status
        return True

    def mark_stale(self, worker_id: UUID) -> bool:
        worker = self._workers.get(worker_id)
        if worker is None:
            return False
        worker.status = WorkerStatus.STALE
        return True

    def note_assignment(self, worker_id: UUID) -> bool:
        worker = self._workers.get(worker_id)
        if worker is None:
            return False
        worker.assignment_count += 1
        return True

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def lookup(self, worker_id: UUID) -> WorkerInfo | None:
        return self._workers.get(worker_id)

    def require(self, worker_id: UUID) -> WorkerInfo:
        worker = self._workers.get(worker_id)
        if worker is None:
            raise UnknownWorkerError(f"unknown worker {worker_id}")
        return worker

    def list_workers(self) -> tuple[WorkerInfo, ...]:
        return tuple(self._workers.values())

    def worker_count(self) -> int:
        return len(self._workers)

    def filter_by_capabilities(
        self, required: frozenset[WorkerCapability]
    ) -> tuple[WorkerInfo, ...]:
        """Workers whose declared capabilities cover ``required``."""
        return tuple(
            worker
            for worker in self._workers.values()
            if required <= worker.capabilities
        )

    def available_workers(self) -> tuple[WorkerInfo, ...]:
        """Workers currently marked available (status check only)."""
        return tuple(
            worker
            for worker in self._workers.values()
            if worker.status is WorkerStatus.AVAILABLE
        )

    # ------------------------------------------------------------------
    # Staleness
    # ------------------------------------------------------------------

    def stale_workers(
        self,
        *,
        timeout: float,
        now: datetime | None = None,
    ) -> tuple[WorkerInfo, ...]:
        """Workers whose last heartbeat is older than ``timeout`` seconds."""
        moment = now if now is not None else _utc_now()
        return tuple(
            worker
            for worker in self._workers.values()
            if _age(worker.last_heartbeat, moment) > timeout
        )

    def is_stale(self, worker: WorkerInfo, *, timeout: float, now: datetime | None = None) -> bool:
        moment = now if now is not None else _utc_now()
        return _age(worker.last_heartbeat, moment) > timeout


def _age(timestamp: datetime, now: datetime) -> float:
    return max((now - timestamp).total_seconds(), 0.0)


def register_event(worker: WorkerInfo) -> DistributedEvent:
    return DistributedEvent(
        event_type=DistributedEventType.WORKER_REGISTERED,
        message=f"Worker registered: '{worker.worker_name}'.",
        success=True,
        worker_id=worker.worker_id,
    )
