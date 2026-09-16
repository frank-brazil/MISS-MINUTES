import logging
import os

from openai import AsyncOpenAI

from app.voice.base import (
    AudioData,
    TextToSpeech,
    TextToSpeechRequest,
    TextToSpeechResult,
)

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
TTS_MODEL_ENV = "MISSMINUTES_TTS_MODEL"
TTS_VOICE_ENV = "MISSMINUTES_TTS_VOICE"
TTS_FORMAT_ENV = "MISSMINUTES_TTS_FORMAT"

DEFAULT_TTS_MODEL = "tts-1"
DEFAULT_TTS_VOICE = "alloy"
DEFAULT_TTS_FORMAT = "mp3"

# Verbose formats accepted by the OpenAI audio speech API.
SUPPORTED_TTS_FORMATS = frozenset({"mp3", "opus", "aac", "flac", "wav", "pcm"})


def _resolve_str(value: str | None, env_name: str, default: str) -> str:
    return (value or os.getenv(env_name) or default).strip() or default


class OpenAITextToSpeech(TextToSpeech):
    """OpenAI text-to-speech synthesis provider.

    Uses the existing ``openai`` SDK dependency; no extra packages required.
    Configuration is read from environment variables (or explicit constructor
    arguments) and an API client may be injected for testing.
    """

    name = "openai-text-to-speech"
    description = "OpenAI text-to-speech provider."

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        voice: str | None = None,
        response_format: str | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._logger = logging.getLogger(__name__)
        self._api_key = self._resolve_api_key(api_key)
        self._model = _resolve_str(model, TTS_MODEL_ENV, DEFAULT_TTS_MODEL)
        self._voice = _resolve_str(voice, TTS_VOICE_ENV, DEFAULT_TTS_VOICE)
        self._response_format = _resolve_str(
            response_format, TTS_FORMAT_ENV, DEFAULT_TTS_FORMAT
        )
        self._client = client

    @property
    def model(self) -> str:
        return self._model

    def _resolve_api_key(self, api_key: str | None) -> str | None:
        if api_key is not None:
            return api_key.strip() or None
        return os.getenv(OPENAI_API_KEY_ENV) or None

    async def synthesize(self, request: TextToSpeechRequest) -> TextToSpeechResult:
        if self._response_format not in SUPPORTED_TTS_FORMATS:
            self._logger.warning(
                "Unsupported text-to-speech response format '%s'",
                self._response_format,
            )
            return TextToSpeechResult.fail(
                f"Unsupported text-to-speech response format: "
                f"{self._response_format}"
            )

        if self._client is None:
            if not self._api_key:
                self._logger.error(
                    "OpenAI text-to-speech is not configured: %s is "
                    "missing or empty",
                    OPENAI_API_KEY_ENV,
                )
                return TextToSpeechResult.fail(
                    "OpenAI text-to-speech is not configured: API key is missing"
                )
            self._client = AsyncOpenAI(api_key=self._api_key)

        voice = (request.voice or self._voice).strip()

        try:
            response = await self._client.audio.speech.create(
                model=self._model,
                voice=voice,
                input=request.text,
                response_format=self._response_format,
            )
        except Exception as exc:
            self._logger.error(
                "OpenAI speech synthesis failed: %s", type(exc).__name__
            )
            return TextToSpeechResult.fail(
                "OpenAI text-to-speech provider call failed"
            )

        audio_bytes = await self._read_audio_bytes(response)
        if not audio_bytes:
            self._logger.warning(
                "OpenAI speech synthesis returned no audio content"
            )
            return TextToSpeechResult.fail(
                "OpenAI provider returned no audio content"
            )

        self._logger.info(
            "Synthesized speech: success=%s characters=%d format=%s voice='%s'",
            True,
            len(request.text),
            self._response_format,
            voice,
        )
        return TextToSpeechResult.ok(
            audio=AudioData(content=audio_bytes, format=self._response_format),
        )

    @staticmethod
    async def _read_audio_bytes(response: object) -> bytes:
        aread = getattr(response, "aread", None)
        if callable(aread):
            data = await aread()
            if isinstance(data, bytes):
                return data
        content = getattr(response, "content", None)
        if isinstance(content, bytes):
            return content
        return b""
