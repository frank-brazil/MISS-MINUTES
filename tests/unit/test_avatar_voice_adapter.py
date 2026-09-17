"""Voice connection boundary: translates voice events into avatar signals."""

from app.avatar.controller import AvatarController, AvatarSignal
from app.avatar.models import AvatarState
from app.avatar.renderer import FakeAvatarRenderer
from app.avatar.voice_adapter import (
    SESSION_STATE_MAP,
    VOICE_EVENT_SIGNAL_MAP,
    VoiceAvatarAdapter,
)
from app.voice.events import VoiceEvent, VoiceEventLog, VoiceEventType
from app.voice.session import VoiceSessionState


def _event(event_type: VoiceEventType, sequence: int = 1) -> VoiceEvent:
    return VoiceEvent(sequence=sequence, event_type=event_type, timestamp=0.0)


def _adapter() -> tuple[VoiceAvatarAdapter, AvatarController]:
    controller = AvatarController(FakeAvatarRenderer(), now_fn=lambda: 0.5)
    controller.start()
    return VoiceAvatarAdapter(controller), controller


def test_event_translation_table():
    expected = {
        VoiceEventType.SESSION_STARTED: AvatarSignal.IDLE,
        VoiceEventType.WAKE_WORD_DETECTED: AvatarSignal.LISTENING,
        VoiceEventType.LISTENING_STARTED: AvatarSignal.LISTENING,
        VoiceEventType.SPEECH_STARTED: AvatarSignal.LISTENING,
        VoiceEventType.TRANSCRIPTION_STARTED: AvatarSignal.THINKING,
        VoiceEventType.AI_STARTED: AvatarSignal.THINKING,
        VoiceEventType.TURN_COMPLETED: AvatarSignal.SUCCESS,
        VoiceEventType.TURN_ERROR: AvatarSignal.ERROR,
        VoiceEventType.SPEAKING_STARTED: AvatarSignal.SPEAKING,
        VoiceEventType.SPEAKING_INTERRUPTED: AvatarSignal.INTERRUPTED,
        VoiceEventType.SPEAKING_STOPPED: AvatarSignal.IDLE,
        VoiceEventType.SESSION_STOPPED: AvatarSignal.IDLE,
        VoiceEventType.SESSION_IDLE_TIMEOUT: AvatarSignal.IDLE,
        VoiceEventType.SESSION_CANCELLED: AvatarSignal.HIDE,
        VoiceEventType.SESSION_ERROR: AvatarSignal.ERROR,
    }
    assert dict(VOICE_EVENT_SIGNAL_MAP) == expected


def test_unmapped_events_translate_to_none():
    adapter, _ = _adapter()
    for event_type in (
        VoiceEventType.TRANSCRIPTION_COMPLETED,
        VoiceEventType.AI_COMPLETED,
        VoiceEventType.SPEECH_ENDED,
        VoiceEventType.SPEAKING_INTERRUPTED,  # mapped, just a sanity check
    ):
        if event_type in VOICE_EVENT_SIGNAL_MAP:
            assert adapter.translate(_event(event_type)) is not None
        else:
            assert adapter.translate(_event(event_type)) is None


def test_translate_returns_signal():
    adapter, _ = _adapter()
    assert adapter.translate(_event(VoiceEventType.LISTENING_STARTED)) is AvatarSignal.LISTENING
    assert adapter.translate(_event(VoiceEventType.SPEAKING_STARTED)) is AvatarSignal.SPEAKING


def test_apply_updates_controller():
    adapter, controller = _adapter()
    assert adapter.apply(_event(VoiceEventType.LISTENING_STARTED)) is True
    assert controller.state is AvatarState.LISTENING
    assert adapter.apply(_event(VoiceEventType.AI_STARTED)) is True
    assert controller.state is AvatarState.THINKING
    assert adapter.apply(_event(VoiceEventType.SPEAKING_STARTED)) is True
    assert controller.state is AvatarState.SPEAKING
    assert adapter.apply(_event(VoiceEventType.SPEAKING_STOPPED)) is True
    assert controller.state is AvatarState.IDLE


def test_apply_ignores_unmapped():
    adapter, controller = _adapter()
    assert adapter.apply(_event(VoiceEventType.TRANSCRIPTION_COMPLETED)) is False
    assert controller.state is AvatarState.IDLE


def test_apply_cancel_hides_character():
    adapter, controller = _adapter()
    adapter.apply(_event(VoiceEventType.LISTENING_STARTED))
    assert adapter.apply(_event(VoiceEventType.SESSION_CANCELLED)) is True
    assert controller.state is AvatarState.HIDDEN


def test_apply_error_via_turn_error():
    adapter, controller = _adapter()
    adapter.apply(_event(VoiceEventType.LISTENING_STARTED))
    assert adapter.apply(_event(VoiceEventType.TURN_ERROR)) is True
    assert controller.state is AvatarState.ERROR


def test_session_state_mapping_covers_all_states():
    assert set(SESSION_STATE_MAP) == set(VoiceSessionState)
    assert SESSION_STATE_MAP[VoiceSessionState.LISTENING] is AvatarState.LISTENING
    assert SESSION_STATE_MAP[VoiceSessionState.CAPTURING] is AvatarState.LISTENING
    assert SESSION_STATE_MAP[VoiceSessionState.TRANSCRIBING] is AvatarState.THINKING
    assert SESSION_STATE_MAP[VoiceSessionState.THINKING] is AvatarState.THINKING
    assert SESSION_STATE_MAP[VoiceSessionState.SPEAKING] is AvatarState.SPEAKING
    assert SESSION_STATE_MAP[VoiceSessionState.INTERRUPTED] is AvatarState.INTERRUPTED
    assert SESSION_STATE_MAP[VoiceSessionState.STOPPED] is AvatarState.IDLE
    assert SESSION_STATE_MAP[VoiceSessionState.ERROR] is AvatarState.ERROR


def test_translate_session_state():
    adapter, _ = _adapter()
    assert adapter.translate_session_state(VoiceSessionState.SPEAKING) is AvatarState.SPEAKING


def test_replay_from_event_log():
    adapter, controller = _adapter()
    log = VoiceEventLog(now_fn=lambda: 0.0)
    log.record(VoiceEventType.LISTENING_STARTED)
    log.record(VoiceEventType.AI_STARTED)
    log.record(VoiceEventType.SPEAKING_STARTED)
    log.record(VoiceEventType.SPEAKING_STOPPED)
    applied = adapter.replay(log)
    assert applied == 4
    assert controller.state is AvatarState.IDLE


def test_replay_does_not_mutate_voice_log():
    adapter, _ = _adapter()
    log = VoiceEventLog(now_fn=lambda: 0.0)
    log.record(VoiceEventType.LISTENING_STARTED)
    expected = list(log.events())
    adapter.replay(log)
    assert list(log.events()) == expected
    assert log.count() == 1
