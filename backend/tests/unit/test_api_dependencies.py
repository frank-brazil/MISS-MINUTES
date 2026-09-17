"""Unit tests for app.api.dependencies — get_orchestrator dependency."""

import pytest
from app.api.dependencies import get_orchestrator
from app.core.orchestrator import Orchestrator


class FakeState:
    def __init__(self, orchestrator: Orchestrator | None = None) -> None:
        self.orchestrator = orchestrator


class FakeApp:
    def __init__(self, orchestrator: Orchestrator | None = None) -> None:
        self.state = FakeState(orchestrator)


class FakeRequest:
    def __init__(self, orchestrator: Orchestrator | None = None) -> None:
        self.app = FakeApp(orchestrator)


def test_get_orchestrator_extracts_from_app_state() -> None:
    orch = Orchestrator()
    request = FakeRequest(orchestrator=orch)
    result = get_orchestrator(request)
    assert result is orch


def test_get_orchestrator_raises_when_missing() -> None:
    request = FakeRequest(orchestrator=None)
    with pytest.raises(RuntimeError, match="not available"):
        get_orchestrator(request)


def test_get_orchestrator_returns_correct_instance() -> None:
    orch1 = Orchestrator()
    orch2 = Orchestrator()
    request = FakeRequest(orchestrator=orch2)
    result = get_orchestrator(request)
    assert result is orch2
    assert result is not orch1
