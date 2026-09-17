import time
from uuid import uuid4

from app.voice.session import (
    VoiceInputState,
    VoiceSession,
    VoiceSessionState,
)


class _Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


def _session(clock: _Clock | None = None) -> VoiceSession:
    return VoiceSession(now_fn=clock or time.time)


def test_session_initial_state() -> None:
    session = _session()
    assert session.state is VoiceSessionState.IDLE
    assert session.input_state is VoiceInputState.IDLE
    assert session.turn_count == 0
    assert session.cancelled is False
    assert session.is_cancelled is False
    assert session.language is None


def test_session_transitions() -> None:
    session = _session()
    session.mark_state(VoiceSessionState.LISTENING)
    assert session.state is VoiceSessionState.LISTENING
    session.mark_input(VoiceInputState.WAITING_FOR_WAKE)
    assert session.input_state is VoiceInputState.WAITING_FOR_WAKE
    session.mark_state(VoiceSessionState.CAPTURING)
    assert session.state is VoiceSessionState.CAPTURING


def test_session_begin_finish_turn() -> None:
    session = _session()
    session.begin_turn()
    assert session.turn_count == 1
    assert session.input_state is VoiceInputState.PROCESSING
    session.finish_turn()
    assert session.turn_count == 1


def test_session_cancel_marks_stopped() -> None:
    session = _session()
    session.mark_state(VoiceSessionState.SPEAKING)
    session.cancel()
    assert session.cancelled is True
    assert session.is_cancelled is True
    assert session.state is VoiceSessionState.STOPPED


def test_session_cancelled_ignores_non_terminal_transitions() -> None:
    session = _session()
    session.cancel()
    session.mark_state(VoiceSessionState.LISTENING)
    assert session.state is VoiceSessionState.STOPPED
    session.mark_input(VoiceInputState.UTTERANCE)
    assert session.input_state is VoiceInputState.IDLE


def test_session_cancelled_allows_stopped_and_error() -> None:
    session = _session()
    session.cancel()
    session.mark_state(VoiceSessionState.ERROR)
    assert session.state is VoiceSessionState.ERROR


def test_session_error_records_last_error() -> None:
    session = _session()
    session.mark_error("microphone unavailable")
    assert session.state is VoiceSessionState.ERROR
    assert session.last_error == "microphone unavailable"


def test_session_tracks_updated_time_with_injected_clock() -> None:
    clock = _Clock()
    session = _session(clock)
    started = session.started_at
    assert started == 100.0
    clock.value = 150.0
    session.mark_state(VoiceSessionState.LISTENING)
    assert session.updated_at == 150.0


def test_session_assigns_unique_ids() -> None:
    assert _session().session_id != _session().session_id
    fixed = uuid4()
    assert _session().session_id != fixed
    session = VoiceSession(session_id=fixed)
    assert session.session_id == fixed
