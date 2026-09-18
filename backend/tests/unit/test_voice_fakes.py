import asyncio
from datetime import timedelta

import pytest

from app.core.ai import AIMessage, AIModel, AIResponse
from app.voice.base import (
    SpeechInput,
    SpeechToText,
    SpeechToTextResult,
    TextToSpeech,
    TextToSpeechRequest,
    TextToSpeechResult,
)
from app.voice.fakes import (
    FakeAIModel,
    FakeLanguageDetector,
    FakeSpeechToText,
    FakeTextToSpeech,
)
from app.voice.language import LanguageDetectionResult, LanguageDetector, LanguageLabel


class SpeechAssistant:
    """Small dependency-injection showcase: consumes the abstract interfaces."""

    def __init__(self, *, stt: SpeechToText, tts: TextToSpeech) -> None:
        self._stt = stt
        self._tts = tts

    async def handle(
        self, audio: bytes, reply: str
    ) -> tuple[SpeechToTextResult, TextToSpeechResult]:
        transcription = await self._stt.transcribe(SpeechInput(audio=audio))
        speech = await self._tts.synthesize(TextToSpeechRequest(text=reply))
        return transcription, speech


FIXTURES = {
    "hello there": "Hello there, how can I help?",
    "open VS Code": "Please open VS Code.",
}


def test_fake_speech_to_text_satisfies_interface() -> None:
    fake = FakeSpeechToText(fixtures=FIXTURES)
    assert isinstance(fake, SpeechToText)
    assert fake.name == "fake-speech-to-text"
    assert fake.description


def test_fake_speech_to_text_transcribes_fixture() -> None:
    fake = FakeSpeechToText(fixtures=FIXTURES)
    result = asyncio.run(fake.transcribe(SpeechInput(audio=b"hello there")))
    assert result.success is True
    assert result.text == "Hello there, how can I help?"
    assert result.language == "en"
    assert result.confidence == 0.99
    assert result.error is None


def test_fake_speech_to_text_multiple_fixtures() -> None:
    fake = FakeSpeechToText(fixtures=FIXTURES)
    result = asyncio.run(fake.transcribe(SpeechInput(audio=b"open VS Code")))
    assert result.success is True
    assert result.text == "Please open VS Code."


def test_fake_speech_to_text_honors_language_hint() -> None:
    fake = FakeSpeechToText(fixtures=FIXTURES)
    result = asyncio.run(fake.transcribe(SpeechInput(audio=b"hello there", language="hi")))
    assert result.success is True
    assert result.language == "hi"


def test_fake_speech_to_text_custom_defaults() -> None:
    fake = FakeSpeechToText(
        fixtures=FIXTURES,
        default_language="hi",
        default_confidence=0.8,
    )
    result = asyncio.run(fake.transcribe(SpeechInput(audio=b"hello there")))
    assert result.success is True
    assert result.language == "hi"
    assert result.confidence == 0.8


def test_fake_speech_to_text_unknown_audio_fails() -> None:
    fake = FakeSpeechToText(fixtures=FIXTURES)
    result = asyncio.run(fake.transcribe(SpeechInput(audio=b"no such fixture")))
    assert result.success is False
    assert result.text is None
    assert result.error is not None


def test_fake_speech_to_text_non_utf8_audio_fails() -> None:
    fake = FakeSpeechToText(fixtures=FIXTURES)
    result = asyncio.run(fake.transcribe(SpeechInput(audio=b"\xff\xff\xfe")))
    assert result.success is False
    assert result.error is not None


def test_fake_speech_to_text_without_fixtures_always_fails() -> None:
    fake = FakeSpeechToText()
    result = asyncio.run(fake.transcribe(SpeechInput(audio=b"anything")))
    assert result.success is False
    assert result.error is not None


def test_fake_speech_to_text_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError, match="confidence"):
        FakeSpeechToText(default_confidence=2.0)


def test_fake_text_to_speech_satisfies_interface() -> None:
    fake = FakeTextToSpeech()
    assert isinstance(fake, TextToSpeech)
    assert fake.name == "fake-text-to-speech"
    assert fake.description


