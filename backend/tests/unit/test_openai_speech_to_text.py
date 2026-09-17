import asyncio

import pytest
from app.providers.openai_speech_to_text import (
    OPENAI_API_KEY_ENV,
    STT_LANGUAGE_ENV,
    STT_MODEL_ENV,
    OpenAISpeechToText,
)
from app.voice.base import SpeechInput, SpeechToText, SpeechToTextResult


class FakeTranscription:
    text = "hello world"
    language = "en"
    segments: list = []


class FakeTranscriptions:
    @staticmethod
    async def create(**kwargs: object) -> FakeTranscription:
        return FakeTranscription()


class FakeAudio:
    transcriptions = FakeTranscriptions()


class FakeClient:
    audio = FakeAudio()


class ConfidentTranscription:
    text = "confident speech"
    language = "en"
    segments = [{"confidence": 0.9}, {"confidence": 0.7}]


class ConfidentTranscriptions:
    @staticmethod
    async def create(**kwargs: object) -> ConfidentTranscription:
        return ConfidentTranscription()


class ConfidentAudio:
    transcriptions = ConfidentTranscriptions()


class ConfidentClient:
    audio = ConfidentAudio()


class BlankTranscription:
    text = "   "
    language = None
    segments: list = []


class BlankTranscriptions:
    @staticmethod
    async def create(**kwargs: object) -> BlankTranscription:
        return BlankTranscription()


class BlankAudio:
    transcriptions = BlankTranscriptions()


class BlankClient:
    audio = BlankAudio()


class RaisingTranscriptions:
    @staticmethod
    async def create(**kwargs: object) -> FakeTranscription:
        raise RuntimeError("invalid media data")


class RaisingAudio:
    transcriptions = RaisingTranscriptions()


class RaisingClient:
    audio = RaisingAudio()


class RecordingTranscriptions:
    def __init__(self) -> None:
        self.last_kwargs: dict = {}

    async def create(self, **kwargs: object) -> FakeTranscription:
        self.last_kwargs = dict(kwargs)
        return FakeTranscription()


class RecordingAudio:
    def __init__(self) -> None:
        self.transcriptions = RecordingTranscriptions()


class RecordingClient:
    def __init__(self) -> None:
        self.audio = RecordingAudio()


def test_provider_satisfies_speech_to_text_interface() -> None:
    provider = OpenAISpeechToText()
    assert isinstance(provider, SpeechToText)
    assert provider.name == "openai-speech-to-text"
    assert provider.description


def test_provider_reads_env_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENAI_API_KEY_ENV, "sk-env-key")
    monkeypatch.setenv(STT_MODEL_ENV, "gpt-4o-mini-transcribe")
    client = RecordingClient()
    provider = OpenAISpeechToText(client=client)
    assert provider.model == "gpt-4o-mini-transcribe"
    result = asyncio.run(provider.transcribe(SpeechInput(audio=b"x", format="wav")))
    assert result.success is True
    assert result.text == "hello world"
    assert client.audio.transcriptions.last_kwargs["model"] == "gpt-4o-mini-transcribe"


def test_explicit_config_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STT_MODEL_ENV, "gpt-4o-transcribe")
    client = RecordingClient()
    provider = OpenAISpeechToText(
        api_key="sk-explicit",
        model="whisper-1",
        client=client,
    )
    assert provider.model == "whisper-1"


def test_default_model_when_env_and_arg_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(STT_MODEL_ENV, raising=False)
    client = RecordingClient()
    provider = OpenAISpeechToText(api_key="sk-test", client=client)
    assert provider.model == "whisper-1"
    asyncio.run(provider.transcribe(SpeechInput(audio=b"x", format="wav")))
    assert client.audio.transcriptions.last_kwargs["model"] == "whisper-1"


def test_missing_api_key_returns_controlled_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(OPENAI_API_KEY_ENV, raising=False)
    provider = OpenAISpeechToText()
    result = asyncio.run(provider.transcribe(SpeechInput(audio=b"x", format="wav")))
    assert isinstance(result, SpeechToTextResult)
    assert result.success is False
    assert "API key" in (result.error or "")
    assert result.text is None


