import asyncio
from collections.abc import Sequence

import pytest

from app.core.ai import AIMessage, AIModel, AIResponse, ToolCall, ToolDefinition
from app.core.orchestrator import Orchestrator
from app.core.permissions import ToolPermission
from app.security.policy import DenyAllPolicy
from app.tools.base import Tool, ToolArguments, ToolResult
from app.voice.assistant import (
    VoiceAssistantConfig,
    VoiceAssistantService,
    VoiceTurnOutcome,
)
from app.voice.audio import CaptureError, FakeAudioCaptureProvider
from app.voice.brain import (
    FakeVoiceBrain,
    OrchestratorVoiceBrain,
    VoiceBrain,
    VoiceBrainRequest,
    VoiceBrainResult,
)
from app.voice.events import VoiceEventLog, VoiceEventType
from app.voice.fakes import (
    FakeLanguageDetector,
    FakeSpeechToText,
    FakeTextToSpeech,
)
from app.voice.language import LanguageDetectionResult, LanguageLabel
from app.voice.output import FakeAudioOutputProvider
from app.voice.privacy import VoicePrivacyGuard
from app.voice.session import VoiceSession, VoiceSessionState
from app.voice.turns import ConversationTurnManager
from app.voice.vad import FakeVoiceActivityDetector
from app.voice.wakeword import FakeWakeWordDetector

EN_TEXT = "Hello there, how can I help?"
HI_TEXT = "आप कैसे हैं?"
DELETE_TEXT = "Delete all project files."

STT_FIXTURES = {
    "hello there": EN_TEXT,
    "hindi namaste": HI_TEXT,
    "delete all project files": DELETE_TEXT,
}


def detection_for(label: LanguageLabel) -> LanguageDetectionResult:
    return LanguageDetectionResult.detected(label, confidence=0.9, languages=(label,))


DETECTIONS = {
    EN_TEXT: detection_for(LanguageLabel.ENGLISH),
    HI_TEXT: detection_for(LanguageLabel.HINDI),
    DELETE_TEXT: detection_for(LanguageLabel.ENGLISH),
}

SEP = b"__silence__"


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def _config(**overrides) -> VoiceAssistantConfig:
    defaults = {
        "wake_required": False,
        "idle_listening_timeout_seconds": 5.0,
        "max_utterance_duration_seconds": 60.0,
        "max_response_seconds": 5.0,
        "max_speaking_seconds": 120.0,
        "max_turns": 100,
    }
    defaults.update(overrides)
    return VoiceAssistantConfig(**defaults)


class Builder:
    def __init__(
        self,
        *,
        frames: list[bytes],
        brain: VoiceBrain | None = None,
        vad: FakeVoiceActivityDetector | None = None,
        stt: FakeSpeechToText | None = None,
        detector: FakeLanguageDetector | None = None,
        output: FakeAudioOutputProvider | None = None,
        config: VoiceAssistantConfig | None = None,
        wakeword: FakeWakeWordDetector | None = None,
        turns: ConversationTurnManager | None = None,
    ) -> None:
        self.clock = Clock()
        self.capture = FakeAudioCaptureProvider([audio(f) for f in frames])
        self.wakeword = wakeword or FakeWakeWordDetector(default=False)
        self.vad = vad or FakeVoiceActivityDetector([True, True, False])
        self.stt = stt or FakeSpeechToText(fixtures=STT_FIXTURES)
        self.detector = detector or FakeLanguageDetector(fixtures=DETECTIONS)
        self.brain = brain or FakeVoiceBrain(default=VoiceBrainResult.ok("Sure, I can help."))
        self.tts = FakeTextToSpeech()
        self.output = output or FakeAudioOutputProvider(auto_stop_after=1)
        self.turns = turns or ConversationTurnManager(now_fn=self.clock)
        self.privacy = VoicePrivacyGuard()
        self.events = VoiceEventLog(now_fn=self.clock)
        self.config = config or _config()
        self.session = VoiceSession(now_fn=self.clock)
        self.service = VoiceAssistantService(
            capture=self.capture,
            wakeword=self.wakeword,
            vad=self.vad,
            stt=self.stt,
            detector=self.detector,
            brain=self.brain,
            tts=self.tts,
            output=self.output,
            turns=self.turns,
            privacy=self.privacy,
            events=self.events,
            config=self.config,
            session=self.session,
            now_fn=self.clock,
        )


