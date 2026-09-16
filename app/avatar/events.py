"""Structured avatar events and a bounded log.

Events describe *what happened* in the avatar layer with safe, redacted
metadata only; they never carry raw transcription or AI content.
"""

import logging
import time
from collections import deque
from enum import StrEnum
from typing import Callable

from pydantic import BaseModel

from app.avatar.models import AvatarState
from app.security.redaction import redact_string


class AvatarEventType(StrEnum):
    """Identifier for each kind of avatar event."""

    AVATAR_STARTED = "avatar_started"
    AVATAR_STOPPED = "avatar_stopped"
    STATE_CHANGED = "state_changed"
    EXPRESSION_CHANGED = "expression_changed"
    BLINK = "blink"
    LOOK_CHANGED = "look_changed"
    ANIMATION_STARTED = "animation_started"
    ANIMATION_COMPLETED = "animation_completed"
    EYE_TARGET_CHANGED = "eye_target_changed"
    BLINK_STARTED = "blink_started"
    BLINK_FINISHED = "blink_finished"
    GESTURE_STARTED = "gesture_started"
    GESTURE_FINISHED = "gesture_finished"
    WALKING_STARTED = "walking_started"
    WALKING_STOPPED = "walking_stopped"
    LIPSYNC_STARTED = "lipsync_started"
    LIPSYNC_FINISHED = "lipsync_finished"
    ANIMATION_INTERRUPTED = "animation_interrupted"


class AvatarEvent(BaseModel):
    """One structured avatar event."""

    sequence: int
    event_type: AvatarEventType
    timestamp: float
    state: AvatarState | None = None
    previous_state: AvatarState | None = None
    expression: str | None = None
    animation: str | None = None
    gesture: str | None = None
    walking: str | None = None
    accuracy: str | None = None
    message: str | None = None


class AvatarEventLog:
    """Bounded, redacted, sequential record of avatar events."""

    def __init__(
        self,
        *,
        max_events: int = 500,
        now_fn: Callable[[], float] | None = None,
        redact_messages: bool = True,
    ) -> None:
        if max_events < 1:
            raise ValueError("max_events must be positive")
        self._max_events = max_events
        self._now_fn = now_fn or time.time
        self._redact_messages = redact_messages
        self._events: deque[AvatarEvent] = deque(maxlen=max_events)
        self._next_sequence = 1
        self._logger = logging.getLogger(__name__)

    @property
    def now(self) -> float:
        return self._now_fn()

    def record(
        self,
        event_type: AvatarEventType,
        *,
        state: AvatarState | None = None,
        previous_state: AvatarState | None = None,
        expression: str | None = None,
        animation: str | None = None,
        gesture: str | None = None,
        walking: str | None = None,
        accuracy: str | None = None,
        message: str | None = None,
        now: float | None = None,
    ) -> AvatarEvent:
        timestamp = self._now_fn() if now is None else now
        safe_message = message
        if safe_message is not None and self._redact_messages:
            safe_message = redact_string(safe_message)
        event = AvatarEvent(
            sequence=self._next_sequence,
            event_type=event_type,
            timestamp=timestamp,
            state=state,
            previous_state=previous_state,
            expression=expression,
            animation=animation,
            gesture=gesture,
            walking=walking,
            accuracy=accuracy,
            message=safe_message,
        )
        self._next_sequence += 1
        self._events.append(event)
        self._logger.info(
            "Avatar event %d: type=%s state=%s", event.sequence, event.event_type.value, event.state
        )
        return event

    def events(self) -> tuple[AvatarEvent, ...]:
        return tuple(self._events)

    def events_of_type(self, event_type: AvatarEventType) -> tuple[AvatarEvent, ...]:
        return tuple(event for event in self._events if event.event_type is event_type)

    def count(self) -> int:
        return len(self._events)

    def clear(self) -> None:
        self._events.clear()
        self._next_sequence = 1
