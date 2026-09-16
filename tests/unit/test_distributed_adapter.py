import asyncio

from app.core.planner import PlanStep
from app.distributed.adapter import DistributedAdapter, DistributedExecutionResult
from app.distributed.config import DistributedConfig
from app.distributed.coordinator import DistributedCoordinator
from app.distributed.executor import FakeWorkerExecutor
from app.distributed.fakes import FakeWorkerTransport
from app.distributed.models import DistributedTask, WorkerInfo
from app.distributed.queue import DistributedTaskQueue
from app.distributed.registry import WorkerRegistry


def _run(coro):
    return asyncio.run(coro)


def _adapter(*, max_retries=2, register=True, transport=None, executor=None, **kwargs):
    registry = WorkerRegistry()
    if register:
        registry.register(
            WorkerInfo(
                worker_name="adapter-worker",
                capabilities=frozenset({"analysis"}),
            )
        )
    queue = DistributedTaskQueue()
    transport = transport or FakeWorkerTransport(
        executor=executor or FakeWorkerExecutor(output="adapter-output")
    )
    coordinator = DistributedCoordinator(
        registry=registry,
        queue=queue,
        transport=transport,
        config=DistributedConfig(max_retries=max_retries),
    )
    return DistributedAdapter(coordinator, **kwargs), coordinator


def test_task_for_step_maps_plan_step():
    adapter, _ = _adapter()
    step = PlanStep(
        description="analyse the report",
        required_capabilities=frozenset({"analysis"}),
    )
    task = adapter.task_for_step(step)
    assert isinstance(task, DistributedTask)
    assert task.description == "analyse the report"
    assert task.required_capabilities == frozenset({"analysis"})
    assert task.context["step_id"] == str(step.step_id)


def test_submit_and_await_success():
    adapter, coordinator = _adapter()
    task = DistributedTask(task_type="analysis", required_capabilities=frozenset({"analysis"}))
    result = _run(adapter.submit_and_await_async(task))
    assert result.success is True
    assert result.output == "adapter-output"
    assert result.task_id == task.distributed_task_id
    assert result.attempts == 1
    assert coordinator.status_for(task.distributed_task_id).value == "completed"


def test_submit_and_await_fails_after_retries():
    task = DistributedTask(task_type="analysis", required_capabilities=frozenset({"analysis"}))
    adapter, coordinator = _adapter(
        max_retries=2,
        executor=FakeWorkerExecutor(
            fail_task_ids=frozenset({task.distributed_task_id})
        ),
    )
    result = _run(adapter.submit_and_await_async(task))
    assert result.success is False
    assert result.attempts <= 2
    assert result.error is not None
    assert coordinator.status_for(task.distributed_task_id).value == "failed"


def test_submit_and_await_succeeds_after_transient_failure():
    task = DistributedTask(task_type="analysis", required_capabilities=frozenset({"analysis"}))
    adapter, _ = _adapter(
        max_retries=2,
        executor=FakeWorkerExecutor(
            fail_once_task_ids=frozenset({task.distributed_task_id}),
        ),
    )
    result = _run(adapter.submit_and_await_async(task))
    assert result.success is True
    assert result.attempts == 2


def test_disabled_adapter_returns_early_failure():
    adapter, _ = _adapter(enabled=False)
    task = DistributedTask(task_type="analysis")
    result = _run(adapter.submit_and_await_async(task))
    assert result.success is False
    assert "disabled" in result.error


def test_result_factories():
    ok = DistributedExecutionResult.ok(
        output="x", task_id=WorkerInfo(worker_name="w").worker_id
    )
    assert ok.success is True
    failed = DistributedExecutionResult.fail(error="nope")
    assert failed.success is False
    assert failed.error == "nope"