def audio(content: bytes) -> object:
    from app.voice.base import AudioData

    return AudioData(content=content, format="text", sample_rate=16000)


async def run_to_stop(service: VoiceAssistantService, clock: Clock) -> VoiceSessionState:
    task = asyncio.create_task(service.run())
    try:
        for _ in range(10000):
            if service.session.state in (
                VoiceSessionState.STOPPED,
                VoiceSessionState.ERROR,
            ):
                break
            await asyncio.sleep(0)
            if _ % 20 == 0:
                clock.value += 0.5
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    if task.done() and not task.cancelled():
        await task
    else:
        raise AssertionError("voice session never stopped")
    return service.session.state


def _assert_event(log: VoiceEventLog, event_type: VoiceEventType) -> None:
    assert log.events_of_type(event_type), f"missing event {event_type.value}"


# ----------------------------------------------------------------------
# Happy path
# ----------------------------------------------------------------------


def test_full_turn_is_transcribed_answered_and_spoken() -> None:
    builder = Builder(frames=[b"hello ", b"there", SEP])
    state = asyncio.run(run_to_stop(builder.service, builder.clock))
    result = builder.service.last_turn_result
    assert state is VoiceSessionState.STOPPED
    assert result is not None
    assert result.outcome is VoiceTurnOutcome.COMPLETED
    assert result.success is True
    assert result.transcription == EN_TEXT
    assert result.response == "Sure, I can help."
    assert result.language == "english"
    assert builder.session.turn_count == 1
    assert len(builder.output.played) == 1
    assert builder.output.played[0].content == b"Sure, I can help."
    turn = builder.turns.latest_turn(builder.service._session_id_str)
    assert turn is not None and turn.success is True
    assert turn.label is LanguageLabel.ENGLISH
    _assert_event(builder.events, VoiceEventType.SPEECH_STARTED)
    _assert_event(builder.events, VoiceEventType.TRANSCRIPTION_COMPLETED)
    _assert_event(builder.events, VoiceEventType.TURN_COMPLETED)
    _assert_event(builder.events, VoiceEventType.SPEAKING_STARTED)
    _assert_event(builder.events, VoiceEventType.SPEAKING_STOPPED)


def test_wake_word_gates_session_and_then_processes_utterance() -> None:
    wakeword = FakeWakeWordDetector([True], default=False)
    builder = Builder(
        frames=[b"wake-frame", b"hello ", b"there", SEP],
        wakeword=wakeword,
        config=_config(wake_required=True),
    )
    asyncio.run(run_to_stop(builder.service, builder.clock))
    assert builder.service.last_turn_result is not None
    assert builder.service.last_turn_result.success is True
    _assert_event(builder.events, VoiceEventType.WAKE_WORD_DETECTED)
    assert wakeword.feed_count == 1


def test_no_wake_word_leads_to_idle_timeout() -> None:
    builder = Builder(
        frames=[],
        config=_config(wake_required=True),
    )
    asyncio.run(run_to_stop(builder.service, builder.clock))
    assert builder.service.last_turn_result is None
    assert builder.session.state is VoiceSessionState.STOPPED
    _assert_event(builder.events, VoiceEventType.SESSION_IDLE_TIMEOUT)


