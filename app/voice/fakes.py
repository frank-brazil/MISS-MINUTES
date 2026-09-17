import logging
from collections.abc import Mapping, Sequence
from datetime import timedelta

from app.core.ai import AIMessage, AIModel, AIResponse, ToolDefinition
from app.voice.base import (
    AudioData,
    SpeechInput,
    SpeechToText,
    SpeechToTextResult,
    TextToSpeech,
    TextToSpeechRequest,
    TextToSpeechResult,
)
from app.voice.language import LanguageDetectionResult, LanguageDetector


class FakeSpeechToText(SpeechToText):
    """Deterministic speech-to-text fake for offline tests.

    The fake never touches an external service. Audio is supplied as bytes
    whose UTF-8 decoding identifies a test fixture; the fixture maps to a
    predictable transcription. Unrecognized audio yields a failed result.
    Failure behavior is configurable to exercise controlled error handling.
    """

    name = "fake-speech-to-text"
    description = "Deterministic speech-to-text fake for offline tests."

    def __init__(
        self,
        *,
        fixtures: Mapping[str, str] | None = None,
        default_language: str = "en",
        default_confidence: float = 0.99,
        fail: bool = False,
        fail_message: str = "simulated speech-to-text failure",
        raise_error: Exception | None = None,
    ) -> None:
        if not (0.0 <= default_confidence <= 1.0):
            raise ValueError("default_confidence must be between 0 and 1")
        if not default_language.strip():
            raise ValueError("default_language must not be blank")
        self._fixtures: dict[str, str] = dict(fixtures or {})
        self._default_language = default_language
        self._default_confidence = default_confidence
        self._fail = fail
        self._fail_message = fail_message
        self._raise_error = raise_error
        self._requests: list[SpeechInput] = []
        self._logger = logging.getLogger(__name__)

    @property
    def requests(self) -> tuple[SpeechInput, ...]:
        return tuple(self._requests)

    async def transcribe(self, speech: SpeechInput) -> SpeechToTextResult:
        self._requests.append(speech)
        if self._raise_error is not None:
            self._logger.error("Fake speech-to-text raising: %s", type(self._raise_error).__name__)
            raise self._raise_error
        if self._fail:
            self._logger.warning("Fake speech-to-text configured to fail")
            return SpeechToTextResult.fail(error=self._fail_message)

        try:
            key = speech.audio.decode("utf-8")
        except UnicodeDecodeError:
            self._logger.warning(
                "Speech-to-text input of %d bytes is not a UTF-8 test fixture (%s)",
                len(speech.audio),
                speech.format,
            )
            return SpeechToTextResult.fail(error="audio is not a supported test fixture")

        text = self._fixtures.get(key)
        if text is None:
            self._logger.warning(
                "Speech-to-text input of %d bytes has no matching fixture (%s)",
                len(speech.audio),
                speech.format,
            )
            return SpeechToTextResult.fail(error="no transcription fixture for the provided audio")

        language = speech.language or self._default_language
        self._logger.info(
            "Transcribed %d bytes of speech (%s): success=%s language=%s confidence=%s",
            len(speech.audio),
            speech.format,
            True,
            language,
            self._default_confidence,
        )
        return SpeechToTextResult.ok(
            text=text,
            language=language,
            confidence=self._default_confidence,
        )


