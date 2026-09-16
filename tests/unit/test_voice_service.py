import asyncio
import logging
from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from app.core.ai import AIMessage, AIModel, AIResponse, ToolDefinition
from app.voice.base import TextToSpeechRequest, TextToSpeechResult
from app.voice.fakes import (
    FakeAIModel,
    FakeLanguageDetector,
    FakeSpeechToText,
    FakeTextToSpeech,
)
from app.voice.language import ConversationLanguage, LanguageDetectionResult, LanguageLabel
from app.voice.service import (
    VoiceConversationRequest,
    VoiceConversationResult,
    VoiceConversationService,
    VoicePipelineStage,
)

EN_AUDIO = b"hello there"
EN_TEXT = "Hello there, how can I help?"
HI_AUDIO = b"hindi namaste"
HI_TEXT = "आप कैसे हैं?"
HE_AUDIO = b"mera laptop"
HE_TEXT = "Mera laptop slow hai"
UR_AUDIO = b"urdu salam"
UR_TEXT = "آپ کیسے ہیں؟"
MX_AUDIO = b"mixed speak"
MX_TEXT = "Mera laptop slow ho gaya, kya hua?"


def detection_for(label: LanguageLabel, confidence: float = 0.9) -> LanguageDetectionResult:
    return LanguageDetectionResult.detected(
        label, confidence=confidence, languages=(label,)
    )


STT_FIXTURES = {
    EN_AUDIO.decode("utf-8"): EN_TEXT,
    HI_AUDIO.decode("utf-8"): HI_TEXT,
    HE_AUDIO.decode("utf-8"): HE_TEXT,
    UR_AUDIO.decode("utf-8"): UR_TEXT,
    MX_AUDIO.decode("utf-8"): MX_TEXT,
}

DETECTIONS = {
    EN_TEXT: detection_for(LanguageLabel.ENGLISH),
    HI_TEXT: detection_for(LanguageLabel.HINDI, 0.95),
    HE_TEXT: detection_for(LanguageLabel.HINGLISH, 0.7),
    UR_TEXT: detection_for(LanguageLabel.URDU, 0.9),
    MX_TEXT: LanguageDetectionResult.mixed(LanguageLabel.HINDI, LanguageLabel.ENGLISH),
}

LANGUAGE_CASES = [
    {"audio": EN_AUDIO, "text": EN_TEXT, "label": LanguageLabel.ENGLISH, "hint": "en"},
    {"audio": HI_AUDIO, "text": HI_TEXT, "label": LanguageLabel.HINDI, "hint": "hi"},
    {"audio": HE_AUDIO, "text": HE_TEXT, "label": LanguageLabel.HINGLISH, "hint": "en"},
    {"audio": UR_AUDIO, "text": UR_TEXT, "label": LanguageLabel.URDU, "hint": "ur"},
    {"audio": MX_AUDIO, "text": MX_TEXT, "label": LanguageLabel.MIXED, "hint": None},
]


