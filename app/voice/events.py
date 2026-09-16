"""Structured voice events and the bounded voice event log.

Events describe *what happened*, never raw content: transcriptions and
responses are recorded as character counts. Event messages are redacted with
the shared security redaction helpers before being stored.
"""

import logging
import time
from collections import deque
from enum import StrEnum
from typing import Callable

from pydantic import BaseModel

from app.security.redaction import redact_string


class VoiceEventType(StrEnum):
    """Identifier for each kind of voice session event."""

    SESSION_STARTED = "session_started"
    SESSION_STOPPED = "session_stopped"
    SESSION_CANCELLED = "session_cancelled"
    SESSION_IDLE_TIMEOUT = "session_idle_timeout"
    SESSION_ERROR = "session_error"
    WAKE_WORD_DETECTED = "wake_word_detected"
    LISTENING_STARTED = "listening_started"
    SPEECH_STARTED = "speech_started"
    SPEECH_ENDED = "speech_ended"
    TRANSCRIPTION_STARTED = "transcription_started"
    TRANSCRIPTION_COMPLETED = "transcription_completed"
    AI_STARTED = "ai_started"
    AI_COMPLETED = "ai_completed"
    TURN_COMPLETED = "turn_completed"
    TURN_ERROR = "turn_error"
    SPEAKING_STARTED = "speaking_started"
    SPEAKING_STOPPED = "speaking_stopped"
    SPEAKING_INTERRUPTED = "speaking_interrupted"


class VoiceEvent(BaseModel):
    """One structured voice session event."""

    sequence: int
    event_type: VoiceEventType
    timestamp: float
    session_id: str | None = None
    turn_id: int | None = None
    language: str | None = None
    success: bool | None = None
    interrupted: bool | None = None
    message: str | None = None


class VoiceEventLog:
    """Bounded, redacted, sequential record of voice events."""

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
        self._events: deque[VoiceEvent] = deque(maxlen=max_events)
        self._next_sequence = 1
        self._logger = logging.getLogger(__name__)

    @property
    def now(self) -> float:
        return self._now_fn()

    def record(
        self,
        event_type: VoiceEventType,
        *,
        session_id: str | None = None,
        turn_id: int | None = None,
        language: str | None = None,
        success: bool | None = None,
        interrupted: bool | None = None,
        message: str | None = None,
        now: float | None = None,
    ) -> VoiceEvent:
        timestamp = self._now_fn() if now is None else now
        safe_message = message
        if safe_message is not None and self._redact_messages:
            safe_message = redact_string(safe_message)
        event = VoiceEvent(
            sequence=self._next_sequence,
            event_type=event_type,
            timestamp=timestamp,
            session_id=session_id,
            turn_id=turn_id,
            language=language,
            success=success,
            interrupted=interrupted,
            message=safe_message,
        )
        self._next_sequence += 1
        self._events.append(event)
        self._logger.info(
            "Voice event %d: type=%s success=%s",
            event.sequence,
            event.event_type.value,
            event.success,
        )
        return event

    def events(self) -> tuple[VoiceEvent, ...]:
        return tuple(self._events)

    def events_of_type(self, event_type: VoiceEventType) -> tuple[VoiceEvent, ...]:
        return tuple(event for event in self._events if event.event_type is event_type)

    def count(self) -> int:
        return len(self._events)

    def clear(self) -> None:
        self._events.clear()
        self._next_sequence = 1
