import asyncio

import pytest

from app.distributed.executor import (
    FakeWorkerExecutor,
    WorkerExecutor,
)
from app.distributed.models import DistributedTask


def _run(coro):
    return asyncio.run(coro)


def _task(task_type: str = "analysis", capabilities=frozenset({"analysis"})) -> DistributedTask:
    return DistributedTask(task_type=task_type, required_capabilities=capabilities)


def test_worker_executor_requires_name_and_description():
    with pytest.raises(TypeError):

        class Missing(WorkerExecutor):
            async def execute(self, task):  # pragma: no cover - never run
                raise NotImplementedError

    class Complete(WorkerExecutor):
        name = "complete"
        description = "a complete executor"

        @property
        def capabilities(self):
            return frozenset()

        @property
        def allowed_task_types(self):
            return frozenset()

        async def execute(self, task):  # pragma: no cover - never run
            raise NotImplementedError

    assert Complete.name == "complete"


def test_fake_executor_defaults_and_properties():
    executor = FakeWorkerExecutor()
    assert "analysis" in executor.capabilities
    assert "analysis" in executor.allowed_task_types
    assert executor.requests == ()


def test_validate_reports_unsupported_capability():
    executor = FakeWorkerExecutor(capabilities=frozenset({"analysis"}))
    task = _task(capabilities=frozenset({"vision"}))
    assert executor.validate(task) is not None


def test_validate_reports_unsupported_task_type():
    executor = FakeWorkerExecutor(allowed_task_types=frozenset({"analysis"}))
    task = _task(task_type="shell")
    assert executor.validate(task) is not None


def test_validate_accepts_matching_task():
    executor = FakeWorkerExecutor()
    assert executor.validate(_task()) is None


def test_execute_returns_success_and_records_request():
    executor = FakeWorkerExecutor(output="structured output")

    async def run():
        task = _task()
        result = await executor.execute(task)
        return task, result

    task, result = _run(run())
    assert result.success is True
    assert result.output == "structured output"
    assert result.distributed_task_id == task.distributed_task_id
    assert executor.requests == (task,)


def test_execute_rejects_unsupported_task_without_running_it():
    executor = FakeWorkerExecutor(allowed_task_types=frozenset({"analysis"}))
    task = _task(task_type="shell")
    result = _run(executor.execute(task))
    assert result.success is False
    assert "unsupported task type" in result.error
    assert executor.requests == (task,)


def test_execute_rejects_unsupported_capability():
    executor = FakeWorkerExecutor(capabilities=frozenset({"analysis"}))
    task = _task(capabilities=frozenset({"vision"}))
    result = _run(executor.execute(task))
    assert result.success is False
    assert "capability" in result.error


def test_execute_honours_scripted_failure_ids():
    task = _task()
    executor = FakeWorkerExecutor(fail_task_ids=frozenset({task.distributed_task_id}))
    result = _run(executor.execute(task))
    assert result.success is False
    assert result.error == "simulated worker failure"


def test_execute_fails_once_then_succeeds():
    task = _task()
    executor = FakeWorkerExecutor(fail_once_task_ids=frozenset({task.distributed_task_id}))
    first = _run(executor.execute(task))
    second = _run(executor.execute(task))
    assert first.success is False
    assert second.success is True


def test_execute_raises_scripted_error():
    executor = FakeWorkerExecutor(raise_error=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        _run(executor.execute(_task()))