class BlankReplyAIModel(AIModel):
    name = "blank-ai"
    description = "Returns blank content for service tests."

    async def chat(
        self,
        messages: Sequence[AIMessage],
        *,
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AIResponse:
        return AIResponse.ok(content="   ")


class FlakyTextToSpeech(FakeTextToSpeech):
    """Fails for the first ``fail_times`` calls, then behaves normally."""

    def __init__(self, *, fail_times: int = 1) -> None:
        super().__init__()
        self._remaining_failures = fail_times

    async def synthesize(self, request: TextToSpeechRequest) -> TextToSpeechResult:
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            return TextToSpeechResult.fail(error="simulated text-to-speech failure")
        return await super().synthesize(request)


def build_service(
    *,
    stt: FakeSpeechToText | None = None,
    detector: FakeLanguageDetector | None = None,
    ai: FakeAIModel | None = None,
    tts: FakeTextToSpeech | None = None,
    conversation_language: ConversationLanguage | None = None,
) -> tuple[VoiceConversationService, FakeSpeechToText, FakeLanguageDetector, FakeAIModel, FakeTextToSpeech]:
    stt = stt or FakeSpeechToText(fixtures=STT_FIXTURES)
    detector = detector or FakeLanguageDetector(fixtures=DETECTIONS)
    ai = ai or FakeAIModel()
    tts = tts or FakeTextToSpeech()
    service = VoiceConversationService(
        stt=stt,
        tts=tts,
        detector=detector,
        ai_model=ai,
        conversation_language=conversation_language,
    )
    return service, stt, detector, ai, tts


def request(audio: bytes = EN_AUDIO, **kwargs) -> VoiceConversationRequest:
    return VoiceConversationRequest(audio=audio, **kwargs)


def test_voice_conversation_request_fields_and_defaults() -> None:
    req = request(request_id="req-1", language_hint="hi", sample_rate=16000)
    assert req.audio == EN_AUDIO
    assert req.format == "wav"
    assert req.sample_rate == 16000
    assert req.language_hint == "hi"
    assert req.request_id == "req-1"


def test_voice_conversation_request_defaults() -> None:
    req = request()
    assert req.format == "wav"
    assert req.sample_rate is None
    assert req.language_hint is None
    assert req.request_id is None


def test_voice_conversation_request_rejects_empty_audio() -> None:
    with pytest.raises(ValidationError):
        request(audio=b"")


def test_voice_conversation_request_rejects_blank_format() -> None:
    with pytest.raises(ValidationError, match="format"):
        request(format="   ")


def test_voice_conversation_request_rejects_blank_language_hint() -> None:
    with pytest.raises(ValidationError, match="blank"):
        request(language_hint="   ")


def test_voice_conversation_request_rejects_blank_request_id() -> None:
    with pytest.raises(ValidationError, match="blank"):
        request(request_id="   ")


def test_voice_conversation_request_rejects_invalid_sample_rate() -> None:
    with pytest.raises(ValidationError, match="sample_rate"):
        request(sample_rate=0)


def test_voice_conversation_result_ok_factory() -> None:
    detection = DETECTIONS[EN_TEXT]
    style = ConversationLanguage().update(detection)
    result = VoiceConversationResult.ok(
        request_id="r1",
        transcription=EN_TEXT,
        detection=detection,
        response_style=style,
        ai_response="reply",
    )
    assert result.success is True
    assert result.stage is VoicePipelineStage.COMPLETE
    assert result.language == "english"
    assert result.transcription == EN_TEXT
    assert result.ai_response == "reply"
    assert result.error is None


def test_voice_conversation_result_fail_factory() -> None:
    result = VoiceConversationResult.fail(
        request_id="r1",
        stage=VoicePipelineStage.AI,
        error="boom",
    )
    assert result.success is False
    assert result.stage is VoicePipelineStage.AI
    assert result.error == "boom"


def test_service_requires_injected_components() -> None:
    with pytest.raises(TypeError):
        VoiceConversationService()


def test_full_successful_pipeline_returns_complete_result() -> None:
    service, _, _, ai, tts = build_service(ai=FakeAIModel(default_reply="Sure thing."))
    result = asyncio.run(service.handle(request()))
    assert result.success is True
    assert result.stage is VoicePipelineStage.COMPLETE
    assert result.transcription == EN_TEXT
    assert result.language == "english"
    assert result.detection is not None
    assert result.detection.label is LanguageLabel.ENGLISH
    assert result.response_style is not None
    assert result.response_style.label is LanguageLabel.ENGLISH
    assert result.ai_response == "Sure thing."
    assert result.audio is not None
    assert result.audio.content == b"Sure thing."
    assert result.audio.format == "text"
    assert result.audio_ref is None
    assert result.error is None
    assert len(ai.chat_requests) == 1
    assert len(tts.requests) == 1


@pytest.mark.parametrize("case", LANGUAGE_CASES, ids=[c["label"].value for c in LANGUAGE_CASES])
def test_language_case_is_detected_and_spoken(case) -> None:
    service, _, _, _, tts = build_service(ai=FakeAIModel(default_reply="reply"))
    result = asyncio.run(service.handle(request(audio=case["audio"])))
    assert result.success is True
    assert result.stage is VoicePipelineStage.COMPLETE
    assert result.transcription == case["text"]
    assert result.language == case["label"].value
    assert result.detection is not None
    assert result.detection.label is case["label"]
    assert result.response_style is not None
    assert result.response_style.label is case["label"]
    assert result.ai_response == "reply"
    assert result.audio is not None
    assert result.audio.content == b"reply"
    assert tts.requests[-1].language == case["hint"]


def test_mixed_style_preserves_mixed_guidance() -> None:
    service, _, _, _, _ = build_service()
    result = asyncio.run(service.handle(request(audio=MX_AUDIO)))
    assert result.success is True
    assert result.response_style is not None
    assert result.response_style.preserve_mixed is True
    assert "mixed-language" in result.response_style.guidance


def test_language_switching_across_turns_preserves_context() -> None:
    service, _, _, ai, _ = build_service()
    first = asyncio.run(service.handle(request(audio=EN_AUDIO)))
    second = asyncio.run(service.handle(request(audio=HE_AUDIO)))
    assert first.response_style is not None
    assert first.response_style.label is LanguageLabel.ENGLISH
    assert second.response_style is not None
    assert second.response_style.label is LanguageLabel.HINGLISH
    assert service.conversation_language.latest_style is second.response_style
    assert len(ai.chat_requests) == 2
    second_contents = [message.content for message in ai.chat_requests[1]]
    assert EN_TEXT in second_contents
    assert first.ai_response in second_contents


def test_ai_requests_include_response_style_guidance() -> None:
    service, *_ = build_service()
    asyncio.run(service.handle(request(audio=HI_AUDIO)))
    messages = service.history
    assert len(messages) == 2


def test_conversation_history_accumulates_in_memory() -> None:
    service, *_ = build_service()
    first = asyncio.run(service.handle(request(audio=EN_AUDIO)))
    second = asyncio.run(service.handle(request(audio=HE_AUDIO)))
    assert first.success is True
    assert second.success is True
    assert second.transcription == HE_TEXT
    assert len(service.history) == 4


def test_request_id_generated_when_absent() -> None:
    service, *_ = build_service()
    first = asyncio.run(service.handle(request()))
    second = asyncio.run(service.handle(request()))
    assert first.request_id
    assert second.request_id
    assert first.request_id != second.request_id


def test_request_id_propagated_when_provided() -> None:
    service, *_ = build_service()
    result = asyncio.run(service.handle(request(request_id="custom-id")))
    assert result.request_id == "custom-id"


def test_audio_and_language_hint_forwarded_to_stt() -> None:
    service, _, _, _, _ = build_service()
    asyncio.run(
        service.handle(request(audio=EN_AUDIO, format="webm", language_hint="en"))
    )


def test_stt_result_failure_is_controlled() -> None:
    service, *_ = build_service(stt=FakeSpeechToText(fixtures={}))
    result = asyncio.run(service.handle(request()))
    assert result.success is False
    assert result.stage is VoicePipelineStage.STT
    assert result.error is not None
    assert result.transcription is None


def test_stt_exception_is_controlled() -> None:
    service, *_ = build_service(
        stt=FakeSpeechToText(
            fixtures=STT_FIXTURES, raise_error=ValueError("boom")
        )
    )
    result = asyncio.run(service.handle(request()))
    assert result.success is False
    assert result.stage is VoicePipelineStage.STT
    assert result.error == "speech-to-text provider raised an error"


def test_language_detection_unknown_is_non_fatal() -> None:
    service, *_ = build_service(detector=FakeLanguageDetector())
    result = asyncio.run(service.handle(request(audio=EN_AUDIO)))
    assert result.success is True
    assert result.language == "unknown"
    assert result.detection is not None
    assert result.detection.label is LanguageLabel.UNKNOWN
    assert result.response_style is not None
    assert result.response_style.label is LanguageLabel.UNKNOWN


def test_language_detection_exception_is_controlled() -> None:
    service, *_ = build_service(
        detector=FakeLanguageDetector(
            fixtures=DETECTIONS, raise_error=RuntimeError("boom")
        )
    )
    result = asyncio.run(service.handle(request()))
    assert result.success is False
    assert result.stage is VoicePipelineStage.LANGUAGE
    assert result.error == "language detection failed"
    assert result.transcription == EN_TEXT


def test_ai_failure_result_is_controlled() -> None:
    service, *_ = build_service(ai=FakeAIModel(respond_fail=True))
    result = asyncio.run(service.handle(request()))
    assert result.success is False
    assert result.stage is VoicePipelineStage.AI
    assert result.error == "simulated AI failure"
    assert result.transcription == EN_TEXT
    assert result.detection is not None
    assert result.response_style is not None
    assert result.ai_response is None


def test_ai_exception_is_controlled() -> None:
    service, *_ = build_service(
        ai=FakeAIModel(raise_error=RuntimeError("boom"))
    )
    result = asyncio.run(service.handle(request()))
    assert result.success is False
    assert result.stage is VoicePipelineStage.AI
    assert result.error == "AI provider raised an error"
    assert result.transcription == EN_TEXT


def test_ai_empty_response_is_controlled() -> None:
    service, *_ = build_service(ai=BlankReplyAIModel())
    result = asyncio.run(service.handle(request()))
    assert result.success is False
    assert result.stage is VoicePipelineStage.AI
    assert result.error == "AI model returned an empty response"
    assert result.transcription == EN_TEXT


def test_tts_failure_result_is_controlled() -> None:
    service, *_ = build_service(tts=FakeTextToSpeech(fail=True))
    result = asyncio.run(service.handle(request()))
    assert result.success is False
    assert result.stage is VoicePipelineStage.TTS
    assert result.error == "simulated text-to-speech failure"
    assert result.transcription == EN_TEXT
    assert result.ai_response is not None


def test_tts_exception_is_controlled() -> None:
    service, *_ = build_service(
        tts=FakeTextToSpeech(raise_error=RuntimeError("boom"))
    )
    result = asyncio.run(service.handle(request()))
    assert result.success is False
    assert result.stage is VoicePipelineStage.TTS
    assert result.error == "text-to-speech provider raised an error"
    assert result.transcription == EN_TEXT
    assert result.ai_response is not None


def test_failed_turn_does_not_corrupt_conversation_history() -> None:
    service, *_ = build_service(tts=FlakyTextToSpeech(fail_times=1))
    failed = asyncio.run(service.handle(request(audio=EN_AUDIO)))
    assert failed.success is False
    ok = asyncio.run(service.handle(request(audio=HE_AUDIO)))
    assert ok.success is True
    assert ok.response_style is not None
    assert ok.response_style.label is LanguageLabel.HINGLISH
    contents = [message.content for message in service.history]
    assert len(service.history) == 4
    assert EN_TEXT in contents
    assert HE_TEXT in contents
    assert contents[-1] == "Understood."


def test_structured_logging_records_request_id_stage_and_success(caplog) -> None:
    service, *_ = build_service()
    with caplog.at_level(logging.INFO, logger="app.voice.service"):
        result = asyncio.run(service.handle(request()))
    assert result.success is True
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "request_id=" in messages
    assert "stage=stt" in messages
    assert "stage=language" in messages
    assert "stage=complete" in messages
    assert "success=" in messages


def test_structured_logging_avoids_private_text(caplog) -> None:
    service, *_ = build_service()
    with caplog.at_level(logging.INFO, logger="app.voice.service"):
        asyncio.run(service.handle(request(audio=EN_AUDIO)))
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert EN_TEXT not in messages
    assert "hello there" not in messages


def test_structured_logging_records_language_label(caplog) -> None:
    service, *_ = build_service()
    with caplog.at_level(logging.INFO, logger="app.voice.service"):
        asyncio.run(service.handle(request(audio=HI_AUDIO)))
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "label=hindi" in messages