def test_fake_text_to_speech_deterministic_result() -> None:
    fake = FakeTextToSpeech()
    result = asyncio.run(fake.synthesize(TextToSpeechRequest(text="hello there")))
    assert result.success is True
    assert result.error is None
    assert result.audio is not None
    assert result.audio.content == b"hello there"
    assert result.audio.format == "text"
    assert result.audio.sample_rate == 16000
    assert result.duration == timedelta(seconds=1.0)


def test_fake_text_to_speech_is_repeatable() -> None:
    fake = FakeTextToSpeech()
    first = asyncio.run(fake.synthesize(TextToSpeechRequest(text="repeat me")))
    second = asyncio.run(fake.synthesize(TextToSpeechRequest(text="repeat me")))
    assert first.audio is not None
    assert second.audio is not None
    assert first.audio.content == second.audio.content
    assert first.duration == second.duration


def test_fake_text_to_speech_custom_config() -> None:
    fake = FakeTextToSpeech(
        language="hi",
        voice="sample-hindi",
        sample_rate=8000,
        duration=timedelta(seconds=2.0),
    )
    result = asyncio.run(fake.synthesize(TextToSpeechRequest(text="namaste")))
    assert result.success is True
    assert result.audio is not None
    assert result.audio.sample_rate == 8000
    assert result.duration == timedelta(seconds=2.0)


def test_fake_text_to_speech_honors_language_request() -> None:
    fake = FakeTextToSpeech(language="en")
    result = asyncio.run(fake.synthesize(TextToSpeechRequest(text="namaste", language="hi")))
    assert result.success is True
    assert result.audio is not None
    assert result.duration == timedelta(seconds=1.0)


def test_fake_text_to_speech_rejects_invalid_sample_rate() -> None:
    with pytest.raises(ValueError, match="sample_rate"):
        FakeTextToSpeech(sample_rate=0)


def test_dependency_injection_compatibility() -> None:
    stt: SpeechToText = FakeSpeechToText(fixtures=FIXTURES)
    tts: TextToSpeech = FakeTextToSpeech()
    assistant = SpeechAssistant(stt=stt, tts=tts)

    transcription, speech = asyncio.run(
        assistant.handle(audio=b"hello there", reply="just a moment")
    )

    assert isinstance(transcription, SpeechToTextResult)
    assert transcription.success is True
    assert transcription.text == "Hello there, how can I help?"

    assert isinstance(speech, TextToSpeechResult)
    assert speech.success is True
    assert speech.audio is not None
    assert speech.audio.content == b"just a moment"


def test_dependency_injection_rejects_unrecognized_audio() -> None:
    stt: SpeechToText = FakeSpeechToText(fixtures=FIXTURES)
    tts: TextToSpeech = FakeTextToSpeech()
    assistant = SpeechAssistant(stt=stt, tts=tts)

    transcription, speech = asyncio.run(assistant.handle(audio=b"gibberish", reply="unclear"))

    assert transcription.success is False
    assert speech.success is True


def test_fake_speech_to_text_can_fail_on_demand() -> None:
    fake = FakeSpeechToText(fixtures=FIXTURES, fail=True)
    result = asyncio.run(fake.transcribe(SpeechInput(audio=b"hello there")))
    assert result.success is False
    assert result.error == "simulated speech-to-text failure"


