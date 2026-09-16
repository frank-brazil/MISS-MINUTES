"""Continuous voice session orchestrator.

``VoiceAssistantService`` coordinates the full advanced voice experience:

capture -> wake word -> VAD -> STT -> language detection -> turn management
     -> response generation (brain) -> TTS -> playback (barge-in capable)

It owns session state, structured events, privacy enforcement, timeouts, and
the interrupt/cancel boundary. Every provider (capture, wake word, VAD, STT,
detector, brain, TTS, output) is injected, so the core is provider-independent
and fully testable offline with fakes. Voice input alone never authorizes an
action: task-oriented requests go through a brain that reuses the Orchestrator
and its CHUNK 30 security seam.
"""

import asyncio
import logging
from enum import StrEnum
from time import monotonic
from typing import Callable

from pydantic import BaseModel, field_validator

from app.security.manager import SecurityManager
from app.voice.audio import AudioCaptureProvider, AudioData, CaptureError
from app.voice.base import (
    SpeechInput,
    SpeechToText,
    SpeechToTextResult,
    TextToSpeech,
    TextToSpeechRequest,
    TextToSpeechResult,
)
from app.voice.brain import VoiceBrain, VoiceBrainRequest, VoiceBrainResult
from app.voice.events import VoiceEventLog, VoiceEventType
from app.voice.language import (
    ConversationLanguage,
    LanguageDetectionResult,
    LanguageDetector,
    ResponseStyle,
)
from app.voice.output import AudioOutputProvider
from app.voice.privacy import VoicePrivacyGuard
from app.voice.response_policy import SpokenResponseProfile, VoiceResponsePolicy
from app.voice.session import (
    VoiceInputState,
    VoiceSession,
    VoiceSessionState,
)
from app.voice.turns import ConversationTurn, ConversationTurnManager
from app.voice.vad import VoiceActivityDetector
from app.voice.wakeword import WakeWordDetector


class VoiceAssistantConfig(BaseModel):
    """Timeout, turn, and wake behavior for a voice assistant."""

    wake_required: bool = True
    idle_listening_timeout_seconds: float = 30.0
    max_utterance_duration_seconds: float = 60.0
    max_response_seconds: float = 30.0
    max_speaking_seconds: float = 120.0
    max_turns: int = 100

    @field_validator(
        "idle_listening_timeout_seconds",
        "max_utterance_duration_seconds",
        "max_response_seconds",
        "max_speaking_seconds",
    )
    @classmethod
    def _timeouts_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeouts must be positive")
        return value

    @field_validator("max_turns")
    @classmethod
    def _max_turns_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_turns must be at least 1")
        return value


class VoiceTurnOutcome(StrEnum):
    """Outcome of one processed voice turn."""

    COMPLETED = "completed"
    EMPTY = "empty"
    STT_FAILED = "stt_failed"
    LANGUAGE_FAILED = "language_failed"
    AI_FAILED = "ai_failed"
    TTS_FAILED = "tts_failed"
    PLAYBACK_FAILED = "playback_failed"
    DENIED = "denied"
    TIMED_OUT = "timed_out"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


class VoiceTurnResult(BaseModel):
    """Typed result of one processed voice turn."""

    turn_id: int | None = None
    outcome: VoiceTurnOutcome
    success: bool
    transcription: str | None = None
    response: str | None = None
    language: str | None = None
    error: str | None = None
    interrupted: bool = False


