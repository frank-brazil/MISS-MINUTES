"""Voice connection boundary.

``VoiceAvatarAdapter`` translates existing voice-session events into avatar
signals so the character *follows* the conversation (listens, thinks, works,
speaks, celebrates, reacts). It never performs lip-sync (CHUNK 33) and never
modifies the voice pipeline: this is a read-only mapping over the already
published ``VoiceEvent``/``VoiceSessionState`` types.
"""

from typing import Mapping

from app.avatar.controller import AvatarController, AvatarSignal
from app.avatar.models import AvatarState as AvatarStateAlias
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


SESSION_STATE_MAP: Mapping[VoiceSessionState, AvatarStateAlias] = {
    VoiceSessionState.IDLE: AvatarStateAlias.IDLE,
    VoiceSessionState.LISTENING: AvatarStateAlias.LISTENING,
    VoiceSessionState.CAPTURING: AvatarStateAlias.LISTENING,
    VoiceSessionState.TRANSCRIBING: AvatarStateAlias.THINKING,
    VoiceSessionState.THINKING: AvatarStateAlias.THINKING,
    VoiceSessionState.SPEAKING: AvatarStateAlias.SPEAKING,
    VoiceSessionState.INTERRUPTED: AvatarStateAlias.INTERRUPTED,
    VoiceSessionState.STOPPED: AvatarStateAlias.IDLE,
    VoiceSessionState.ERROR: AvatarStateAlias.ERROR,
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

    def translate_session_state(self, state: VoiceSessionState) -> AvatarStateAlias:
        if state not in SESSION_STATE_MAP:
            return AvatarStateAlias.IDLE
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
