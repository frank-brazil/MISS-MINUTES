from abc import ABC, abstractmethod
from datetime import timedelta
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator


class SpeechError(Exception):
    """Base exception for speech subsystem failures.

    Reserved for provider-level problems. Invalid input is rejected earlier
    through model validation.
    """


class AudioData(BaseModel):
    """Encoded audio bytes plus descriptive metadata."""

    content: bytes = Field(min_length=1)
    format: str
    sample_rate: int | None = None

    @field_validator("format")
    @classmethod
    def _format_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("format must not be blank")
        return value

    @field_validator("sample_rate")
    @classmethod
    def _sample_rate_positive(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("sample_rate must be a positive number")
        return value


class SpeechInput(BaseModel):
    """Speech to transcribe.

    # ADD HARDWARE HERE: MICROPHONE (audio input device)
    """

    audio: bytes = Field(min_length=1)
    format: str = "wav"
    sample_rate: int | None = None
    language: str | None = None

    @field_validator("format")
    @classmethod
    def _format_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("format must not be blank")
        return value

    @field_validator("language")
    @classmethod
    def _language_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("language must not be blank")
        return value

    @field_validator("sample_rate")
    @classmethod
    def _sample_rate_positive(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("sample_rate must be a positive number")
        return value


class SpeechToTextResult(BaseModel):
    """Outcome of a speech-to-text transcription attempt."""

    success: bool
    text: str | None = None
    language: str | None = None
    confidence: float | None = None
    error: str | None = None

    @classmethod
    def ok(
        cls,
        text: str,
        *,
        language: str | None = None,
        confidence: float | None = None,
    ) -> "SpeechToTextResult":
        return cls(success=True, text=text, language=language, confidence=confidence)

    @classmethod
    def fail(cls, error: str) -> "SpeechToTextResult":
        return cls(success=False, error=error)

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value


class TextToSpeechRequest(BaseModel):
    """Text to synthesize into speech.

    # ADD HARDWARE HERE: SPEAKER (audio output device)
    """

    text: str
    language: str | None = None
    voice: str | None = None

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value

    @field_validator("language", "voice")
    @classmethod
    def _optional_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value


class TextToSpeechResult(BaseModel):
    """Outcome of a text-to-speech synthesis attempt.

    Exactly one of ``audio`` (inline data representation) and ``audio_ref``
    (reference to generated audio) is the primary payload; a provider may
    provide both.
    """

    success: bool
    audio: AudioData | None = None
    audio_ref: str | None = None
    duration: timedelta | None = None
    error: str | None = None

    @classmethod
    def ok(
        cls,
        *,
        audio: AudioData | None = None,
        audio_ref: str | None = None,
        duration: timedelta | None = None,
    ) -> "TextToSpeechResult":
        return cls(
            success=True,
            audio=audio,
            audio_ref=audio_ref,
            duration=duration,
        )

    @classmethod
    def fail(cls, error: str) -> "TextToSpeechResult":
        return cls(success=False, error=error)


class SpeechToText(ABC):
    name: ClassVar[str]
    description: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        missing = [
            attribute for attribute in ("name", "description") if not hasattr(cls, attribute)
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} must define required attribute(s): {', '.join(missing)}"
            )

    @abstractmethod
    async def transcribe(self, speech: SpeechInput) -> SpeechToTextResult:
        raise NotImplementedError


class TextToSpeech(ABC):
    name: ClassVar[str]
    description: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        missing = [
            attribute for attribute in ("name", "description") if not hasattr(cls, attribute)
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} must define required attribute(s): {', '.join(missing)}"
            )

    @abstractmethod
    async def synthesize(self, request: TextToSpeechRequest) -> TextToSpeechResult:
        raise NotImplementedError