def test_continuous_session_switches_language_across_turns() -> None:
    builder = Builder(
        frames=[
            b"hello ",
            b"there",
            SEP,
            b"hindi ",
            b"namaste",
            SEP,
        ]
    )
    asyncio.run(run_to_stop(builder.service, builder.clock))
    assert builder.session.turn_count == 2
    assert len(builder.output.played) == 2
    second = builder.turns.turns(builder.service._session_id_str)
    assert second[1].label is LanguageLabel.HINDI
    assert builder.session.language == "hindi"
    assert builder.service.conversation_language.latest_style is not None
    assert builder.service.conversation_language.latest_style.label is LanguageLabel.HINDI


def test_second_utterance_in_window_is_continuation() -> None:
    turn_manager = ConversationTurnManager(now_fn=None, continuation_window_seconds=30.0)
    turn_manager._now_fn = lambda: 0.0
    builder = Builder(
        frames=[
            b"hello ",
            b"there",
            SEP,
            b"hindi ",
            b"namaste",
            SEP,
        ],
        turns=turn_manager,
    )
    asyncio.run(run_to_stop(builder.service, builder.clock))
    turns = builder.turns.turns(builder.service._session_id_str)
    assert turns[0].kind.value == "first"
    assert turns[1].kind.value == "continuation"
    assert turns[1].continuation is True


def test_max_turns_bounds_the_session() -> None:
    builder = Builder(
        frames=[
            b"hello ",
            b"there",
            SEP,
            b"hindi ",
            b"namaste",
            SEP,
        ],
        config=_config(max_turns=1),
    )
    asyncio.run(run_to_stop(builder.service, builder.clock))
    assert builder.session.turn_count == 1
    assert builder.session.state is VoiceSessionState.STOPPED


# ----------------------------------------------------------------------
# Interruption and barge-in
# ----------------------------------------------------------------------


def test_external_interrupt_stops_playback_and_marks_turn() -> None:
    builder = Builder(
        frames=[b"hello ", b"there", SEP],
        output=FakeAudioOutputProvider(),  # never auto-stops
        config=_config(max_speaking_seconds=1000.0),
    )

    async def scenario() -> None:
        task = asyncio.create_task(builder.service.run())
        try:
            while not builder.output.is_speaking():
                await asyncio.sleep(0)
            await builder.service.interrupt()
            for _ in range(5000):
                if builder.session.state in (
                    VoiceSessionState.STOPPED,
                    VoiceSessionState.ERROR,
                ):
                    break
                if _ % 20 == 0:
                    builder.clock.value += 0.5
                await asyncio.sleep(0)
            await task
        finally:
            if not task.done():
                task.cancel()

    asyncio.run(scenario())
    result = builder.service.last_turn_result
    assert result is not None
    assert result.outcome is VoiceTurnOutcome.INTERRUPTED
    assert result.interrupted is True
    assert builder.output.stop_requests >= 1
    turn = builder.turns.latest_turn(builder.service._session_id_str)
    assert turn is not None and turn.interrupted is True
    _assert_event(builder.events, VoiceEventType.SPEAKING_INTERRUPTED)


def test_barge_in_captures_new_request_immediately() -> None:
    builder = Builder(
        frames=[
            b"hello ",
            b"there",
            SEP,
            b"hindi ",
            b"namaste",
            SEP,
        ],
        output=FakeAudioOutputProvider(),  # speaks forever until barge-in/timeout
        config=_config(max_speaking_seconds=3.0),
    )

    async def scenario() -> None:
        task = asyncio.create_task(builder.service.run())
        try:
            for _ in range(10000):
                if builder.session.state in (
                    VoiceSessionState.STOPPED,
                    VoiceSessionState.ERROR,
                ):
                    break
                if _ % 20 == 0:
                    builder.clock.value += 0.3
                await asyncio.sleep(0)
            await task
        finally:
            if not task.done():
                task.cancel()

        turns = builder.turns.turns(builder.service._session_id_str)
        assert turns, "expected at least one turn"
        assert turns[0].interrupted is True
        assert turns[-1].success is True
        assert len(builder.output.played) == 2

    asyncio.run(scenario())
    assert builder.session.state is VoiceSessionState.STOPPED
    assert len(builder.output.played) == 2
    last = builder.service.last_turn_result
    assert last is not None and last.transcription == HI_TEXT


