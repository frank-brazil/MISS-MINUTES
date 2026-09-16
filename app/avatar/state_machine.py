"""Avatar state machine.

Typed transitions between character states. Invalid transitions are handled
safely (``try_transition`` returns ``False``; ``transition`` raises
``AvatarTransitionError``). Previous state is tracked; the machine keeps no
hidden global state.
"""

from collections.abc import Mapping

from app.avatar.models import AvatarState


class AvatarTransitionError(RuntimeError):
    """Raised when a transition is not allowed."""


TRANSITIONS: Mapping[AvatarState, frozenset[AvatarState]] = {
    AvatarState.IDLE: frozenset(
        {
            AvatarState.LISTENING,
            AvatarState.THINKING,
            AvatarState.WORKING,
            AvatarState.SPEAKING,
            AvatarState.HAPPY,
            AvatarState.CONCERNED,
            AvatarState.WARNING,
            AvatarState.SUCCESS,
            AvatarState.ERROR,
            AvatarState.SLEEPING,
            AvatarState.HIDDEN,
            AvatarState.WALKING,
            AvatarState.EXPLAINING,
            AvatarState.INTERRUPTED,
        }
    ),
    AvatarState.LISTENING: frozenset(
        {
            AvatarState.THINKING,
            AvatarState.WORKING,
            AvatarState.SPEAKING,
            AvatarState.HAPPY,
            AvatarState.SUCCESS,
            AvatarState.ERROR,
            AvatarState.IDLE,
            AvatarState.SLEEPING,
            AvatarState.HIDDEN,
        }
    ),
    AvatarState.THINKING: frozenset(
        {
            AvatarState.WORKING,
            AvatarState.SPEAKING,
            AvatarState.CONCERNED,
            AvatarState.ERROR,
            AvatarState.SUCCESS,
            AvatarState.IDLE,
            AvatarState.HIDDEN,
        }
    ),
    AvatarState.WORKING: frozenset(
        {
            AvatarState.SPEAKING,
            AvatarState.SUCCESS,
            AvatarState.ERROR,
            AvatarState.LISTENING,
            AvatarState.IDLE,
            AvatarState.HIDDEN,
            AvatarState.WARNING,
        }
    ),
    AvatarState.SPEAKING: frozenset(
        {
            AvatarState.IDLE,
            AvatarState.LISTENING,
            AvatarState.SUCCESS,
            AvatarState.ERROR,
            AvatarState.HAPPY,
            AvatarState.HIDDEN,
            AvatarState.WARNING,
            AvatarState.INTERRUPTED,
        }
    ),
    AvatarState.HAPPY: frozenset(
        {AvatarState.IDLE, AvatarState.SPEAKING, AvatarState.SUCCESS, AvatarState.ERROR, AvatarState.HIDDEN}
    ),
    AvatarState.CONCERNED: frozenset(
        {AvatarState.ERROR, AvatarState.WARNING, AvatarState.IDLE, AvatarState.SPEAKING, AvatarState.HIDDEN}
    ),
    AvatarState.WARNING: frozenset(
        {AvatarState.ERROR, AvatarState.CONCERNED, AvatarState.IDLE, AvatarState.HIDDEN}
    ),
    AvatarState.SUCCESS: frozenset({AvatarState.IDLE, AvatarState.SPEAKING, AvatarState.HIDDEN}),
    AvatarState.ERROR: frozenset({AvatarState.IDLE, AvatarState.CONCERNED, AvatarState.HIDDEN}),
    AvatarState.SLEEPING: frozenset({AvatarState.IDLE, AvatarState.HIDDEN}),
    AvatarState.HIDDEN: frozenset({AvatarState.IDLE}),
    AvatarState.WALKING: frozenset(
        {
            AvatarState.IDLE,
            AvatarState.LISTENING,
            AvatarState.THINKING,
            AvatarState.SPEAKING,
            AvatarState.SUCCESS,
            AvatarState.ERROR,
            AvatarState.WARNING,
            AvatarState.HIDDEN,
            AvatarState.SLEEPING,
            AvatarState.EXPLAINING,
            AvatarState.INTERRUPTED,
        }
    ),
    AvatarState.EXPLAINING: frozenset(
        {
            AvatarState.IDLE,
            AvatarState.LISTENING,
            AvatarState.THINKING,
            AvatarState.WORKING,
            AvatarState.SPEAKING,
            AvatarState.SUCCESS,
            AvatarState.WARNING,
            AvatarState.ERROR,
            AvatarState.HIDDEN,
            AvatarState.WALKING,
            AvatarState.INTERRUPTED,
        }
    ),
    AvatarState.INTERRUPTED: frozenset(
        {
            AvatarState.IDLE,
            AvatarState.LISTENING,
            AvatarState.THINKING,
            AvatarState.WORKING,
            AvatarState.SPEAKING,
            AvatarState.CONCERNED,
            AvatarState.HIDDEN,
        }
    ),
}


class AvatarStateMachine:
    """Deterministic state machine with previous-state tracking."""

    def __init__(self, initial: AvatarState = AvatarState.IDLE) -> None:
        self._state = initial
        self._previous: AvatarState | None = None

    @property
    def state(self) -> AvatarState:
        return self._state

    @property
    def previous(self) -> AvatarState | None:
        return self._previous

    def can_transition(self, target: AvatarState) -> bool:
        return target in TRANSITIONS.get(self._state, frozenset())

    def try_transition(self, target: AvatarState) -> bool:
        """Apply the transition when allowed; otherwise return ``False``."""
        if not self.can_transition(target):
            return False
        self._previous = self._state
        self._state = target
        return True

    def transition(self, target: AvatarState) -> AvatarState:
        """Apply the transition or raise :class:`AvatarTransitionError`."""
        if not self.can_transition(target):
            raise AvatarTransitionError(
                f"cannot transition from {self._state.value} to {target.value}"
            )
        self._previous = self._state
        self._state = target
        return self._state

    def reset(self, initial: AvatarState = AvatarState.IDLE) -> None:
        self._previous = None
        self._state = initial
