import asyncio

import pytest
from app.providers.openai_text_to_speech import (
    OPENAI_API_KEY_ENV,
    TTS_FORMAT_ENV,
    TTS_MODEL_ENV,
    TTS_VOICE_ENV,
    OpenAITextToSpeech,
)
from app.voice.base import (
    TextToSpeech,
    TextToSpeechRequest,
    TextToSpeechResult,
)


class FakeSpeechContent:
    content = b"fake mp3 bytes"


class FakeSpeech:
    @staticmethod
    async def create(**kwargs: object) -> FakeSpeechContent:
        return FakeSpeechContent()


class FakeAudio:
    speech = FakeSpeech()


class FakeClient:
    audio = FakeAudio()


class AreadSpeechContent:
    async def aread(self) -> bytes:
        return b"streamed audio bytes"


class AreadSpeech:
    @staticmethod
    async def create(**kwargs: object) -> AreadSpeechContent:
        return AreadSpeechContent()


class AreadAudio:
    speech = AreadSpeech()


class AreadClient:
    audio = AreadAudio()


class EmptySpeechContent:
    content = b""


class EmptySpeech:
    @staticmethod
    async def create(**kwargs: object) -> EmptySpeechContent:
        return EmptySpeechContent()


class EmptyAudio:
    speech = EmptySpeech()


class EmptyClient:
    audio = EmptyAudio()


class RaisingSpeech:
    @staticmethod
    async def create(**kwargs: object) -> FakeSpeechContent:
        raise RuntimeError("synthesis engine unavailable")


class RaisingAudio:
    speech = RaisingSpeech()


class RaisingClient:
    audio = RaisingAudio()


class RecordingSpeech:
    def __init__(self) -> None:
        self.last_kwargs: dict = {}

    async def create(self, **kwargs: object) -> FakeSpeechContent:
        self.last_kwargs = dict(kwargs)
        return FakeSpeechContent()


class RecordingAudio:
    def __init__(self) -> None:
        self.speech = RecordingSpeech()


class RecordingClient:
    def __init__(self) -> None:
        self.audio = RecordingAudio()


def test_provider_satisfies_text_to_speech_interface() -> None:
    provider = OpenAITextToSpeech()
    assert isinstance(provider, TextToSpeech)
    assert provider.name == "openai-text-to-speech"
    assert provider.description


def test_provider_reads_env_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENAI_API_KEY_ENV, "sk-env-key")
    monkeypatch.setenv(TTS_MODEL_ENV, "gpt-4o-mini-tts")
    monkeypatch.setenv(TTS_VOICE_ENV, "nova")
    monkeypatch.setenv(TTS_FORMAT_ENV, "wav")
    client = RecordingClient()
    provider = OpenAITextToSpeech(client=client)
    assert provider.model == "gpt-4o-mini-tts"
    result = asyncio.run(provider.synthesize(TextToSpeechRequest(text="hello")))
    assert result.success is True
    sent = client.audio.speech.last_kwargs
    assert sent["model"] == "gpt-4o-mini-tts"
    assert sent["voice"] == "nova"
    assert sent["response_format"] == "wav"


def test_explicit_config_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TTS_VOICE_ENV, "nova")
    client = RecordingClient()
    provider = OpenAITextToSpeech(
        api_key="sk-explicit",
        model="tts-1-hd",
        voice="echo",
        response_format="wav",
        client=client,
    )
    assert provider.model == "tts-1-hd"
    asyncio.run(provider.synthesize(TextToSpeechRequest(text="hello")))
    sent = client.audio.speech.last_kwargs
    assert sent["model"] == "tts-1-hd"
    assert sent["voice"] == "echo"
    assert sent["response_format"] == "wav"


def test_defaults_when_env_and_args_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(TTS_MODEL_ENV, raising=False)
    monkeypatch.delenv(TTS_VOICE_ENV, raising=False)
    monkeypatch.delenv(TTS_FORMAT_ENV, raising=False)
    client = RecordingClient()
    provider = OpenAITextToSpeech(api_key="sk-test", client=client)
    assert provider.model == "tts-1"
    asyncio.run(provider.synthesize(TextToSpeechRequest(text="hello")))
    sent = client.audio.speech.last_kwargs
    assert sent["model"] == "tts-1"
    assert sent["voice"] == "alloy"
    assert sent["response_format"] == "mp3"