# ----------------------------------------------------------------------
# Cancellation
# ----------------------------------------------------------------------


def test_cancel_stops_session_and_records_event() -> None:
    builder = Builder(
        frames=[b"hello ", b"there", SEP],
        output=FakeAudioOutputProvider(),
        config=_config(max_speaking_seconds=1000.0),
    )

    async def scenario() -> None:
        task = asyncio.create_task(builder.service.run())
        try:
            while not builder.output.is_speaking():
                await asyncio.sleep(0)
            await builder.service.cancel()
            await task
        finally:
            if not task.done():
                task.cancel()

    asyncio.run(scenario())
    assert builder.session.is_cancelled is True
    assert builder.session.state is VoiceSessionState.STOPPED
    _assert_event(builder.events, VoiceEventType.SESSION_CANCELLED)
    assert builder.output.is_speaking() is False


# ----------------------------------------------------------------------
# Failure handling
# ----------------------------------------------------------------------


def test_stt_failure_is_structured_and_session_continues() -> None:
    builder = Builder(
        frames=[b"hello ", b"there", SEP],
        stt=FakeSpeechToText(fixtures=STT_FIXTURES, fail=True),
        output=FakeAudioOutputProvider(auto_stop_after=1),
    )
    asyncio.run(run_to_stop(builder.service, builder.clock))
    result = builder.service.last_turn_result
    assert result is not None
    assert result.outcome is VoiceTurnOutcome.STT_FAILED
    assert result.success is False
    assert builder.session.turn_count == 0
    assert builder.output.played == []
    _assert_event(builder.events, VoiceEventType.TURN_ERROR)


def test_language_detection_failure_is_structured() -> None:
    builder = Builder(
        frames=[b"hello ", b"there", SEP],
        detector=FakeLanguageDetector(raise_error=RuntimeError("detection down")),
    )
    asyncio.run(run_to_stop(builder.service, builder.clock))
    result = builder.service.last_turn_result
    assert result is not None
    assert result.outcome is VoiceTurnOutcome.LANGUAGE_FAILED
    _assert_event(builder.events, VoiceEventType.TURN_ERROR)


def test_tts_synthesis_failure_is_structured() -> None:
    tts = FakeTextToSpeech(fail=True)
    builder = Builder(
        frames=[b"hello ", b"there", SEP],
        brain=FakeVoiceBrain(default=VoiceBrainResult.ok("Hi there.")),
    )
    builder.tts = tts
    builder.service._tts = tts
    asyncio.run(run_to_stop(builder.service, builder.clock))
    result = builder.service.last_turn_result
    assert result is not None
    assert result.outcome is VoiceTurnOutcome.TTS_FAILED
    assert builder.output.played == []


def test_brain_denial_is_structured() -> None:
    builder = Builder(
        frames=[b"hello ", b"there", SEP],
        brain=FakeVoiceBrain(
            default=VoiceBrainResult.fail("denied by security policy", denied=True)
        ),
    )
    asyncio.run(run_to_stop(builder.service, builder.clock))
    result = builder.service.last_turn_result
    assert result is not None
    assert result.outcome is VoiceTurnOutcome.DENIED
    assert result.success is False
    assert builder.output.played == []
    turn = builder.turns.latest_turn(builder.service._session_id_str)
    assert turn is not None and turn.success is False


def test_response_timeout_is_structured() -> None:
    class HangingBrain(VoiceBrain):
        name = "hanging-brain"
        description = "A brain that never answers."

        async def respond(self, request: VoiceBrainRequest) -> VoiceBrainResult:
            await asyncio.Event().wait()
            raise AssertionError("should never return")

    builder = Builder(
        frames=[b"hello ", b"there", SEP],
        brain=HangingBrain(),
        config=_config(max_response_seconds=0.02),
    )
    asyncio.run(run_to_stop(builder.service, builder.clock))
    result = builder.service.last_turn_result
    assert result is not None
    assert result.outcome is VoiceTurnOutcome.TIMED_OUT
    assert result.success is False


