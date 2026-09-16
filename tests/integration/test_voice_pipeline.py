import asyncio

from app.voice.fakes import (
    FakeAIModel,
    FakeLanguageDetector,
    FakeSpeechToText,
    FakeTextToSpeech,
)
from app.voice.language import LanguageDetectionResult, LanguageLabel
from app.voice.service import (
    VoiceConversationRequest,
    VoiceConversationService,
    VoicePipelineStage,
)

FIXTURES = {
    "good morning": "Good morning, what can I do for you?",
    "mera laptop slow": "Mera laptop bahut slow hai, check karo.",
    "hindi namaste": "मेरा नाम राहुल है।",
    "urdu salam": "آپ کیسے ہیں؟",
    "mixed speak": "मेरा laptop slow हो गया है, क्या हुआ?",
}

DETECTIONS = {
    "Good morning, what can I do for you?": LanguageDetectionResult.detected(
        LanguageLabel.ENGLISH, confidence=0.9, languages=(LanguageLabel.ENGLISH,)
    ),
    "Mera laptop bahut slow hai, check karo.": LanguageDetectionResult.detected(
        LanguageLabel.HINGLISH, confidence=0.7, languages=(LanguageLabel.HINGLISH,)
    ),
    "मेरा नाम राहुल है।": LanguageDetectionResult.detected(
        LanguageLabel.HINDI, confidence=0.95, languages=(LanguageLabel.HINDI,)
    ),
    "آپ کیسے ہیں؟": LanguageDetectionResult.detected(
        LanguageLabel.URDU, confidence=0.9, languages=(LanguageLabel.URDU,)
    ),
    "मेरा laptop slow हो गया है, क्या हुआ?": LanguageDetectionResult.mixed(
        LanguageLabel.HINDI, LanguageLabel.ENGLISH
    ),
}


def build_pipeline(
    replies: list[str] | None = None,
) -> tuple[VoiceConversationService, FakeSpeechToText, FakeLanguageDetector, FakeAIModel, FakeTextToSpeech]:
    stt = FakeSpeechToText(fixtures=FIXTURES)
    detector = FakeLanguageDetector(fixtures=DETECTIONS)
    ai = FakeAIModel(replies=replies)
    tts = FakeTextToSpeech()
    service = VoiceConversationService(stt=stt, tts=tts, detector=detector, ai_model=ai)
    return service, stt, detector, ai, tts


def test_complete_fake_voice_pipeline() -> None:
    service, stt, detector, ai, tts = build_pipeline(replies=["Here is my reply."])
    result = asyncio.run(
        service.handle(VoiceConversationRequest(audio=b"good morning"))
    )
    assert result.success is True
    assert result.stage is VoicePipelineStage.COMPLETE
    assert result.transcription == "Good morning, what can I do for you?"
    assert result.language == "english"
    assert result.detection is not None
    assert result.detection.label is LanguageLabel.ENGLISH
    assert result.response_style is not None
    assert result.response_style.label is LanguageLabel.ENGLISH
    assert result.ai_response == "Here is my reply."
    assert result.audio is not None
    assert result.audio.content == b"Here is my reply."
    assert result.audio.format == "text"
    assert result.error is None
    assert stt.requests[0].audio == b"good morning"
    assert detector.name == "fake-language-detector"
    assert len(ai.chat_requests) == 1
    assert len(tts.requests) == 1


def test_full_pipeline_english_turn() -> None:
    service, *_ = build_pipeline(replies=["Glad to help."])
    result = asyncio.run(service.handle(VoiceConversationRequest(audio=b"good morning")))
    assert result.success is True
    assert result.language == "english"
    assert result.ai_response == "Glad to help."
    assert result.audio is not None
    assert result.audio.content == b"Glad to help."


def test_full_pipeline_hindi_turn() -> None:
    service, *_ = build_pipeline(replies=["नमस्ते।"])
    result = asyncio.run(
        service.handle(VoiceConversationRequest(audio=b"hindi namaste"))
    )
    assert result.success is True
    assert result.language == "hindi"
    assert result.response_style is not None
    assert result.response_style.label is LanguageLabel.HINDI
    assert result.audio is not None
    assert result.audio.content == "नमस्ते।".encode("utf-8")


def test_full_pipeline_hinglish_turn() -> None:
    service, *_ = build_pipeline(replies=["Thik hai, check karta hoon."])
    result = asyncio.run(
        service.handle(VoiceConversationRequest(audio=b"mera laptop slow"))
    )
    assert result.success is True
    assert result.language == "hinglish"
    assert result.response_style is not None
    assert result.response_style.preserve_mixed is True
    assert result.audio is not None
    assert result.audio.content == "Thik hai, check karta hoon.".encode("utf-8")


def test_full_pipeline_urdu_turn() -> None:
    service, *_ = build_pipeline(replies=["جی بالکل۔"])
    result = asyncio.run(service.handle(VoiceConversationRequest(audio=b"urdu salam")))
    assert result.success is True
    assert result.language == "urdu"
    assert result.response_style is not None
    assert result.response_style.label is LanguageLabel.URDU
    assert result.audio is not None
    assert result.audio.content == "جی بالکل۔".encode("utf-8")


def test_full_pipeline_mixed_turn() -> None:
    service, *_ = build_pipeline(replies=["Check karta hoon."])
    result = asyncio.run(
        service.handle(VoiceConversationRequest(audio=b"mixed speak"))
    )
    assert result.success is True
    assert result.language == "mixed"
    assert result.detection is not None
    assert result.detection.is_mixed is True
    assert result.response_style is not None
    assert result.response_style.preserve_mixed is True


def test_full_pipeline_language_switching_across_turns() -> None:
    service, *_ = build_pipeline(replies=["Sure.", "Kya karna hai?"])
    first = asyncio.run(
        service.handle(VoiceConversationRequest(audio=b"good morning"))
    )
    second = asyncio.run(
        service.handle(VoiceConversationRequest(audio=b"mera laptop slow"))
    )
    assert first.success is True
    assert first.language == "english"
    assert second.success is True
    assert second.language == "hinglish"
    assert second.response_style is not None
    assert service.conversation_language.latest_style is second.response_style


def test_full_pipeline_stt_failure_is_controlled() -> None:
    service, *_ = build_pipeline()
    result = asyncio.run(
        service.handle(VoiceConversationRequest(audio=b"unrecognized audio"))
    )
    assert result.success is False
    assert result.stage is VoicePipelineStage.STT
    assert result.error is not None


def test_full_pipeline_passes_previous_turn_to_ai() -> None:
    service, _, _, ai, _ = build_pipeline(replies=["first", "second"])
    asyncio.run(service.handle(VoiceConversationRequest(audio=b"good morning")))
    asyncio.run(service.handle(VoiceConversationRequest(audio=b"mera laptop slow")))
    assert len(ai.chat_requests) == 2
    second_contents = [message.content for message in ai.chat_requests[1]]
    assert "Good morning, what can I do for you?" in second_contents
    assert "first" in second_contents
