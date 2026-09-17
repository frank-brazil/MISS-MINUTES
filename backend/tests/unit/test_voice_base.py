import asyncio
from datetime import timedelta

import pytest
from app.voice.base import (
    AudioData,
    SpeechError,
    SpeechInput,
    SpeechToText,
    SpeechToTextResult,
    TextToSpeech,
    TextToSpeechRequest,
    TextToSpeechResult,
)
from pydantic import ValidationError


class SampleSpeechToText(SpeechToText):
    name = "sample-speech-to-text"
    description = "A sample speech-to-text implementation for tests."

    async def transcribe(self, speech: SpeechInput) -> SpeechToTextResult:
        return SpeechToTextResult.ok(text=speech.audio.decode("utf-8"))


class SampleTextToSpeech(TextToSpeech):
    name = "sample-text-to-speech"
    description = "A sample text-to-speech implementation for tests."

    async def synthesize(self, request: TextToSpeechRequest) -> TextToSpeechResult:
        audio = AudioData(content=request.text.encode("utf-8"), format="text")
        return TextToSpeechResult.ok(audio=audio)


def test_speech_to_text_is_abstract() -> None:
    with pytest.raises(TypeError):
        SpeechToText()


def test_text_to_speech_is_abstract() -> None:
    with pytest.raises(TypeError):
        TextToSpeech()


def test_speech_to_text_requires_metadata() -> None:
    with pytest.raises(TypeError, match="name"):

        class MissingMetadata(SpeechToText):
            async def transcribe(self, speech: SpeechInput) -> SpeechToTextResult:
                return SpeechToTextResult.ok(text="x")


def test_text_to_speech_requires_metadata() -> None:
    with pytest.raises(TypeError, match="description"):

        class MissingDescription(TextToSpeech):
            name = "missing-description"

            async def synthesize(self, request: TextToSpeechRequest) -> TextToSpeechResult:
                return TextToSpeechResult.ok()


def test_required_speech_metadata() -> None:
    assert SampleSpeechToText.name == "sample-speech-to-text"
    assert SampleSpeechToText.description


def test_required_speech_metadata_tts() -> None:
    assert SampleTextToSpeech.name == "sample-text-to-speech"
    assert SampleTextToSpeech.description


def test_concrete_samples_satisfy_interfaces() -> None:
    stt = SampleSpeechToText()
    tts = SampleTextToSpeech()
    assert isinstance(stt, SpeechToText)
    assert isinstance(tts, TextToSpeech)
    transcription = asyncio.run(stt.transcribe(SpeechInput(audio=b"hello")))
    assert transcription.text == "hello"
    synthesis = asyncio.run(tts.synthesize(TextToSpeechRequest(text="hello")))
    assert synthesis.audio is not None
    assert synthesis.audio.content == b"hello"


def test_speech_error_is_exception() -> None:
    error = SpeechError("boom")
    assert isinstance(error, Exception)
    assert str(error) == "boom"


def test_speech_input_model_fields() -> None:
    speech = SpeechInput(audio=b"abc", format="wav", sample_rate=16000, language="en")
    assert speech.audio == b"abc"
    assert speech.format == "wav"
    assert speech.sample_rate == 16000
    assert speech.language == "en"


def test_speech_input_defaults() -> None:
    speech = SpeechInput(audio=b"abc")
    assert speech.format == "wav"
    assert speech.sample_rate is None
    assert speech.language is None


def test_speech_input_rejects_empty_audio() -> None:
    with pytest.raises(ValidationError):
        SpeechInput(audio=b"")


def test_speech_input_rejects_blank_format() -> None:
    with pytest.raises(ValidationError):
        SpeechInput(audio=b"abc", format="  ")


def test_speech_input_rejects_blank_language() -> None:
    with pytest.raises(ValidationError):
        SpeechInput(audio=b"abc", language="  ")


def test_speech_input_rejects_invalid_sample_rate() -> None:
    with pytest.raises(ValidationError):
        SpeechInput(audio=b"abc", sample_rate=0)


