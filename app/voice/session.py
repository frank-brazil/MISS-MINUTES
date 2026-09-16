"""Voice session state machine.

Tracks a single live voice session: its lifecycle state, the current input
phase, accumulated metadata, and cancellation. The orchestrating service
drives transitions; the session itself knows nothing about providers.
"""

from enum import StrEnum
import time
from typing import Callable
from uuid import UUID, uuid4


class VoiceSessionState(StrEnum):
    """Lifecycle state of a voice session."""

    IDLE = "idle"
    LISTENING = "listening"
    CAPTURING = "capturing"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    STOPPED = "stopped"
    ERROR = "error"


class VoiceInputState(StrEnum):
    """Current microphone input phase within a session."""

    IDLE = "idle"
    WAITING_FOR_WAKE = "waiting_for_wake"
    LISTENING = "listening"
    UTTERANCE = "utterance"
    PROCESSING = "processing"


class VoiceSession:
    """Mutable metadata and cancellation for one voice session.

    ``mark_state`` rejects transitions after cancellation (except ``STOPPED``
    and ``ERROR``), so a cancelled session cannot silently resume.
    """

    def __init__(
        self,
        *,
        session_id: UUID | None = None,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self.session_id = session_id or uuid4()
        self._now_fn = now_fn or time.time
        self.state = VoiceSessionState.IDLE
        self.input_state = VoiceInputState.IDLE
        self.started_at = self._now_fn()
        self.updated_at = self.started_at
        self.language: str | None = None
        self.turn_count: int = 0
        self.cancelled = False
        self.last_error: str | None = None

    @property
    def is_cancelled(self) -> bool:
        return self.cancelled

    def mark_state(self, state: VoiceSessionState) -> None:
        if self.cancelled and state not in (
            VoiceSessionState.STOPPED,
            VoiceSessionState.ERROR,
        ):
            return
        self.state = state
        self.updated_at = self._now_fn()

    def mark_input(self, input_state: VoiceInputState) -> None:
        if self.cancelled:
            return
        self.input_state = input_state
        self.updated_at = self._now_fn()

    def begin_turn(self) -> None:
        if self.cancelled:
            return
        self.turn_count += 1
        self.input_state = VoiceInputState.PROCESSING
        self.updated_at = self._now_fn()

    def finish_turn(self) -> None:
        if self.cancelled:
            return
        self.updated_at = self._now_fn()

    def mark_error(self, error: str) -> None:
        self.last_error = error
        self.state = VoiceSessionState.ERROR
        self.updated_at = self._now_fn()

    def cancel(self) -> None:
        self.cancelled = True
        self.state = VoiceSessionState.STOPPED
        self.updated_at = self._now_fn()