"""Avatar events: types, ordering, bounds and redaction."""

from app.avatar.events import AvatarEventLog, AvatarEventType
from app.avatar.models import AvatarState


def test_full_event_type_set():
    types = {t.value for t in AvatarEventType}
    assert types == {
        "avatar_started",
        "avatar_stopped",
        "state_changed",
        "expression_changed",
        "blink",
        "look_changed",
        "animation_started",
        "animation_completed",
        "eye_target_changed",
        "blink_started",
        "blink_finished",
        "gesture_started",
        "gesture_finished",
        "walking_started",
        "walking_stopped",
        "lipsync_started",
        "lipsync_finished",
        "animation_interrupted",
    }


def test_record_orders_and_sequences():
    log = AvatarEventLog(now_fn=lambda: 0.0)
    first = log.record(AvatarEventType.AVATAR_STARTED, state=AvatarState.IDLE)
    second = log.record(AvatarEventType.STATE_CHANGED, state=AvatarState.LISTENING)
    assert first.sequence == 1
    assert second.sequence == 2
    assert second.timestamp >= first.timestamp
    assert log.count() == 2


def test_events_of_type():
    log = AvatarEventLog(now_fn=lambda: 42.0)
    log.record(AvatarEventType.BLINK, state=AvatarState.IDLE)
    log.record(AvatarEventType.LOOK_CHANGED, state=AvatarState.IDLE)
    log.record(AvatarEventType.BLINK, state=AvatarState.IDLE)
    assert len(log.events_of_type(AvatarEventType.BLINK)) == 2
    assert len(log.events_of_type(AvatarEventType.LOOK_CHANGED)) == 1


def test_record_metadata_fields():
    log = AvatarEventLog(now_fn=lambda: 1.5)
    event = log.record(
        AvatarEventType.STATE_CHANGED,
        state=AvatarState.THINKING,
        previous_state=AvatarState.LISTENING,
        expression="thinking",
        message="signal=thinking",
    )
    assert event.state is AvatarState.THINKING
    assert event.previous_state is AvatarState.LISTENING
    assert event.expression == "thinking"
    assert event.timestamp == 1.5


def test_log_is_bounded():
    log = AvatarEventLog(max_events=3, now_fn=lambda: 0.0)
    for _ in range(5):
        log.record(AvatarEventType.BLINK)
    assert log.count() == 3
    events = log.events()
    assert events[0].sequence == 3
    assert events[-1].sequence == 5


def test_message_redaction():
    log = AvatarEventLog()
    event = log.record(AvatarEventType.LOOK_CHANGED, message="password=hunter2")
    assert event.message == "password=[REDACTED]"
    plain = log.record(AvatarEventType.BLINK, message="all good")
    assert plain.message == "all good"


def test_clear_resets_sequence():
    log = AvatarEventLog(now_fn=lambda: 0.0)
    log.record(AvatarEventType.AVATAR_STARTED)
    log.clear()
    assert log.count() == 0
    assert log.record(AvatarEventType.AVATAR_STARTED).sequence == 1


def test_max_events_validation():
    try:
        AvatarEventLog(max_events=0)
        assert False, "expected ValueError"
    except ValueError:
        pass