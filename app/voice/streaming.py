"""Streaming speech boundaries.

Continuous voice sessions benefit from incremental transcription and
synthesis. These are separate, optional capabilities: existing one-shot
providers (``SpeechToText``/``TextToSpeech``) are NOT subclasses of these
interfaces, so nothing is forced to become streaming. Providers may implement
either or both boundaries without affecting the existing pipeline.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import ClassVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from app.voice.audio import AudioFrame
from app.voice.base import AudioData, SpeechError, TextToSpeechRequest


class StreamingError(SpeechError):
    """Raised when a streaming provider fails mid-stream."""


# ----------------------------------------------------------------------
# Streaming speech-to-text
# ----------------------------------------------------------------------


class StreamingSttChunk(BaseModel):
    """An incremental transcription update for a streaming session."""

    transcription_id: UUID = Field(default_factory=uuid4)
    final: bool = False
    text: str
    confidence: float | None = None

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value


class StreamingSttResult(BaseModel):
    """Finalised outcome of a streaming transcription session."""

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
    ) -> "StreamingSttResult":
        return cls(success=True, text=text, language=language, confidence=confidence)

    @classmethod
    def fail(cls, error: str) -> "StreamingSttResult":
        return cls(success=False, error=error)

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value


class StreamingSTTProvider(ABC):
    """Accepts live audio frames and produces incremental transcriptions."""

    name: ClassVar[str]
    description: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        missing = [
            attribute
            for attribute in ("name", "description")
            if not hasattr(cls, attribute)
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} must define required attribute(s): {', '.join(missing)}"
            )

    @abstractmethod
    async def start_transcription(
        self,
        *,
        language: str | None = None,
        format: str = "wav",
        transcription_id: UUID | None = None,
    ) -> UUID:
        """Start a streaming transcription session and return its id."""
        raise NotImplementedError

    @abstractmethod
    async def push_audio(
        self, transcription_id: UUID, frame: AudioFrame
    ) -> StreamingSttChunk | None:
        """Feed one frame and return an incremental chunk, if any."""
        raise NotImplementedError

    @abstractmethod
    async def finalize(
        self, transcription_id: UUID
    ) -> StreamingSttResult | None:
        """Finish a session and return the final transcription."""
        raise NotImplementedError


class FakeStreamingSTTProvider(StreamingSTTProvider):
    """Deterministic, offline streaming speech-to-text provider.

    Mirrors the one-shot fake's fixture convention: the UTF-8 decoding of the
    accumulated audio is the fixture key. ``push_audio`` returns an interim
    chunk carrying the text seen so far; ``finalize`` returns the full
    fixture transcription (or a controlled failure).
    """

    name = "fake-streaming-stt"
    description = "Deterministic streaming speech-to-text fake for offline tests."

    def __init__(
        self,
        fixtures: Mapping[str, str] | None = None,
        *,
        default_language: str = "en",
        default_confidence: float = 0.99,
        fail: bool = False,
        fail_message: str = "simulated streaming transcription failure",
        raise_error: Exception | None = None,
    ) -> None:
        if not (0.0 <= default_confidence <= 1.0):
            raise ValueError("default_confidence must be between 0 and 1")
        self._fixtures = dict(fixtures or {})
        self._default_language = default_language
        self._default_confidence = default_confidence
        self._fail = fail
        self._fail_message = fail_message
        self._raise_error = raise_error
        self._sessions: dict[UUID, list[AudioFrame]] = {}
        self._sessions_started: dict[UUID, str | None] = {}
        self._logger = logging.getLogger(__name__)

    @property
    def active_sessions(self) -> tuple[UUID, ...]:
        return tuple(self._sessions)

    async def start_transcription(
        self,
        *,
        language: str | None = None,
        format: str = "wav",
        transcription_id: UUID | None = None,
    ) -> UUID:
        session_id = transcription_id or uuid4()
        if session_id in self._sessions:
            raise ValueError(f"transcription session {session_id} already active")
        self._sessions[session_id] = []
        self._sessions_started[session_id] = language
        self._logger.info(
            "Fake streaming STT started session=%s", session_id
        )
        return session_id

    async def push_audio(
        self, transcription_id: UUID, frame: AudioFrame
    ) -> StreamingSttChunk | None:
        if self._raise_error is not None:
            self._logger.error(
                "Fake streaming STT push raising: %s",
                type(self._raise_error).__name__,
            )
            raise self._raise_error
        frames = self._sessions.get(transcription_id)
        if frames is None:
            raise ValueError(f"unknown transcription session {transcription_id}")
        frames.append(frame)
        partial = b"".join(f.content for f in frames).decode(
            "utf-8", errors="replace"
        )
        self._logger.info(
            "Fake streaming STT interim session=%s text_chars=%d",
            transcription_id,
            len(partial),
        )
        return StreamingSttChunk(
            transcription_id=transcription_id,
            final=False,
            text=partial,
        )

    async def finalize(
        self, transcription_id: UUID
    ) -> StreamingSttResult | None:
        if self._raise_error is not None:
            self._logger.error(
                "Fake streaming STT finalize raising: %s",
                type(self._raise_error).__name__,
            )
            raise self._raise_error
        frames = self._sessions.pop(transcription_id, None)
        self._sessions_started.pop(transcription_id, None)
        if frames is None:
            raise ValueError(f"unknown transcription session {transcription_id}")
        if self._fail:
            self._logger.warning("Fake streaming STT configured to fail")
            return StreamingSttResult.fail(self._fail_message)
        key = b"".join(f.content for f in frames).decode(
            "utf-8", errors="replace"
        )
        text = self._fixtures.get(key)
        if text is None:
            self._logger.warning(
                "Fake streaming STT has no fixture for %r", key
            )
            return StreamingSttResult.fail(
                "no transcription fixture for the provided audio"
            )
        self._logger.info(
            "Fake streaming STT finalized session=%s text_chars=%d",
            transcription_id,
            len(text),
        )
        return StreamingSttResult.ok(
            text=text,
            language=self._default_language,
            confidence=self._default_confidence,
        )


# ----------------------------------------------------------------------
# Streaming text-to-speech
# ----------------------------------------------------------------------


class StreamingTtsStream(ABC):
    """A cursor over generated audio chunks for one synthesis request."""

    @abstractmethod
    async def next_chunk(self) -> AudioData | None:
        """Return the next audio chunk, or ``None`` at the end of stream."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Release stream resources."""
        raise NotImplementedError