class VoiceAssistantService:
    """Orchestrates continuous voice sessions end to end.

    All providers are injected; nothing here depends on a hardware device
    library or an external service. Sessions run until cancelled, an idle
    timeout, or ``max_turns``. Provider failures become structured events and
    controlled turn results instead of escaping.
    """

    def __init__(
        self,
        *,
        capture: AudioCaptureProvider,
        wakeword: WakeWordDetector,
        vad: VoiceActivityDetector,
        stt: SpeechToText,
        detector: LanguageDetector,
        brain: VoiceBrain,
        tts: TextToSpeech,
        output: AudioOutputProvider,
        turns: ConversationTurnManager | None = None,
        response_policy: VoiceResponsePolicy | None = None,
        conversation_language: ConversationLanguage | None = None,
        privacy: VoicePrivacyGuard | None = None,
        events: VoiceEventLog | None = None,
        security: SecurityManager | None = None,
        config: VoiceAssistantConfig | None = None,
        session: VoiceSession | None = None,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        if response_policy is None:
            from app.voice.response_policy import DefaultVoiceResponsePolicy

            response_policy = DefaultVoiceResponsePolicy()
        self._capture = capture
        self._wakeword = wakeword
        self._vad = vad
        self._stt = stt
        self._detector = detector
        self._brain = brain
        self._tts = tts
        self._output = output
        self._turns = turns or ConversationTurnManager()
        self._policy = response_policy
        self._conversation_language = conversation_language or ConversationLanguage()
        self._privacy = privacy or VoicePrivacyGuard()
        self._events = events or VoiceEventLog()
        self._security = security
        self._config = config or VoiceAssistantConfig()
        self._session = session or VoiceSession()
        self._now_fn = now_fn or monotonic
        self._interrupt_event = asyncio.Event()
        self._barge_in_seed: list[AudioData] = []
        self._last_turn_result: VoiceTurnResult | None = None
        self._running = False
        self._logger = logging.getLogger(__name__)

    @property
    def session(self) -> VoiceSession:
        return self._session

    @property
    def events(self) -> VoiceEventLog:
        return self._events

    @property
    def turns(self) -> ConversationTurnManager:
        return self._turns

    @property
    def security(self) -> SecurityManager | None:
        return self._security

    @property
    def conversation_language(self) -> ConversationLanguage:
        return self._conversation_language

    @property
    def last_turn_result(self) -> VoiceTurnResult | None:
        return self._last_turn_result

    @property
    def config(self) -> VoiceAssistantConfig:
        return self._config

    @property
    def _session_id_str(self) -> str:
        return str(self._session.session_id)

    @property
    def _now(self) -> float:
        return self._now_fn()

    # ------------------------------------------------------------------
    # Public control boundaries
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Run the continuous session until idle, cancel, or max turns."""
        if self._running:
            raise RuntimeError("voice assistant is already running")
        if self._session.state is not VoiceSessionState.IDLE:
            raise RuntimeError(
                f"voice assistant session is in state {self._session.state.value}"
            )
        self._running = True
        self._session.mark_state(VoiceSessionState.LISTENING)
        self._events.record(
            VoiceEventType.SESSION_STARTED,
            session_id=self._session_id_str,
            success=True,
            message="voice session started",
        )
        try:
            await self._capture.start()
        except CaptureError as exc:
            self._events.record(
                VoiceEventType.SESSION_ERROR,
                session_id=self._session_id_str,
                success=False,
                message=f"microphone unavailable: {exc}",
            )
            self._session.mark_error(f"capture unavailable: {exc}")
            self._events.record(
                VoiceEventType.SESSION_STOPPED,
                session_id=self._session_id_str,
                success=False,
                message="session failed at start",
            )
            await self._stop_hardware()
            self._running = False
            return
        try:
            if self._config.wake_required:
                woke = await self._wait_for_wake()
                if not woke:
                    self._events.record(
                        VoiceEventType.SESSION_IDLE_TIMEOUT,
                        session_id=self._session_id_str,
                        success=False,
                        message="no wake word within the listening window",
                    )
                    self._session.mark_state(VoiceSessionState.STOPPED)
                    return

            while not self._session.is_cancelled:
                if self._session.turn_count >= self._config.max_turns:
                    break
                utterance = await self._capture_utterance()
                if utterance is None:
                    if self._session.is_cancelled:
                        break
                    self._events.record(
                        VoiceEventType.SESSION_IDLE_TIMEOUT,
                        session_id=self._session_id_str,
                        success=False,
                        message="no speech within the listening window",
                    )
                    self._session.mark_state(VoiceSessionState.STOPPED)
                    return
                self._last_turn_result = await self._process_utterance(utterance)
        except CaptureError as exc:
            self._logger.warning(
                "Voice session aborted by capture error: %s", exc
            )
            self._session.mark_error(f"capture unavailable: {exc}")
        finally:
            if self._session.state is not VoiceSessionState.ERROR:
                self._session.mark_state(VoiceSessionState.STOPPED)
            self._events.record(
                VoiceEventType.SESSION_STOPPED,
                session_id=self._session_id_str,
                success=True,
                message=f"session stopped: turns={self._session.turn_count}",
            )
            await self._stop_hardware()
            self._running = False

    async def interrupt(self) -> None:
        """Cancel active playback (barge-in boundary)."""
        self._interrupt_event.set()
        if self._output.is_speaking():
            await self._output.stop()

    async def cancel(self) -> None:
        """Cancel the whole session and release resources."""
        self._session.cancel()
        self._events.record(
            VoiceEventType.SESSION_CANCELLED,
            session_id=self._session_id_str,
            success=False,
            message="session cancelled",
        )
        self._interrupt_event.set()
        await self._stop_hardware()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _stop_hardware(self) -> None:
        if self._output.is_speaking():
            await self._output.stop()
        try:
            await self._capture.stop()
            await self._capture.close()
        except Exception as exc:
            self._logger.warning(
                "Capture cleanup raised %s", type(exc).__name__
            )
        try:
            await self._output.close()
        except Exception as exc:
            self._logger.warning(
                "Output cleanup raised %s", type(exc).__name__
            )

    async def _read_frame(self) -> AudioData | None:
        try:
            frame = await self._capture.read()
        except CaptureError as exc:
            self._events.record(
                VoiceEventType.SESSION_ERROR,
                session_id=self._session_id_str,
                success=False,
                message=f"microphone unavailable: {exc}",
            )
            self._session.mark_error(f"capture unavailable: {exc}")
            raise
        except Exception as exc:
            self._events.record(
                VoiceEventType.SESSION_ERROR,
                session_id=self._session_id_str,
                success=False,
                message=f"capture read raised {type(exc).__name__}",
            )
            self._session.mark_error(f"capture read failed: {type(exc).__name__}")
            raise CaptureError(f"capture read failed: {type(exc).__name__}") from exc
        return frame

    async def _wait_for_wake(self) -> bool:
        self._session.mark_input(VoiceInputState.WAITING_FOR_WAKE)
        self._session.mark_state(VoiceSessionState.LISTENING)
        await self._wakeword.reset()
        started = self._now
        self._logger.info("Waiting for wake word '%s'", self._wakeword.wake_phrase)
        while not self._session.is_cancelled:
            frame = await self._read_frame()
            if frame is not None:
                result = await self._wakeword.detect(frame)
                if result.detected:
                    self._events.record(
                        VoiceEventType.WAKE_WORD_DETECTED,
                        session_id=self._session_id_str,
                        success=True,
                        message=f"wake word '{self._wakeword.wake_phrase}' detected",
                    )
                    return True
            if self._now - started >= self._config.idle_listening_timeout_seconds:
                return False
            await asyncio.sleep(0)
        return False

    async def _capture_utterance(self) -> AudioData | None:
        self._session.mark_state(VoiceSessionState.LISTENING)
        self._session.mark_input(VoiceInputState.LISTENING)
        await self._vad.reset()
        frames: list[AudioData] = []
        for seed in self._barge_in_seed:
            frames.append(seed)
            await self._feed_vad_frame(seed)
        self._barge_in_seed = []
        started = self._now
        last_activity = started
        while not self._session.is_cancelled:
            frame = await self._read_frame()
            if frame is not None:
                last_activity = self._now
                result = await self._feed_vad_frame(frame)
                if result.speech:
                    frames.append(frame)
                if result.ended and frames:
                    break
            if self._now - started >= self._config.max_utterance_duration_seconds:
                break
            if self._now - last_activity >= self._config.idle_listening_timeout_seconds:
                break
            await asyncio.sleep(0)
        if not frames:
            return None
        audio = self._join_frames(frames)
        if audio is None:
            return None
        self._session.mark_input(VoiceInputState.UTTERANCE)
        return audio

    async def _feed_vad_frame(self, frame: AudioData):
        result = await self._vad.feed(frame)
        if result.started:
            self._session.mark_state(VoiceSessionState.CAPTURING)
            self._events.record(
                VoiceEventType.SPEECH_STARTED,
                session_id=self._session_id_str,
                success=True,
            )
        if result.ended:
            self._events.record(
                VoiceEventType.SPEECH_ENDED,
                session_id=self._session_id_str,
                success=True,
            )
        return result

    def _join_frames(self, frames: list[AudioData]) -> AudioData | None:
        content = b"".join(frame.content for frame in frames)
        if not content:
            return None
        return AudioData(
            content=content,
            format=frames[0].format,
            sample_rate=frames[0].sample_rate,
        )

    async def _process_utterance(self, utterance: AudioData) -> VoiceTurnResult:
        self._session.mark_state(VoiceSessionState.TRANSCRIBING)
        self._session.mark_input(VoiceInputState.PROCESSING)
        self._events.record(
            VoiceEventType.TRANSCRIPTION_STARTED,
            session_id=self._session_id_str,
            success=True,
            message=f"input_bytes={len(utterance.content)}",
        )
        buffer_id = self._privacy.retain_audio(utterance)
        stt_result = await self._transcribe(utterance)
        self._privacy.release_audio(buffer_id)
        if stt_result is None or not stt_result.success:
            error = (
                stt_result.error if stt_result is not None else "speech-to-text failed"
            )
            self._events.record(
                VoiceEventType.TRANSCRIPTION_COMPLETED,
                session_id=self._session_id_str,
                success=False,
                message=error,
            )
            self._events.record(
                VoiceEventType.TURN_ERROR,
                session_id=self._session_id_str,
                success=False,
                message=f"speech-to-text failed: {error}",
            )
            return VoiceTurnResult(
                outcome=VoiceTurnOutcome.STT_FAILED,
                success=False,
                error=error,
            )
        text = (stt_result.text or "").strip()
        self._events.record(
            VoiceEventType.TRANSCRIPTION_COMPLETED,
            session_id=self._session_id_str,
            success=True,
            language=stt_result.language,
            message=f"transcription_chars={len(text)}",
        )
        if not text:
            return VoiceTurnResult(
                outcome=VoiceTurnOutcome.EMPTY,
                success=False,
                error="speech-to-text produced no text",
            )

        detection = await self._detect_language(text)
        if detection is None:
            self._events.record(
                VoiceEventType.TURN_ERROR,
                session_id=self._session_id_str,
                success=False,
                message="language detection failed",
            )
            return VoiceTurnResult(
                outcome=VoiceTurnOutcome.LANGUAGE_FAILED,
                success=False,
                transcription=text,
                error="language detection failed",
            )

        style = self._conversation_language.update(detection)
        self._session.begin_turn()
        turn = self._turns.begin_turn(
            self._session_id_str,
            text=text,
            detection=detection,
            style=style,
            audio_bytes=len(utterance.content),
            now=self._now,
        )

        self._session.mark_state(VoiceSessionState.THINKING)
        self._events.record(
            VoiceEventType.AI_STARTED,
            session_id=self._session_id_str,
            turn_id=turn.turn_id,
            success=True,
        )
        brain_result = await self._respond(turn, text, stt_result.language, style)
        if brain_result is None:
            self._turns.complete_turn(
                turn.turn_id,
                error="response timed out",
                success=False,
                now=self._now,
            )
            return VoiceTurnResult(
                turn_id=turn.turn_id,
                outcome=VoiceTurnOutcome.TIMED_OUT,
                success=False,
                transcription=text,
                error="response timed out",
            )
        if brain_result.denied:
            error = brain_result.error or "response denied by security policy"
            self._events.record(
                VoiceEventType.TURN_ERROR,
                session_id=self._session_id_str,
                turn_id=turn.turn_id,
                success=False,
                message="response denied by security policy",
            )
            self._turns.complete_turn(
                turn.turn_id, error=error, success=False, now=self._now
            )
            return VoiceTurnResult(
                turn_id=turn.turn_id,
                outcome=VoiceTurnOutcome.DENIED,
                success=False,
                transcription=text,
                error=error,
            )
        if not brain_result.success:
            error = brain_result.error or "response generation failed"
            self._events.record(
                VoiceEventType.TURN_ERROR,
                session_id=self._session_id_str,
                turn_id=turn.turn_id,
                success=False,
                message="response generation failed",
            )
            self._turns.complete_turn(
                turn.turn_id, error=error, success=False, now=self._now
            )
            return VoiceTurnResult(
                turn_id=turn.turn_id,
                outcome=VoiceTurnOutcome.AI_FAILED,
                success=False,
                transcription=text,
                error=error,
            )
        response = (brain_result.response or "").strip()
        if not response:
            self._turns.complete_turn(
                turn.turn_id,
                error="brain returned an empty response",
                success=False,
                now=self._now,
            )
            return VoiceTurnResult(
                turn_id=turn.turn_id,
                outcome=VoiceTurnOutcome.AI_FAILED,
                success=False,
                transcription=text,
                error="brain returned an empty response",
            )
        self._events.record(
            VoiceEventType.AI_COMPLETED,
            session_id=self._session_id_str,
            turn_id=turn.turn_id,
            success=True,
            language=detection.label.value,
            message=f"response_chars={len(response)}",
        )

        profile = self._policy.profile_for(text=text, style=style, response_text=response)
        tts_result = await self._synthesize(response, profile)
        if tts_result is None or not tts_result.success:
            error = (
                tts_result.error
                if tts_result is not None
                else "text-to-speech failed"
            )
            self._events.record(
                VoiceEventType.TURN_ERROR,
                session_id=self._session_id_str,
                turn_id=turn.turn_id,
                success=False,
                message="text-to-speech failed",
            )
            self._turns.complete_turn(
                turn.turn_id, error=error, success=False, now=self._now
            )
            return VoiceTurnResult(
                turn_id=turn.turn_id,
                outcome=VoiceTurnOutcome.TTS_FAILED,
                success=False,
                transcription=text,
                response=response,
                error=error,
            )
        if tts_result.audio is None:
            self._turns.complete_turn(
                turn.turn_id,
                error="text-to-speech produced no inline audio",
                success=False,
                now=self._now,
            )
            return VoiceTurnResult(
                turn_id=turn.turn_id,
                outcome=VoiceTurnOutcome.TTS_FAILED,
                success=False,
                transcription=text,
                response=response,
                error="text-to-speech produced no inline audio",
            )

        speak = await self._speak(turn, tts_result.audio)
        if speak == "failed":
            self._turns.complete_turn(
                turn.turn_id,
                error="playback failed",
                success=False,
                now=self._now,
            )
            return VoiceTurnResult(
                turn_id=turn.turn_id,
                outcome=VoiceTurnOutcome.PLAYBACK_FAILED,
                success=False,
                transcription=text,
                response=response,
                language=detection.label.value,
                error="playback failed",
            )
        if speak == "cancelled":
            self._turns.complete_turn(
                turn.turn_id,
                error="session cancelled during playback",
                success=False,
                interrupted=True,
                now=self._now,
            )
            return VoiceTurnResult(
                turn_id=turn.turn_id,
                outcome=VoiceTurnOutcome.CANCELLED,
                success=False,
                transcription=text,
                response=response,
                language=detection.label.value,
                interrupted=True,
                error="session cancelled during playback",
            )

        interrupted = speak == "interrupted"
        self._turns.complete_turn(
            turn.turn_id,
            response_text=response,
            success=True,
            interrupted=interrupted,
            now=self._now,
        )
        self._events.record(
            VoiceEventType.TURN_COMPLETED,
            session_id=self._session_id_str,
            turn_id=turn.turn_id,
            success=True,
            language=detection.label.value,
            interrupted=interrupted,
            message=f"turn completed: response_chars={len(response)}",
        )
        self._session.language = detection.label.value
        self._session.finish_turn()
        if interrupted:
            return VoiceTurnResult(
                turn_id=turn.turn_id,
                outcome=VoiceTurnOutcome.INTERRUPTED,
                success=True,
                transcription=text,
                response=response,
                language=detection.label.value,
                interrupted=True,
            )
        return VoiceTurnResult(
            turn_id=turn.turn_id,
            outcome=VoiceTurnOutcome.COMPLETED,
            success=True,
            transcription=text,
            response=response,
            language=detection.label.value,
        )

    async def _transcribe(self, utterance: AudioData) -> SpeechToTextResult | None:
        try:
            return await self._stt.transcribe(
                SpeechInput(
                    audio=utterance.content,
                    format=utterance.format,
                    sample_rate=utterance.sample_rate,
                )
            )
        except Exception as exc:
            self._logger.warning(
                "Voice STT raised %s", type(exc).__name__
            )
            self._events.record(
                VoiceEventType.TURN_ERROR,
                session_id=self._session_id_str,
                success=False,
                message=f"speech-to-text provider error: {type(exc).__name__}",
            )
            return None

    async def _detect_language(self, text: str) -> LanguageDetectionResult | None:
        try:
            return await self._detector.detect(text)
        except Exception as exc:
            self._logger.warning(
                "Voice language detection raised %s", type(exc).__name__
            )
            self._events.record(
                VoiceEventType.TURN_ERROR,
                session_id=self._session_id_str,
                success=False,
                message=f"language detection provider error: {type(exc).__name__}",
            )
            return None

    async def _respond(
        self,
        turn: ConversationTurn,
        text: str,
        language: str | None,
        style: ResponseStyle,
    ) -> VoiceBrainResult | None:
        request = VoiceBrainRequest(
            session_id=self._session_id_str,
            turn_id=turn.turn_id,
            text=text,
            language=language,
            style=style,
        )
        try:
            result = await asyncio.wait_for(
                self._brain.respond(request),
                timeout=self._config.max_response_seconds,
            )
            return result
        except asyncio.TimeoutError:
            self._logger.warning("Voice brain response timed out")
            return None
        except Exception as exc:
            self._logger.warning("Voice brain raised %s", type(exc).__name__)
            self._events.record(
                VoiceEventType.TURN_ERROR,
                session_id=self._session_id_str,
                turn_id=turn.turn_id,
                success=False,
                message=f"response generation provider error: {type(exc).__name__}",
            )
            return VoiceBrainResult.fail(
                f"response generation provider error: {type(exc).__name__}"
            )

    async def _synthesize(
        self, text: str, profile: SpokenResponseProfile
    ) -> TextToSpeechResult | None:
        request = TextToSpeechRequest(
            text=text,
            language=profile.language,
            voice=profile.voice,
        )
        try:
            return await self._tts.synthesize(request)
        except Exception as exc:
            self._logger.warning("Voice TTS raised %s", type(exc).__name__)
            self._events.record(
                VoiceEventType.TURN_ERROR,
                session_id=self._session_id_str,
                success=False,
                message=f"text-to-speech provider error: {type(exc).__name__}",
            )
            return None

    async def _speak(self, turn, audio: AudioData) -> str:
        self._session.mark_state(VoiceSessionState.SPEAKING)
        self._interrupt_event.clear()
        self._events.record(
            VoiceEventType.SPEAKING_STARTED,
            session_id=self._session_id_str,
            turn_id=turn.turn_id,
            success=True,
            message=f"speech_bytes={len(audio.content)}",
        )
        play_result = await self._output.play(audio)
        if not play_result.success:
            self._logger.warning("Voice playback failed: %s", play_result.error)
            self._events.record(
                VoiceEventType.SPEAKING_STOPPED,
                session_id=self._session_id_str,
                turn_id=turn.turn_id,
                success=False,
                message="playback failed",
            )
            return "failed"

        started = self._now
        interrupted = False
        timed_out = False
        try:
            while (
                self._output.is_speaking()
                and not self._session.is_cancelled
                and not self._interrupt_event.is_set()
            ):
                if self._now - started >= self._config.max_speaking_seconds:
                    timed_out = True
                    break
                barge_frame = await self._read_frame()
                if barge_frame is not None:
                    self._barge_in_seed = [barge_frame]
                    self._interrupt_event.set()
                    interrupted = True
                await asyncio.sleep(0)
        finally:
            if self._output.is_speaking():
                await self._output.stop()

        interrupted = interrupted or self._interrupt_event.is_set()
        self._events.record(
            VoiceEventType.SPEAKING_STOPPED,
            session_id=self._session_id_str,
            turn_id=turn.turn_id,
            success=True,
            interrupted=interrupted,
        )

        if self._session.is_cancelled and not interrupted:
            return "cancelled"
        if interrupted:
            self._events.record(
                VoiceEventType.SPEAKING_INTERRUPTED,
                session_id=self._session_id_str,
                turn_id=turn.turn_id,
                success=True,
                interrupted=True,
                message="speech interrupted by new input",
            )
            return "interrupted"
        if timed_out:
            return "timeout"
        return "completed"
