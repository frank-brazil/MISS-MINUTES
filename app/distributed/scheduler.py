"""Deterministic distributed task scheduler.

Selection policy (in order):

1. **Capability matching**: candidates must declare every
   ``task.required_capabilities`` tag.
2. **Status**: only ``AVAILABLE`` (and non-stale) workers are candidates.
3. **Load tie-break**: candidates are sorted by ``current_load`` ascending.
4. **Deterministic tie-break**: equal loads are ordered by worker ID
   ascending, so selection is fully deterministic and reproducible offline.

The load value is coarse scheduling metadata, not a measured performance
claim.

No AI-based scheduling is implemented.

A task with an empty required-capability set is eligible on any available
worker (matching the existing ``AgentRouter`` behaviour for empty sets).
"""

from collections.abc import Callable
from uuid import UUID

from app.distributed.models import (
    DistributedTask,
    WorkerCapability,
    WorkerInfo,
    WorkerStatus,
)


class NoEligibleWorkerError(Exception):
    """Raised when no worker can currently handle a task."""

    def __init__(self, required: frozenset[WorkerCapability]) -> None:
        self.required = required
        super().__init__(
            f"no eligible worker for required capabilities "
            f"{sorted(required)}"
        )


class DistributedScheduler:
    name = "deterministic-load-balancing"

    def eligible(
        self,
        task: DistributedTask,
        workers,
        *,
        is_stale: Callable | None = None,
    ) -> tuple[WorkerInfo, ...]:
        """Candidates for ``task``: available, capable, non-stale workers.

        ``is_stale`` lets the caller (coordinator) inject its heartbeat-based
        staleness check without the scheduler owning time.
        """
        candidates: list[WorkerInfo] = []
        for worker in workers:
            if worker.status is not WorkerStatus.AVAILABLE:
                continue
            if task.required_capabilities and not (
                task.required_capabilities <= worker.capabilities
            ):
                continue
            if is_stale is not None and is_stale(worker):
                continue
            candidates.append(worker)
        candidates.sort(key=lambda w: (w.resources.current_load, w.worker_id))
        return tuple(candidates)

    def select_worker(
        self,
        task: DistributedTask,
        workers,
        *,
        is_stale: Callable | None = None,
    ) -> WorkerInfo:
        """Pick the best currently-eligible worker per the documented policy."""
        candidates = self.eligible(task, workers, is_stale=is_stale)
        if not candidates:
            raise NoEligibleWorkerError(task.required_capabilities)
        return candidates[0]


def capability_rank(worker: WorkerInfo, required: frozenset[WorkerCapability]) -> int:
    """Count of required capabilities covered; used only for diagnostics."""
    return len(worker.capabilities & required)


def stable_worker_key(worker: WorkerInfo) -> tuple[float, UUID]:
    """Deterministic ordering key: load first, then worker ID."""
    return (worker.resources.current_load, worker.worker_id)