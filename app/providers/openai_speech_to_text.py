import logging
import os

from openai import AsyncOpenAI

from app.voice.base import SpeechInput, SpeechToText, SpeechToTextResult

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
STT_MODEL_ENV = "MISSMINUTES_STT_MODEL"
STT_LANGUAGE_ENV = "MISSMINUTES_STT_LANGUAGE"

DEFAULT_STT_MODEL = "whisper-1"

# Formats accepted for uploaded files by the OpenAI audio transcription API.
SUPPORTED_AUDIO_FORMATS = frozenset(
    {"flac", "m4a", "mp3", "mp4", "mpeg", "mpga", "ogg", "wav", "webm"}
)


class OpenAISpeechToText(SpeechToText):
    """OpenAI Whisper audio transcription provider.

    Uses the existing ``openai`` SDK dependency; no extra packages required.
    Configuration is read from environment variables (or explicit constructor
    arguments) and an API client may be injected for testing.
    """

    name = "openai-speech-to-text"
    description = "OpenAI audio transcription (Whisper) provider."

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        language: str | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._logger = logging.getLogger(__name__)
        self._api_key = self._resolve_api_key(api_key)
        self._model = (
            model or os.getenv(STT_MODEL_ENV) or DEFAULT_STT_MODEL
        ).strip() or DEFAULT_STT_MODEL
        self._default_language = self._resolve_default_language(language)
        self._client = client

    @property
    def model(self) -> str:
        return self._model

    def _resolve_api_key(self, api_key: str | None) -> str | None:
        if api_key is not None:
            return api_key.strip() or None
        return os.getenv(OPENAI_API_KEY_ENV) or None

    def _resolve_default_language(self, language: str | None) -> str | None:
        value = language or os.getenv(STT_LANGUAGE_ENV)
        if value is None:
            return None
        return value.strip() or None

    async def transcribe(self, speech: SpeechInput) -> SpeechToTextResult:
        if speech.format not in SUPPORTED_AUDIO_FORMATS:
            self._logger.warning("Unsupported speech format '%s'", speech.format)
            return SpeechToTextResult.fail(
                f"Unsupported audio format: {speech.format}"
            )

        if self._client is None:
            if not self._api_key:
                self._logger.error(
                    "OpenAI speech-to-text is not configured: %s is "
                    "missing or empty",
                    OPENAI_API_KEY_ENV,
                )
                return SpeechToTextResult.fail(
                    "OpenAI speech-to-text is not configured: API key is missing"
                )
            self._client = AsyncOpenAI(api_key=self._api_key)

        language = speech.language or self._default_language
        kwargs: dict = {
            "model": self._model,
            "file": (f"speech.{speech.format}", speech.audio),
            "response_format": "verbose_json",
        }
        if language:
            kwargs["language"] = language

        try:
            transcription = await self._client.audio.transcriptions.create(
                **kwargs
            )
        except Exception as exc:
            self._logger.error(
                "OpenAI transcription failed: %s", type(exc).__name__
            )
            return SpeechToTextResult.fail(
                "OpenAI speech-to-text provider call failed"
            )

        return self._parse_transcription(transcription)

    def _parse_transcription(self, transcription: object) -> SpeechToTextResult:
        text = (getattr(transcription, "text", None) or "").strip()
        if not text:
            self._logger.warning(
                "OpenAI transcription returned no transcription text"
            )
            return SpeechToTextResult.fail(
                "OpenAI provider returned no transcription text"
            )

        language = getattr(transcription, "language", None)
        language = language if isinstance(language, str) and language.strip() else None
        confidence = self._extract_confidence(transcription)

        self._logger.info(
            "Transcribed speech: success=%s language=%s confidence=%s",
            True,
            language,
            confidence,
        )
        return SpeechToTextResult.ok(
            text=text,
            language=language,
            confidence=confidence,
        )

    @staticmethod
    def _extract_confidence(transcription: object) -> float | None:
        values: list[float] = []
        for segment in getattr(transcription, "segments", None) or []:
            if isinstance(segment, dict):
                raw = segment.get("confidence")
            else:
                raw = getattr(segment, "confidence", None)
            if raw is None:
                continue
            try:
                values.append(float(raw))
            except (TypeError, ValueError):
                continue
        if not values:
            return None
        return round(sum(values) / len(values), 6)
