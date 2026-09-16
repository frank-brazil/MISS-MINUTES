import asyncio
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.solver.fakes import FakeObservationProvider
from app.solver.observation import (
    ObservationProvider,
    ObservationRequest,
    ObservationResult,
)


def _run(coro):
    return asyncio.run(coro)


def test_observation_request_defaults() -> None:
    request = ObservationRequest(
        description="Observe the outcome of the action."
    )
    assert isinstance(request.observation_id, UUID)
    assert request.action_ref is None
    assert request.expected_outcome is None


def test_observation_request_rejects_blank_description() -> None:
    with pytest.raises(ValidationError):
        ObservationRequest(description="")


def test_observation_result_factories() -> None:
    observation_id = UUID(int=5)
    ok = ObservationResult.ok(
        observation_id=observation_id,
        observations=["everything looks fine"],
        action_succeeded=True,
    )
    assert ok.success is True
    assert ok.observations == ["everything looks fine"]
    assert ok.action_succeeded is True
    fail = ObservationResult.fail(observation_id=observation_id, error="boom")
    assert fail.success is False
    assert fail.error == "boom"
    assert fail.observations == []


def test_observation_provider_is_abstract() -> None:
    with pytest.raises(TypeError):
        ObservationProvider()  # type: ignore[abstract]


def test_fake_observation_provider_interface() -> None:
    provider = FakeObservationProvider()
    request = ObservationRequest(description="observe")
    result = _run(provider.observe(request))
    assert isinstance(result, ObservationResult)
    assert result.success is True
    assert provider.name == "fake-observation-provider"


def test_fake_observation_provider_returns_configured_observations() -> None:
    provider = FakeObservationProvider(
        observations=["first", "second"], action_succeeded=False
    )
    request = ObservationRequest(description="observe")
    result = _run(provider.observe(request))
    assert result.success is True
    assert result.observations == ["first", "second"]
    assert result.action_succeeded is False


def test_fake_observation_provider_records_requests() -> None:
    provider = FakeObservationProvider()
    first = ObservationRequest(description="one")
    second = ObservationRequest(description="two")
    _run(provider.observe(first))
    _run(provider.observe(second))
    assert provider.requests == (first, second)


def test_fake_observation_provider_fail() -> None:
    provider = FakeObservationProvider(
        fail=True,
        fail_message="no signal",
        observations=["partial"],
    )
    request = ObservationRequest(description="observe")
    result = _run(provider.observe(request))
    assert result.success is False
    assert result.error == "no signal"
    assert result.observations == ["partial"]


def test_fake_observation_provider_raise_error() -> None:
    provider = FakeObservationProvider(raise_error=RuntimeError("boom"))
    request = ObservationRequest(description="observe")
    with pytest.raises(RuntimeError, match="boom"):
        _run(provider.observe(request))


def test_fake_observation_provider_does_not_touch_screens() -> None:
    provider = FakeObservationProvider()
    _run(
        provider.observe(
            ObservationRequest(description="never reads the real screen")
        )
    )
    assert len(provider.requests) == 1