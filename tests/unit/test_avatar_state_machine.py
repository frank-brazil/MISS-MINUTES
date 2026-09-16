"""Avatar state machine: valid/invalid transitions and history."""

import pytest

from app.avatar.models import AvatarState
from app.avatar.state_machine import AvatarStateMachine, AvatarTransitionError


def test_defaults_to_idle():
    machine = AvatarStateMachine()
    assert machine.state is AvatarState.IDLE
    assert machine.previous is None


def test_required_happy_path_chain():
    machine = AvatarStateMachine()
    chain = (
        (AvatarState.LISTENING, AvatarState.LISTENING),
        (AvatarState.THINKING, AvatarState.THINKING),
        (AvatarState.WORKING, AvatarState.WORKING),
        (AvatarState.SPEAKING, AvatarState.SPEAKING),
        (AvatarState.SUCCESS, AvatarState.SUCCESS),
        (AvatarState.IDLE, AvatarState.IDLE),
    )
    for target, expected in chain:
        assert machine.transition(target) is expected
        assert machine.state is expected


def test_thinking_concerned_error_path():
    machine = AvatarStateMachine(initial=AvatarState.THINKING)
    machine.transition(AvatarState.CONCERNED)
    assert machine.state is AvatarState.CONCERNED
    machine.transition(AvatarState.ERROR)
    assert machine.state is AvatarState.ERROR
    machine.transition(AvatarState.IDLE)
    assert machine.state is AvatarState.IDLE


def test_transition_raises_on_invalid():
    machine = AvatarStateMachine(initial=AvatarState.HIDDEN)
    with pytest.raises(AvatarTransitionError):
        machine.transition(AvatarState.LISTENING)
    assert machine.state is AvatarState.HIDDEN


def test_try_transition_returns_false_safely():
    machine = AvatarStateMachine()
    assert machine.try_transition(AvatarState.HIDDEN) is True
    assert machine.state is AvatarState.HIDDEN
    assert machine.try_transition(AvatarState.ERROR) is False
    assert machine.state is AvatarState.HIDDEN
    assert machine.try_transition(AvatarState.IDLE) is True


def test_can_transition():
    machine = AvatarStateMachine()
    assert machine.can_transition(AvatarState.LISTENING)
    assert machine.can_transition(AvatarState.HIDDEN)
    assert machine.can_transition(AvatarState.ERROR)  # idle may react to ambient errors
    machine.transition(AvatarState.SUCCESS)
    assert not machine.can_transition(AvatarState.ERROR)  # success is a safe-rest state


def test_previous_state_tracking():
    machine = AvatarStateMachine()
    machine.transition(AvatarState.LISTENING)
    assert machine.previous is AvatarState.IDLE
    machine.transition(AvatarState.THINKING)
    assert machine.previous is AvatarState.LISTENING


def test_reset_clears_history():
    machine = AvatarStateMachine()
    machine.transition(AvatarState.LISTENING)
    machine.reset()
    assert machine.state is AvatarState.IDLE
    assert machine.previous is None


def test_hidden_only_returns_to_idle():
    machine = AvatarStateMachine(initial=AvatarState.HIDDEN)
    assert not machine.can_transition(AvatarState.LISTENING)
    assert machine.can_transition(AvatarState.IDLE)


def test_sleeping_wakes_to_idle_only():
    machine = AvatarStateMachine(initial=AvatarState.SLEEPING)
    assert not machine.can_transition(AvatarState.WORKING)
    assert machine.can_transition(AvatarState.IDLE)