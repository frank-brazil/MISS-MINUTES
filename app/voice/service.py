import logging
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.core.ai import AIMessage, AIModel, AIResponse
from app.voice.base import (
    AudioData,
    SpeechInput,
    SpeechToText,
    SpeechToTextResult,
    TextToSpeech,
    TextToSpeechRequest,
    TextToSpeechResult,
)
from app.voice.language import (
    ConversationLanguage,
    LanguageDetectionResult,
    LanguageDetector,
    LanguageLabel,
    ResponseStyle,
)


class VoicePipelineStage(StrEnum):
    """Structured pipeline stage identifiers used in results and logs."""

    INPUT = "input"
    STT = "stt"
    LANGUAGE = "language"
    AI = "ai"
    TTS = "tts"
    COMPLETE = "complete"


class VoiceConversationRequest(BaseModel):
    """Typed audio input for a single voice conversation turn."""

    audio: bytes = Field(min_length=1)
    format: str = "wav"
    sample_rate: int | None = None
    language_hint: str | None = None
    request_id: str | None = None

    @field_validator("format")
    @classmethod
    def _format_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("format must not be blank")
        return value

    @field_validator("language_hint", "request_id")
    @classmethod
    def _optional_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("sample_rate")
    @classmethod
    def _sample_rate_positive(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("sample_rate must be a positive number")
        return value


class VoiceConversationResult(BaseModel):
    """Typed outcome of a voice conversation turn.

    On success ``stage`` is ``complete`` and every pipeline field is populated.
    On failure ``success`` is False, ``stage`` identifies where the pipeline
    stopped, and any partial results gathered so far are kept for diagnostics.
    """

    request_id: str
    success: bool
    stage: VoicePipelineStage | None = None
    transcription: str | None = None
    language: str | None = None
    detection: LanguageDetectionResult | None = None
    response_style: ResponseStyle | None = None
    ai_response: str | None = None
    audio: AudioData | None = None
    audio_ref: str | None = None
    error: str | None = None

    @classmethod
    def ok(
        cls,
        *,
        request_id: str,
        transcription: str,
        detection: LanguageDetectionResult,
        response_style: ResponseStyle,
        ai_response: str,
        audio: AudioData | None = None,
        audio_ref: str | None = None,
    ) -> "VoiceConversationResult":
        language = detection.label.value if detection is not None else None
        return cls(
            request_id=request_id,
            success=True,
            stage=VoicePipelineStage.COMPLETE,
            transcription=transcription,
            language=language,
            detection=detection,
            response_style=response_style,
            ai_response=ai_response,
            audio=audio,
            audio_ref=audio_ref,
        )

    @classmethod
    def fail(
        cls,
        *,
        request_id: str,
        stage: VoicePipelineStage,
        error: str,
        transcription: str | None = None,
        detection: LanguageDetectionResult | None = None,
        response_style: ResponseStyle | None = None,
        ai_response: str | None = None,
    ) -> "VoiceConversationResult":
        language = detection.label.value if detection is not None else None
        return cls(
            request_id=request_id,
            success=False,
            stage=stage,
            transcription=transcription,
            language=language,
            detection=detection,
            response_style=response_style,
            ai_response=ai_response,
            error=error,
        )


_TTS_LANGUAGE_HINT: dict[LanguageLabel, str | None] = {
    LanguageLabel.ENGLISH: "en",
    LanguageLabel.HINDI: "hi",
    LanguageLabel.HINGLISH: "en",
    LanguageLabel.URDU: "ur",
    LanguageLabel.MIXED: None,
    LanguageLabel.UNKNOWN: None,
}

_DEFAULT_SYSTEM_PROMPT = (
    "You are MISSMINUTES, a personal, intelligent, multilingual AI assistant. "
    "Answer the user's most recent message using the provided conversation "
    "history and follow the response-style guidance."
)


class VoiceConversationService:
    """Provider-independent conversational voice pipeline.

    The service owns the audio-in/audio-out pipeline and the in-memory
    conversation history. Nothing here depends on a specific provider: the
    speech-to-text, text-to-speech, language detector, and AI model are all
    injected. The detected language/style is tracked across turns and the
    response style is passed to the AI model as structured system context.
    Provider failures are converted into controlled ``VoiceConversationResult``
    failures instead of being re-raised to callers.
    """

    def __init__(
        self,
        *,
        stt: SpeechToText,
        tts: TextToSpeech,
        detector: LanguageDetector,
        ai_model: AIModel,
        conversation_language: ConversationLanguage | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._stt = stt
        self._tts = tts
        self._detector = detector
        self._ai_model = ai_model
        self._conversation_language = conversation_language or ConversationLanguage()
        self._system_prompt = (system_prompt or _DEFAULT_SYSTEM_PROMPT).strip()
        self._history: list[AIMessage] = []
        self._logger = logging.getLogger(__name__)

    @property
    def conversation_language(self) -> ConversationLanguage:
        return self._conversation_language

    @property
    def history(self) -> tuple[AIMessage, ...]:
        return tuple(self._history)

    async def handle(self, request: VoiceConversationRequest) -> VoiceConversationResult:
        request_id = self._resolve_request_id(request.request_id)
        self._logger.info(
            "Voice conversation starting: request_id=%s stage=%s "
            "audio_format=%s audio_bytes=%d",
            request_id,
            VoicePipelineStage.INPUT.value,
            request.format,
            len(request.audio),
        )
        if not request.audio:
            return self._controlled_fail(
                request_id=request_id,
                stage=VoicePipelineStage.INPUT,
                error="no audio content provided",
            )

        transcription_result = await self._transcribe(request, request_id)
        if not transcription_result.success:
            return self._controlled_fail(
                request_id=request_id,
                stage=VoicePipelineStage.STT,
                error=transcription_result.error or "speech-to-text failed",
            )
        text = (transcription_result.text or "").strip()
        if not text:
            return self._controlled_fail(
                request_id=request_id,
                stage=VoicePipelineStage.STT,
                error="speech-to-text produced no text",
            )

        detection = await self._detect(text, request_id)
        if detection is None:
            return self._controlled_fail(
                request_id=request_id,
                stage=VoicePipelineStage.LANGUAGE,
                error="language detection failed",
                transcription=text,
            )
        style = self._conversation_language.update(detection)

        ai_response = await self._chat(text, style, request_id)
        if not ai_response.success:
            return self._controlled_fail(
                request_id=request_id,
                stage=VoicePipelineStage.AI,
                error=ai_response.error or "AI model failed",
                transcription=text,
                detection=detection,
                response_style=style,
            )
        content = (ai_response.content or "").strip()
        if not content:
            return self._controlled_fail(
                request_id=request_id,
                stage=VoicePipelineStage.AI,
                error="AI model returned an empty response",
                transcription=text,
                detection=detection,
                response_style=style,
            )

        tts_result = await self._synthesize(content, style, request_id)
        if not tts_result.success:
            return self._controlled_fail(
                request_id=request_id,
                stage=VoicePipelineStage.TTS,
                error=tts_result.error or "text-to-speech failed",
                transcription=text,
                detection=detection,
                response_style=style,
                ai_response=content,
            )

        self._logger.info(
            "Voice conversation completed: request_id=%s stage=%s success=%s",
            request_id,
            VoicePipelineStage.COMPLETE.value,
            True,
        )
        return VoiceConversationResult.ok(
            request_id=request_id,
            transcription=text,
            detection=detection,
            response_style=style,
            ai_response=content,
            audio=tts_result.audio,
            audio_ref=tts_result.audio_ref,
        )

    async def _transcribe(
        self, request: VoiceConversationRequest, request_id: str
    ) -> SpeechToTextResult:
        self._logger.info(
            "Voice conversation stage started: request_id=%s stage=%s",
            request_id,
            VoicePipelineStage.STT.value,
        )
        try:
            result = await self._stt.transcribe(
                SpeechInput(
                    audio=request.audio,
                    format=request.format,
                    sample_rate=request.sample_rate,
                    language=request.language_hint,
                )
            )
        except Exception as exc:
            self._logger.warning(
                "Voice conversation stage exception: request_id=%s stage=%s "
                "error=%s",
                request_id,
                VoicePipelineStage.STT.value,
                type(exc).__name__,
            )
            return SpeechToTextResult.fail(
                "speech-to-text provider raised an error"
            )
        self._logger.info(
            "Voice conversation stage: request_id=%s stage=%s success=%s "
            "transcription_chars=%d",
            request_id,
            VoicePipelineStage.STT.value,
            result.success,
            len(result.text or ""),
        )
        return result

    async def _detect(
        self, text: str, request_id: str
    ) -> LanguageDetectionResult | None:
        self._logger.info(
            "Voice conversation stage started: request_id=%s stage=%s",
            request_id,
            VoicePipelineStage.LANGUAGE.value,
        )
        try:
            detection = await self._detector.detect(text)
        except Exception as exc:
            self._logger.warning(
                "Voice conversation stage exception: request_id=%s stage=%s "
                "error=%s",
                request_id,
                VoicePipelineStage.LANGUAGE.value,
                type(exc).__name__,
            )
            return None
        self._logger.info(
            "Voice conversation stage: request_id=%s stage=%s success=%s "
            "label=%s",
            request_id,
            VoicePipelineStage.LANGUAGE.value,
            True,
            detection.label.value,
        )
        return detection

    async def _chat(
        self, text: str, style: ResponseStyle, request_id: str
    ) -> AIResponse:
        self._logger.info(
            "Voice conversation stage started: request_id=%s stage=%s",
            request_id,
            VoicePipelineStage.AI.value,
        )
        messages = self._build_ai_request(text, style)
        try:
            response = await self._ai_model.chat(messages)
        except Exception as exc:
            self._logger.warning(
                "Voice conversation stage exception: request_id=%s stage=%s "
                "error=%s",
                request_id,
                VoicePipelineStage.AI.value,
                type(exc).__name__,
            )
            return AIResponse.fail("AI provider raised an error")
        content = (response.content or "").strip()
        if response.success and content:
            self._history.append(AIMessage(role="user", content=text))
            self._history.append(
                AIMessage(role="assistant", content=response.content)
            )
        self._logger.info(
            "Voice conversation stage: request_id=%s stage=%s success=%s "
            "label=%s",
            request_id,
            VoicePipelineStage.AI.value,
            response.success,
            style.label.value,
        )
        return response

    async def _synthesize(
        self, text: str, style: ResponseStyle, request_id: str
    ) -> TextToSpeechResult:
        self._logger.info(
            "Voice conversation stage started: request_id=%s stage=%s",
            request_id,
            VoicePipelineStage.TTS.value,
        )
        tts_request = TextToSpeechRequest(
            text=text,
            language=_TTS_LANGUAGE_HINT.get(style.label),
        )
        try:
            result = await self._tts.synthesize(tts_request)
        except Exception as exc:
            self._logger.warning(
                "Voice conversation stage exception: request_id=%s stage=%s "
                "error=%s",
                request_id,
                VoicePipelineStage.TTS.value,
                type(exc).__name__,
            )
            return TextToSpeechResult.fail("text-to-speech provider raised an error")
        self._logger.info(
            "Voice conversation stage: request_id=%s stage=%s success=%s "
            "speech_chars=%d",
            request_id,
            VoicePipelineStage.TTS.value,
            result.success,
            len(text),
        )
        return result

    def _build_ai_request(self, text: str, style: ResponseStyle) -> list[AIMessage]:
        messages: list[AIMessage] = []
        if self._system_prompt:
            messages.append(
                AIMessage(role="system", content=self._system_prompt)
            )
        messages.append(
            AIMessage(
                role="system",
                content=f"Response style for this conversation: {style.guidance}",
            )
        )
        messages.extend(self._history)
        messages.append(AIMessage(role="user", content=text))
        return messages

    def _controlled_fail(
        self,
        *,
        request_id: str,
        stage: VoicePipelineStage,
        error: str,
        transcription: str | None = None,
        detection: LanguageDetectionResult | None = None,
        response_style: ResponseStyle | None = None,
        ai_response: str | None = None,
    ) -> VoiceConversationResult:
        self._logger.warning(
            "Voice conversation controlled failure: request_id=%s stage=%s "
            "success=%s error=%s",
            request_id,
            stage.value,
            False,
            error,
        )
        return VoiceConversationResult.fail(
            request_id=request_id,
            stage=stage,
            error=error,
            transcription=transcription,
            detection=detection,
            response_style=response_style,
            ai_response=ai_response,
        )

    def _resolve_request_id(self, request_id: str | None) -> str:
        if isinstance(request_id, str):
            value = request_id.strip()
            if value:
                return value
        return str(uuid4())