def test_blank_api_key_treated_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(OPENAI_API_KEY_ENV, raising=False)
    provider = OpenAISpeechToText(api_key="   ")
    result = asyncio.run(provider.transcribe(SpeechInput(audio=b"x", format="wav")))
    assert result.success is False


def test_successful_transcription_with_mocked_client() -> None:
    provider = OpenAISpeechToText(api_key="sk-test", client=FakeClient())
    result = asyncio.run(provider.transcribe(SpeechInput(audio=b"x", format="wav")))
    assert result.success is True
    assert result.text == "hello world"
    assert result.language == "en"
    assert result.confidence is None
    assert result.error is None


def test_language_hint_forwarded_to_api() -> None:
    client = RecordingClient()
    provider = OpenAISpeechToText(api_key="sk-test", client=client)
    result = asyncio.run(provider.transcribe(SpeechInput(audio=b"x", format="wav", language="hi")))
    assert result.success is True
    sent = client.audio.transcriptions.last_kwargs
    assert sent["model"] == "whisper-1"
    assert sent["response_format"] == "verbose_json"
    assert sent["language"] == "hi"
    filename, payload = sent["file"]
    assert filename == "speech.wav"
    assert payload == b"x"


def test_default_language_from_env_forwarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(STT_LANGUAGE_ENV, "hi")
    client = RecordingClient()
    provider = OpenAISpeechToText(api_key="sk-test", client=client)
    result = asyncio.run(provider.transcribe(SpeechInput(audio=b"x", format="wav")))
    assert result.success is True
    assert client.audio.transcriptions.last_kwargs["language"] == "hi"


def test_language_omitted_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(STT_LANGUAGE_ENV, raising=False)
    client = RecordingClient()
    provider = OpenAISpeechToText(api_key="sk-test", client=client)
    result = asyncio.run(provider.transcribe(SpeechInput(audio=b"x", format="wav")))
    assert result.success is True
    assert "language" not in client.audio.transcriptions.last_kwargs


def test_detected_language_preserved() -> None:
    provider = OpenAISpeechToText(api_key="sk-test", client=FakeClient())
    result = asyncio.run(provider.transcribe(SpeechInput(audio=b"x", format="wav")))
    assert result.language == "en"


def test_confidence_preserved_when_provider_supplies_it() -> None:
    provider = OpenAISpeechToText(api_key="sk-test", client=ConfidentClient())
    result = asyncio.run(provider.transcribe(SpeechInput(audio=b"x", format="wav")))
    assert result.success is True
    assert result.confidence == 0.8


def test_blank_transcription_not_invented() -> None:
    provider = OpenAISpeechToText(api_key="sk-test", client=BlankClient())
    result = asyncio.run(provider.transcribe(SpeechInput(audio=b"x", format="wav")))
    assert result.success is False
    assert "no transcription text" in (result.error or "")
    assert result.text is None


def test_provider_failure_with_mocked_client() -> None:
    provider = OpenAISpeechToText(api_key="sk-test", client=RaisingClient())
    result = asyncio.run(provider.transcribe(SpeechInput(audio=b"x", format="wav")))
    assert result.success is False
    assert result.error == "OpenAI speech-to-text provider call failed"
    assert result.text is None


def test_corrupt_audio_failure() -> None:
    provider = OpenAISpeechToText(api_key="sk-test", client=RaisingClient())
    result = asyncio.run(
        provider.transcribe(SpeechInput(audio=b"\x00not real audio", format="wav"))
    )
    assert result.success is False
    assert result.error is not None


def test_unsupported_format_rejected_without_client_call() -> None:
    client = RecordingClient()
    provider = OpenAISpeechToText(api_key="sk-test", client=client)
    result = asyncio.run(provider.transcribe(SpeechInput(audio=b"x", format="txt")))
    assert result.success is False
    assert "Unsupported audio format" in (result.error or "")
    assert client.audio.transcriptions.last_kwargs == {}


def test_does_not_log_transcribed_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO")
    provider = OpenAISpeechToText(api_key="sk-test", client=FakeClient())
    result = asyncio.run(provider.transcribe(SpeechInput(audio=b"x", format="wav")))
    assert result.success is True
    assert "hello world" not in caplog.text
