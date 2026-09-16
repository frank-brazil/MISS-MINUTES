"""Voice connection boundary.

``VoiceAvatarAdapter`` translates existing voice-session events into avatar
signals so the character *follows* the conversation (listens, thinks, works,
speaks, celebrates, reacts). It never performs lip-sync (CHUNK 33) and never
modifies the voice pipeline: this is a read-only mapping over the already
published ``VoiceEvent``/``VoiceSessionState`` types.
"""

from typing import Mapping

from app.avatar.controller import AvatarController, AvatarSignal
from app.avatar.models import AvatarState as _S
from app.voice.events import VoiceEvent, VoiceEventType
from app.voice.session import VoiceSessionState


VOICE_EVENT_SIGNAL_MAP: Mapping[VoiceEventType, AvatarSignal] = {
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


SESSION_STATE_MAP: Mapping[VoiceSessionState, _S] = {
    VoiceSessionState.IDLE: _S.IDLE,
    VoiceSessionState.LISTENING: _S.LISTENING,
    VoiceSessionState.CAPTURING: _S.LISTENING,
    VoiceSessionState.TRANSCRIBING: _S.THINKING,
    VoiceSessionState.THINKING: _S.THINKING,
    VoiceSessionState.SPEAKING: _S.SPEAKING,
    VoiceSessionState.INTERRUPTED: _S.INTERRUPTED,
    VoiceSessionState.STOPPED: _S.IDLE,
    VoiceSessionState.ERROR: _S.ERROR,
}


class VoiceAvatarAdapter:
    """One-way mapping from the voice layer to the avatar character."""

    def __init__(self, controller: AvatarController) -> None:
        self._controller = controller

    @property
    def controller(self) -> AvatarController:
        return self._controller

    def translate(self, event: VoiceEvent) -> AvatarSignal | None:
        """Map a voice event to a high-level avatar signal (or ``None``)."""
        return VOICE_EVENT_SIGNAL_MAP.get(event.event_type)

    def apply(self, event: VoiceEvent) -> bool:
        """Translate and apply a voice event to the controller."""
        signal = self.translate(event)
        if signal is None:
            return False
        return self._controller.handle(signal)

    def translate_session_state(self, state: VoiceSessionState) -> _S:
        if state not in SESSION_STATE_MAP:
            return _S.IDLE
        return SESSION_STATE_MAP[state]

    def replay(self, events: "object") -> int:
        """Apply a collection of ``VoiceEvent`` records in order.

        ``events`` may be a ``VoiceEventLog`` or any iterable of
        ``VoiceEvent``. Returns the number of events successfully applied.
        """
        applied = 0
        records = events.events() if hasattr(events, "events") else list(events)
        for event in records:
            if self.apply(event):
                applied += 1
        return applied