def test_missing_api_key_returns_controlled_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(OPENAI_API_KEY_ENV, raising=False)
    provider = OpenAITextToSpeech()
    result = asyncio.run(provider.synthesize(TextToSpeechRequest(text="hello")))
    assert isinstance(result, TextToSpeechResult)
    assert result.success is False
    assert "API key" in (result.error or "")
    assert result.audio is None


def test_blank_api_key_treated_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(OPENAI_API_KEY_ENV, raising=False)
    provider = OpenAITextToSpeech(api_key="   ")
    result = asyncio.run(provider.synthesize(TextToSpeechRequest(text="hello")))
    assert result.success is False


def test_successful_synthesis_with_mocked_client() -> None:
    provider = OpenAITextToSpeech(api_key="sk-test", client=FakeClient())
    result = asyncio.run(provider.synthesize(TextToSpeechRequest(text="hello")))
    assert result.success is True
    assert result.error is None
    assert result.audio is not None
    assert result.audio.content == b"fake mp3 bytes"
    assert result.audio.format == "mp3"
    assert result.audio_ref is None
    assert result.duration is None


def test_synthesis_reads_async_payload() -> None:
    provider = OpenAITextToSpeech(api_key="sk-test", client=AreadClient())
    result = asyncio.run(provider.synthesize(TextToSpeechRequest(text="hello")))
    assert result.success is True
    assert result.audio is not None
    assert result.audio.content == b"streamed audio bytes"


def test_request_voice_overrides_default_voice() -> None:
    client = RecordingClient()
    provider = OpenAITextToSpeech(api_key="sk-test", client=client)
    result = asyncio.run(provider.synthesize(TextToSpeechRequest(text="hello", voice="nova")))
    assert result.success is True
    assert client.audio.speech.last_kwargs["voice"] == "nova"


def test_default_voice_used_when_request_has_none() -> None:
    client = RecordingClient()
    provider = OpenAITextToSpeech(api_key="sk-test", client=client)
    result = asyncio.run(provider.synthesize(TextToSpeechRequest(text="hello")))
    assert result.success is True
    assert client.audio.speech.last_kwargs["voice"] == "alloy"


def test_input_text_forwarded_to_api() -> None:
    client = RecordingClient()
    provider = OpenAITextToSpeech(api_key="sk-test", client=client)
    result = asyncio.run(provider.synthesize(TextToSpeechRequest(text="greetings")))
    assert result.success is True
    assert client.audio.speech.last_kwargs["input"] == "greetings"


def test_empty_audio_from_provider_not_invented() -> None:
    provider = OpenAITextToSpeech(api_key="sk-test", client=EmptyClient())
    result = asyncio.run(provider.synthesize(TextToSpeechRequest(text="hello")))
    assert result.success is False
    assert "no audio content" in (result.error or "")
    assert result.audio is None


def test_provider_failure_with_mocked_client() -> None:
    provider = OpenAITextToSpeech(api_key="sk-test", client=RaisingClient())
    result = asyncio.run(provider.synthesize(TextToSpeechRequest(text="hello")))
    assert result.success is False
    assert result.error == "OpenAI text-to-speech provider call failed"
    assert result.audio is None


def test_unsupported_response_format_rejected_without_client_call() -> None:
    client = RecordingClient()
    provider = OpenAITextToSpeech(
        api_key="sk-test",
        response_format="mp4",
        client=client,
    )
    result = asyncio.run(provider.synthesize(TextToSpeechRequest(text="hello")))
    assert result.success is False
    assert "Unsupported" in (result.error or "")
    assert client.audio.speech.last_kwargs == {}


def test_does_not_log_input_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO")
    provider = OpenAITextToSpeech(api_key="sk-test", client=FakeClient())
    result = asyncio.run(provider.synthesize(TextToSpeechRequest(text="secret greeting")))
    assert result.success is True
    assert "secret greeting" not in caplog.text
    assert "fake mp3 bytes" not in caplog.text