def test_audio_data_model_fields() -> None:
    audio = AudioData(content=b"data", format="wav", sample_rate=44100)
    assert audio.content == b"data"
    assert audio.format == "wav"
    assert audio.sample_rate == 44100


def test_audio_data_rejects_empty_content() -> None:
    with pytest.raises(ValidationError):
        AudioData(content=b"", format="wav")


def test_audio_data_rejects_blank_format() -> None:
    with pytest.raises(ValidationError):
        AudioData(content=b"data", format="   ")


def test_successful_speech_to_text_result() -> None:
    result = SpeechToTextResult.ok(
        text="please open VS Code",
        language="en",
        confidence=0.95,
    )
    assert isinstance(result, SpeechToTextResult)
    assert result.success is True
    assert result.text == "please open VS Code"
    assert result.language == "en"
    assert result.confidence == 0.95
    assert result.error is None


def test_optional_language_and_confidence_default_to_none() -> None:
    result = SpeechToTextResult.ok(text="hi")
    assert result.language is None
    assert result.confidence is None
    assert result.success is True


def test_failed_speech_to_text_result() -> None:
    result = SpeechToTextResult.fail(error="no audio detected")
    assert isinstance(result, SpeechToTextResult)
    assert result.success is False
    assert result.error == "no audio detected"
    assert result.text is None
    assert result.language is None
    assert result.confidence is None


def test_speech_to_text_result_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValidationError):
        SpeechToTextResult.ok(text="x", confidence=1.5)
    with pytest.raises(ValidationError):
        SpeechToTextResult.ok(text="x", confidence=-0.1)


def test_text_to_speech_request_model_fields() -> None:
    request = TextToSpeechRequest(text="hello", language="hi", voice="sample-voice")
    assert request.text == "hello"
    assert request.language == "hi"
    assert request.voice == "sample-voice"


def test_text_to_speech_request_defaults() -> None:
    request = TextToSpeechRequest(text="hello")
    assert request.language is None
    assert request.voice is None


def test_text_to_speech_request_rejects_blank_text() -> None:
    with pytest.raises(ValidationError):
        TextToSpeechRequest(text="")
    with pytest.raises(ValidationError):
        TextToSpeechRequest(text="   ")


def test_text_to_speech_request_rejects_blank_language() -> None:
    with pytest.raises(ValidationError):
        TextToSpeechRequest(text="hello", language="  ")


def test_text_to_speech_request_rejects_blank_voice() -> None:
    with pytest.raises(ValidationError):
        TextToSpeechRequest(text="hello", voice="  ")


def test_successful_text_to_speech_result() -> None:
    audio = AudioData(content=b"hello", format="wav")
    result = TextToSpeechResult.ok(
        audio=audio,
        duration=timedelta(seconds=2.5),
    )
    assert isinstance(result, TextToSpeechResult)
    assert result.success is True
    assert result.audio is audio
    assert result.audio.content == b"hello"
    assert result.duration == timedelta(seconds=2.5)
    assert result.audio_ref is None
    assert result.error is None


def test_successful_text_to_speech_result_with_audio_ref() -> None:
    result = TextToSpeechResult.ok(
        audio_ref="provider://audio/ref/123",
        duration=timedelta(seconds=1.0),
    )
    assert result.success is True
    assert result.audio is None
    assert result.audio_ref == "provider://audio/ref/123"
    assert result.duration == timedelta(seconds=1.0)


def test_failed_text_to_speech_result() -> None:
    result = TextToSpeechResult.fail(error="synthesis engine unavailable")
    assert isinstance(result, TextToSpeechResult)
    assert result.success is False
    assert result.error == "synthesis engine unavailable"
    assert result.audio is None
    assert result.audio_ref is None
    assert result.duration is None


def test_speech_to_text_result_fail_via_interface() -> None:
    class AlwaysFailSTT(SpeechToText):
        name = "always-fail-stt"
        description = "Always fails."

        async def transcribe(self, speech: SpeechInput) -> SpeechToTextResult:
            return SpeechToTextResult.fail(error="simulated failure")

    result = asyncio.run(AlwaysFailSTT().transcribe(SpeechInput(audio=b"anything")))
    assert result.success is False
    assert result.error == "simulated failure"
