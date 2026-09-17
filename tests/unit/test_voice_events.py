from app.voice.events import VoiceEventLog, VoiceEventType

REDACTABLE_MESSAGE = "token=abc123 password=hunter2"


class _Clock:
    def __init__(self, start: float = 1.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value


def test_event_log_records_sequential_events() -> None:
    clock = _Clock()
    log = VoiceEventLog(now_fn=clock)
    first = log.record(
        VoiceEventType.SESSION_STARTED,
        session_id="s1",
        success=True,
        message="hello",
    )
    second = log.record(VoiceEventType.WAKE_WORD_DETECTED, session_id="s1")
    assert first.sequence == 1
    assert second.sequence == 2
    assert first.timestamp == 1.0
    assert log.count() == 2
    assert log.events()[0] is first


def test_event_log_redacts_secret_like_messages_by_default() -> None:
    log = VoiceEventLog()
    event = log.record(
        VoiceEventType.SESSION_ERROR,
        message=REDACTABLE_MESSAGE,
        success=False,
    )
    assert "token=[REDACTED]" in (event.message or "")
    assert "password=[REDACTED]" in (event.message or "")
    assert "hunter2" not in (event.message or "")


def test_event_log_can_disable_redaction() -> None:
    log = VoiceEventLog(redact_messages=False)
    event = log.record(VoiceEventType.SESSION_ERROR, message=REDACTABLE_MESSAGE)
    assert event.message == REDACTABLE_MESSAGE


def test_event_log_respects_bounded_size() -> None:
    log = VoiceEventLog(max_events=3)
    for _ in range(5):
        log.record(VoiceEventType.TURN_COMPLETED, success=True)
    assert log.count() == 3
    assert log.events()[0].sequence == 3
    assert log.events()[-1].sequence == 5


def test_event_log_filters_by_type() -> None:
    log = VoiceEventLog()
    log.record(VoiceEventType.TURN_COMPLETED, success=True)
    log.record(VoiceEventType.SPEAKING_STARTED, success=True)
    log.record(VoiceEventType.TURN_COMPLETED, success=True)
    turns = log.events_of_type(VoiceEventType.TURN_COMPLETED)
    assert len(turns) == 2
    speaking = log.events_of_type(VoiceEventType.SPEAKING_STARTED)
    assert len(speaking) == 1


def test_event_log_clear_resets_sequence() -> None:
    log = VoiceEventLog()
    log.record(VoiceEventType.SESSION_STARTED)
    log.clear()
    assert log.count() == 0
    event = log.record(VoiceEventType.SESSION_STOPPED)
    assert event.sequence == 1


def test_event_log_carries_turn_and_interrupted_metadata() -> None:
    log = VoiceEventLog()
    event = log.record(
        VoiceEventType.TURN_COMPLETED,
        session_id="s1",
        turn_id=7,
        language="hindi",
        success=True,
        interrupted=True,
    )
    assert event.turn_id == 7
    assert event.language == "hindi"
    assert event.interrupted is True
    assert event.success is True
