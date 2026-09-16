from uuid import UUID, uuid4

import pytest

from app.distributed.models import (
    DistributedTask,
    WorkerInfo,
    WorkerResources,
    WorkerStatus,
)
from app.distributed.scheduler import (
    DistributedScheduler,
    NoEligibleWorkerError,
    capability_rank,
    stable_worker_key,
)


def _worker(
    *,
    name: str = "worker",
    capabilities: frozenset[str] = frozenset({"coding"}),
    load: float = 0.0,
    status: WorkerStatus = WorkerStatus.AVAILABLE,
    worker_id: UUID | None = None,
) -> WorkerInfo:
    info = WorkerInfo(
        worker_name=name,
        capabilities=capabilities,
        resources=WorkerResources(current_load=load),
        status=status,
    )
    if worker_id is not None:
        info.worker_id = worker_id
    return info


def test_selects_only_capable_available_workers():
    task = DistributedTask(task_type="coding", required_capabilities=frozenset({"coding"}))
    capable = _worker(name="capable", capabilities=frozenset({"coding"}))
    incapable = _worker(name="incapable", capabilities=frozenset({"vision"}))
    busy = _worker(name="busy", capabilities=frozenset({"coding"}), status=WorkerStatus.BUSY)

    eligible = DistributedScheduler().eligible(task, [capable, incapable, busy])
    assert eligible == (capable,)


def test_empty_required_capabilities_matches_any_available_worker():
    task = DistributedTask(task_type="analysis")
    worker = _worker(capabilities=frozenset())
    eligible = DistributedScheduler().eligible(task, [worker])
    assert eligible == (worker,)


def test_load_tie_break_prefers_lower_load():
    task = DistributedTask(task_type="coding", required_capabilities=frozenset({"coding"}))
    low = _worker(name="low", load=0.1)
    high = _worker(name="high", load=0.9)
    selected = DistributedScheduler().select_worker(task, [high, low])
    assert selected is low


def test_equal_load_is_deterministic_by_worker_id():
    task = DistributedTask(task_type="coding", required_capabilities=frozenset({"coding"}))
    id_a = UUID("00000000-0000-0000-0000-000000000001")
    id_b = UUID("00000000-0000-0000-0000-000000000002")
    worker_b = _worker(name="b", load=0.5, worker_id=id_b)
    worker_a = _worker(name="a", load=0.5, worker_id=id_a)

    scheduler = DistributedScheduler()
    assert scheduler.select_worker(task, [worker_b, worker_a]) is worker_a
    # Order of input does not change the result.
    assert scheduler.select_worker(task, [worker_a, worker_b]) is worker_a


def test_raises_when_no_eligible_worker():
    task = DistributedTask(task_type="coding", required_capabilities=frozenset({"coding"}))
    with pytest.raises(NoEligibleWorkerError) as excinfo:
        DistributedScheduler().select_worker(task, [])
    assert "coding" in str(excinfo.value)
    assert excinfo.value.required == frozenset({"coding"})


def test_is_stale_predicate_excludes_workers():
    task = DistributedTask(task_type="coding", required_capabilities=frozenset({"coding"}))
    fresh = _worker(name="fresh")
    stale = _worker(name="stale")

    def is_stale(worker: WorkerInfo) -> bool:
        return worker is stale

    eligible = DistributedScheduler().eligible(task, [fresh, stale], is_stale=is_stale)
    assert eligible == (fresh,)


def test_capability_rank_and_stable_key():
    worker = _worker(capabilities=frozenset({"coding", "vision"}), load=0.3)
    assert capability_rank(worker, frozenset({"coding"})) == 1
    assert capability_rank(worker, frozenset({"coding", "vision", "audio"})) == 2
    assert stable_worker_key(worker) == (0.3, worker.worker_id)
