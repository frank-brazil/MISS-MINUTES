import asyncio
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.solver.actions import ActionExecutor, ActionRequest, ActionResult
from app.solver.fakes import FakeActionExecutor


def _run(coro):
    return asyncio.run(coro)


def test_action_request_defaults() -> None:
    request = ActionRequest(description="apply the fix")
    assert isinstance(request.action_id, UUID)
    assert request.description == "apply the fix"
    assert request.expected_outcome is None
    assert request.iteration is None


def test_action_request_rejects_blank_description() -> None:
    with pytest.raises(ValidationError):
        ActionRequest(description="")
    with pytest.raises(ValidationError):
        ActionRequest(description="   ")


def test_action_result_factories() -> None:
    action_id = UUID(int=1)
    ok = ActionResult.ok(action_id=action_id, output="done")
    assert ok.success is True
    assert ok.output == "done"
    assert ok.error is None
    assert ok.observation_data == {}
    fail = ActionResult.fail(action_id=action_id, error="boom")
    assert fail.success is False
    assert fail.error == "boom"
    assert fail.output is None
    assert fail.observation_data == {}


def test_action_result_accepts_observation_data() -> None:
    action_id = UUID(int=2)
    result = ActionResult.ok(
        action_id=action_id,
        output="done",
        observation_data={"count": 3},
    )
    assert result.observation_data == {"count": 3}


def test_action_executor_is_abstract() -> None:
    with pytest.raises(TypeError):
        ActionExecutor()  # type: ignore[abstract]


def test_fake_action_executor_interface() -> None:
    executor = FakeActionExecutor()
    request = ActionRequest(description="do a thing", iteration=1)
    try:
        result = _run(executor.execute(request))
    except TypeError as exc:
        raise AssertionError(f"Fake is not async-callable: {exc}") from exc
    assert isinstance(result, ActionResult)
    assert result.success is True
    assert executor.name == "fake-action-executor"
    assert executor.description


def test_fake_action_executor_deterministic() -> None:
    executor = FakeActionExecutor(success_output="same output")
    request = ActionRequest(description="do a thing", iteration=1)
    first = _run(executor.execute(request))
    second = _run(executor.execute(request))
    assert first.success is True
    assert first.output == "same output"
    assert second.success is True
    assert second.output == "same output"


def test_fake_action_executor_records_requests() -> None:
    executor = FakeActionExecutor()
    first = ActionRequest(description="one", iteration=1)
    second = ActionRequest(description="two", iteration=1)
    _run(executor.execute(first))
    _run(executor.execute(second))
    assert executor.requests == (first, second)


def test_fake_action_executor_fail() -> None:
    executor = FakeActionExecutor(fail=True, fail_message="no")
    request = ActionRequest(description="do a thing", iteration=1)
    result = _run(executor.execute(request))
    assert result.success is False
    assert result.error == "no"


def test_fake_action_executor_fail_iterations() -> None:
    executor = FakeActionExecutor(fail_iterations=frozenset({1}))
    first = _run(executor.execute(ActionRequest(description="a", iteration=1)))
    second = _run(executor.execute(ActionRequest(description="a", iteration=2)))
    assert first.success is False
    assert second.success is True


def test_fake_action_executor_raise_error() -> None:
    executor = FakeActionExecutor(raise_error=RuntimeError("boom"))
    request = ActionRequest(description="do a thing", iteration=1)
    with pytest.raises(RuntimeError, match="boom"):
        _run(executor.execute(request))


def test_fake_action_executor_performs_no_real_effect() -> None:
    executor = FakeActionExecutor()
    request = ActionRequest(description="no side effects", iteration=1)
    result = _run(executor.execute(request))
    assert result is not None
    assert result.output is not None
    assert result.observation_data == {}