class StreamingTTSProvider(ABC):
    """Synthesises speech into incremental audio chunks."""

    name: ClassVar[str]
    description: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        missing = [
            attribute
            for attribute in ("name", "description")
            if not hasattr(cls, attribute)
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} must define required attribute(s): {', '.join(missing)}"
            )

    @abstractmethod
    async def synthesize_stream(self, request: TextToSpeechRequest) -> StreamingTtsStream:
        """Begin streaming synthesis for ``request``."""
        raise NotImplementedError


class FakeStreamingTTSProvider(StreamingTTSProvider):
    """Deterministic, offline streaming text-to-speech provider.

    Splits the requested text into word-sized audio chunks whose bytes are the
    UTF-8 encoding of each word. Failure behavior is configurable.
    """

    name = "fake-streaming-tts"
    description = "Deterministic streaming text-to-speech fake for offline tests."

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        fail: bool = False,
        fail_message: str = "simulated streaming synthesis failure",
        raise_error: Exception | None = None,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be a positive number")
        self._sample_rate = sample_rate
        self._fail = fail
        self._fail_message = fail_message
        self._raise_error = raise_error
        self.requests: list[TextToSpeechRequest] = []
        self._logger = logging.getLogger(__name__)

    async def synthesize_stream(self, request: TextToSpeechRequest) -> StreamingTtsStream:
        self.requests.append(request)
        if self._raise_error is not None:
            self._logger.error(
                "Fake streaming TTS raising: %s", type(self._raise_error).__name__
            )
            raise self._raise_error
        return FakeStreamingTtsStream(
            text=request.text,
            sample_rate=self._sample_rate,
            fail=self._fail,
            fail_message=self._fail_message,
        )


class FakeStreamingTtsStream(StreamingTtsStream):
    """Chunk cursor backed by word-sized audio pieces."""

    def __init__(
        self,
        *,
        text: str,
        sample_rate: int,
        fail: bool = False,
        fail_message: str = "simulated streaming synthesis failure",
    ) -> None:
        self._words = [word for word in text.split() if word]
        self._index = 0
        self._sample_rate = sample_rate
        self._fail = fail
        self._fail_message = fail_message
        self._closed = False
        self._logger = logging.getLogger(__name__)

    @property
    def closed(self) -> bool:
        return self._closed

    async def next_chunk(self) -> AudioData | None:
        if self._closed:
            return None
        if self._fail and self._index == 0:
            self._logger.warning("Fake streaming TTS stream configured to fail")
            raise StreamingError(self._fail_message)
        if self._index >= len(self._words):
            return None
        word = self._words[self._index]
        self._index += 1
        self._logger.info(
            "Fake streaming TTS chunk %d/%d: chars=%d",
            self._index,
            len(self._words),
            len(word),
        )
        return AudioData(
            content=word.encode("utf-8"),
            format="text",
            sample_rate=self._sample_rate,
        )

    async def close(self) -> None:
        self._closed = True
        self._logger.info("Fake streaming TTS stream closed")