def test_fake_speech_to_text_can_raise_configured_error() -> None:
    fake = FakeSpeechToText(fixtures=FIXTURES, raise_error=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(fake.transcribe(SpeechInput(audio=b"hello there")))


def test_fake_speech_to_text_records_requests() -> None:
    fake = FakeSpeechToText(fixtures=FIXTURES)
    asyncio.run(fake.transcribe(SpeechInput(audio=b"hello there")))
    assert len(fake.requests) == 1
    assert fake.requests[0].audio == b"hello there"


def test_fake_text_to_speech_can_fail_on_demand() -> None:
    fake = FakeTextToSpeech(fail=True)
    result = asyncio.run(fake.synthesize(TextToSpeechRequest(text="hello")))
    assert result.success is False
    assert result.error == "simulated text-to-speech failure"


def test_fake_text_to_speech_can_raise_configured_error() -> None:
    fake = FakeTextToSpeech(raise_error=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(fake.synthesize(TextToSpeechRequest(text="hello")))


def test_fake_text_to_speech_records_requests() -> None:
    fake = FakeTextToSpeech()
    asyncio.run(fake.synthesize(TextToSpeechRequest(text="namaste", language="hi")))
    asyncio.run(fake.synthesize(TextToSpeechRequest(text="bye")))
    assert len(fake.requests) == 2
    assert fake.requests[0].language == "hi"
    assert fake.requests[1].text == "bye"


def test_fake_language_detector_satisfies_interface() -> None:
    fake = FakeLanguageDetector(
        fixtures={"hello": LanguageDetectionResult.detected(LanguageLabel.ENGLISH, confidence=0.9)}
    )
    assert isinstance(fake, LanguageDetector)
    assert fake.name == "fake-language-detector"
    assert fake.description


def test_fake_language_detector_uses_fixture() -> None:
    fake = FakeLanguageDetector(
        fixtures={
            "hello there": LanguageDetectionResult.detected(LanguageLabel.ENGLISH, confidence=0.9)
        }
    )
    result = asyncio.run(fake.detect("hello there"))
    assert result.label is LanguageLabel.ENGLISH
    assert result.confidence == 0.9


def test_fake_language_detector_defaults_to_unknown() -> None:
    fake = FakeLanguageDetector()
    result = asyncio.run(fake.detect("unseen text"))
    assert result.label is LanguageLabel.UNKNOWN
    assert result.confidence is None


def test_fake_language_detector_respects_custom_default() -> None:
    fake = FakeLanguageDetector(
        default=LanguageDetectionResult.mixed(LanguageLabel.HINDI, LanguageLabel.ENGLISH)
    )
    result = asyncio.run(fake.detect("anything"))
    assert result.label is LanguageLabel.MIXED


def test_fake_language_detector_can_raise_configured_error() -> None:
    fake = FakeLanguageDetector(raise_error=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(fake.detect("hello"))


def test_fake_ai_model_satisfies_interface() -> None:
    fake = FakeAIModel()
    assert isinstance(fake, AIModel)
    assert fake.name == "fake-ai-model"
    assert fake.description


def test_fake_ai_model_returns_default_reply() -> None:
    fake = FakeAIModel()
    result = asyncio.run(fake.chat([AIMessage(role="user", content="hi")]))
    assert result.success is True
    assert result.content == "Understood."
    assert result.model_name == "fake-ai-model"


def test_fake_ai_model_cycles_replies() -> None:
    fake = FakeAIModel(replies=["first", "second"])
    first = asyncio.run(fake.chat([AIMessage(role="user", content="a")]))
    second = asyncio.run(fake.chat([AIMessage(role="user", content="b")]))
    assert first.content == "first"
    assert second.content == "second"


def test_fake_ai_model_records_chat_requests() -> None:
    fake = FakeAIModel()
    asyncio.run(fake.chat([AIMessage(role="user", content="hello")]))
    asyncio.run(fake.chat([AIMessage(role="system", content="ctx")]))
    assert len(fake.chat_requests) == 2
    assert fake.chat_requests[0][0].content == "hello"
    assert fake.chat_requests[1][0].content == "ctx"


def test_fake_ai_model_can_respond_fail() -> None:
    fake = FakeAIModel(respond_fail=True)
    result = asyncio.run(fake.chat([AIMessage(role="user", content="hi")]))
    assert result.success is False
    assert result.error == "simulated AI failure"
    assert isinstance(result, AIResponse)


def test_fake_ai_model_can_raise_configured_error() -> None:
    fake = FakeAIModel(raise_error=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(fake.chat([AIMessage(role="user", content="hi")]))