class FakeTextToSpeech(TextToSpeech):
    """Deterministic text-to-speech fake for offline tests.

    The fake never touches an external service. The generated audio is a
    deterministic envelope whose bytes are the UTF-8 encoding of the input
    text; the duration and other properties are deterministic configurable
    constants. Failure behavior is configurable to exercise controlled error
    handling.
    """

    name = "fake-text-to-speech"
    description = "Deterministic text-to-speech fake for offline tests."

    def __init__(
        self,
        *,
        language: str = "en",
        voice: str = "sample",
        sample_rate: int = 16000,
        duration: timedelta = timedelta(seconds=1.0),
        fail: bool = False,
        fail_message: str = "simulated text-to-speech failure",
        raise_error: Exception | None = None,
    ) -> None:
        if not language.strip():
            raise ValueError("language must not be blank")
        if not voice.strip():
            raise ValueError("voice must not be blank")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be a positive number")
        self._language = language
        self._voice = voice
        self._sample_rate = sample_rate
        self._duration = duration
        self._fail = fail
        self._fail_message = fail_message
        self._raise_error = raise_error
        self._requests: list[TextToSpeechRequest] = []
        self._logger = logging.getLogger(__name__)

    @property
    def requests(self) -> tuple[TextToSpeechRequest, ...]:
        return tuple(self._requests)

    async def synthesize(self, request: TextToSpeechRequest) -> TextToSpeechResult:
        self._requests.append(request)
        if self._raise_error is not None:
            self._logger.error("Fake text-to-speech raising: %s", type(self._raise_error).__name__)
            raise self._raise_error
        if self._fail:
            self._logger.warning("Fake text-to-speech configured to fail")
            return TextToSpeechResult.fail(error=self._fail_message)

        content = request.text.encode("utf-8")
        audio = AudioData(
            content=content,
            format="text",
            sample_rate=self._sample_rate,
        )
        language = request.language or self._language
        self._logger.info(
            "Synthesized %d characters of speech: success=%s language=%s voice=%s duration=%s",
            len(request.text),
            True,
            language,
            self._voice,
            self._duration,
        )
        return TextToSpeechResult.ok(audio=audio, duration=self._duration)


class FakeLanguageDetector(LanguageDetector):
    """Deterministic language detector fake for offline tests.

    Maps exact transcribed text to a predictable detection. Unrecognized text
    falls back to a configurable default (an ``unknown`` result by default).
    The fake never touches an external service and may simulate a detector
    failure by raising a configured exception.
    """

    name = "fake-language-detector"
    description = "Deterministic language detector fake for offline tests."

    def __init__(
        self,
        *,
        fixtures: Mapping[str, LanguageDetectionResult] | None = None,
        default: LanguageDetectionResult | None = None,
        raise_error: Exception | None = None,
    ) -> None:
        self._fixtures: dict[str, LanguageDetectionResult] = dict(fixtures or {})
        self._default = default or LanguageDetectionResult.unknown()
        self._raise_error = raise_error
        self._logger = logging.getLogger(__name__)

    @property
    def default(self) -> LanguageDetectionResult:
        return self._default

    async def detect(self, text: str) -> LanguageDetectionResult:
        if self._raise_error is not None:
            self._logger.error(
                "Fake language detector raising: %s", type(self._raise_error).__name__
            )
            raise self._raise_error
        result = self._fixtures.get(text, self._default)
        self._logger.info(
            "Detected language via fixture label=%s confidence=%s",
            result.label.value,
            result.confidence,
        )
        return result


class FakeAIModel(AIModel):
    """Deterministic AI model fake for offline pipeline tests.

    Returns a fixed sequence of replies (or a default reply) and records every
    chat request so tests can verify conversational context. Failure behavior
    is configurable to exercise controlled error handling.
    """

    name = "fake-ai-model"
    description = "Deterministic AI model fake for offline pipeline tests."

    def __init__(
        self,
        *,
        replies: Sequence[str] | None = None,
        default_reply: str = "Understood.",
        respond_fail: bool = False,
        raise_error: Exception | None = None,
    ) -> None:
        if not default_reply.strip():
            raise ValueError("default_reply must not be blank")
        self._replies: list[str] = list(replies or [])
        self._default_reply = default_reply
        self._respond_fail = respond_fail
        self._raise_error = raise_error
        self._requests: list[list[AIMessage]] = []
        self._logger = logging.getLogger(__name__)

    @property
    def chat_requests(self) -> tuple[tuple[AIMessage, ...], ...]:
        return tuple(tuple(messages) for messages in self._requests)

    async def chat(
        self,
        messages: Sequence[AIMessage],
        *,
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AIResponse:
        self._requests.append(list(messages))
        if self._raise_error is not None:
            self._logger.error("Fake AI model raising: %s", type(self._raise_error).__name__)
            raise self._raise_error
        if self._respond_fail:
            self._logger.warning("Fake AI model configured to fail")
            return AIResponse.fail(error="simulated AI failure")
        if self._replies:
            content = self._replies.pop(0)
            if not content.strip():
                raise ValueError("fake AI replies must not be blank")
        else:
            content = self._default_reply
        self._logger.info("Fake AI model replied: characters=%d model=%s", len(content), self.name)
        return AIResponse.ok(content=content, model_name=self.name)