def test_microphone_unavailable_is_structured_session_error() -> None:
    builder = Builder(frames=[])
    builder.capture = FakeAudioCaptureProvider(
        raise_on_read=CaptureError("microphone not available")
    )
    builder.service._capture = builder.capture
    state = asyncio.run(run_to_stop(builder.service, builder.clock))
    assert state is VoiceSessionState.ERROR
    assert builder.session.last_error is not None
    assert "capture" in (builder.session.last_error or "").lower()
    error_events = builder.events.events_of_type(VoiceEventType.SESSION_ERROR)
    assert error_events
    assert error_events[0].success is False


# ----------------------------------------------------------------------
# Security: voice input cannot bypass tool permissions
# ----------------------------------------------------------------------


class ReadTool(Tool):
    name = "read-tool"
    description = "Read-only tool for the voice security test."
    input_schema = ToolArguments
    permission: ToolPermission = ToolPermission.READ

    def __init__(self) -> None:
        self.called = False

    async def execute(self, **kwargs: object) -> ToolResult:
        self.called = True
        return ToolResult.ok(output="read-output")


class ScriptedAIModel(AIModel):
    name = "scripted-tool-ai"
    description = "Scripted AI that issues one tool call."

    def __init__(self, tool_call: ToolCall) -> None:
        self._tool_call = tool_call
        self._calls = 0

    async def chat(
        self,
        messages: Sequence[AIMessage],
        *,
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AIResponse:
        self._calls += 1
        if self._calls == 1:
            return AIResponse.ok(content="calling a tool", tool_calls=[self._tool_call])
        return AIResponse.fail(error="the requested tool action was denied by security policy")


def test_voice_task_dispatch_goes_through_chunk30_security() -> None:
    tool = ReadTool()
    orchestrator = Orchestrator(
        ai_model=ScriptedAIModel(ToolCall(id="call-1", name=tool.name, arguments={})),
        security=DenyAllPolicy(),
    )
    orchestrator.register_tool(tool)
    brain = OrchestratorVoiceBrain(orchestrator)

    builder = Builder(
        frames=[b"delete all project", b" files", SEP],
        brain=brain,
    )
    asyncio.run(run_to_stop(builder.service, builder.clock))
    result = builder.service.last_turn_result
    assert result is not None
    assert result.outcome is VoiceTurnOutcome.DENIED
    assert result.success is False
    assert tool.called is False
    assert orchestrator.security is not None
    denied = [
        event
        for event in orchestrator.security.audit_store.snapshot()
        if event.reason_code == "deny_all"
    ]
    assert denied
    dispatch = [
        event
        for event in orchestrator.security.audit_store.snapshot()
        if event.action == "voice:dispatch_task"
    ]
    assert dispatch
    assert dispatch[0].origin == "voice"


# ----------------------------------------------------------------------
# Privacy
# ----------------------------------------------------------------------


def test_audio_buffers_are_released_after_processing() -> None:
    builder = Builder(frames=[b"hello ", b"there", SEP])
    asyncio.run(run_to_stop(builder.service, builder.clock))
    assert builder.privacy.live_buffers() == ()
    assert builder.privacy.retained_bytes == 0
    assert builder.privacy.released_bytes == len(b"hello there")
    assert builder.privacy.local_only is True
    assert builder.privacy.can_upload("anything") is False


# ----------------------------------------------------------------------
# Service guards
# ----------------------------------------------------------------------


def test_run_requires_fresh_idle_session() -> None:
    builder = Builder(frames=[b"hello ", b"there", SEP])
    asyncio.run(run_to_stop(builder.service, builder.clock))
    with pytest.raises(RuntimeError):
        asyncio.run(builder.service.run())
