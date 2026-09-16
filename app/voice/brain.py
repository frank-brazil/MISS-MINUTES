"""Response generation boundary for voice turns.

A ``VoiceBrain`` turns recognised speech into reply text. Two provided
implementations show how the boundary reuses existing subsystems without
tightening them to voice:

- :class:`ConversationalVoiceBrain` reuses the AI model chat and response
  style guidance (the same conversational path as the one-shot pipeline).
- :class:`OrchestratorVoiceBrain` routes task-oriented requests through the
  Orchestrator, so any tool/agent/action they trigger is evaluated by the
  CHUNK 30 security policy at the normal execution boundary. Voice input is
  never treated as authorization by itself.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar

from pydantic import BaseModel, field_validator

from app.core.ai import AIMessage, AIModel
from app.core.orchestrator import OrchestrationResult, Orchestrator
from app.core.task import Task
from app.voice.language import ResponseStyle


class VoiceBrainRequest(BaseModel):
    """Typed input for a voice response generation turn."""

    session_id: str | None = None
    turn_id: int | None = None
    text: str
    language: str | None = None
    style: ResponseStyle | None = None

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value

    @field_validator("language")
    @classmethod
    def _language_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("language must not be blank")
        return value


class VoiceBrainResult(BaseModel):
    """Outcome of a voice response generation attempt.

    ``denied`` marks requests that were refused by a security policy (never a
    generic error): the caller can surface that distinctly.
    """

    success: bool
    response: str | None = None
    denied: bool = False
    reason_code: str | None = None
    error: str | None = None

    @classmethod
    def ok(cls, response: str) -> "VoiceBrainResult":
        return cls(success=True, response=response)

    @classmethod
    def fail(
        cls,
        error: str,
        *,
        denied: bool = False,
        reason_code: str | None = None,
    ) -> "VoiceBrainResult":
        return cls(
            success=False,
            error=error,
            denied=denied,
            reason_code=reason_code,
        )


class VoiceBrain(ABC):
    """Interface for generating a reply to recognised speech."""

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
    async def respond(self, request: VoiceBrainRequest) -> VoiceBrainResult:
        raise NotImplementedError


_DEFAULT_BRAIN_SYSTEM_PROMPT = (
    "You are MISSMINUTES, a personal, intelligent, multilingual AI assistant. "
    "Answer the user's most recent spoken message using the provided "
    "conversation history and follow the response-style guidance. Keep "
    "responses suitable for being read aloud."
)


class ConversationalVoiceBrain(VoiceBrain):
    """Conversational reply generator reusing the AI chat boundary.

    Maintains bounded in-memory history and passes the response style as
    structured system context, mirroring the one-shot voice pipeline's chat
    behaviour.
    """

    name = "conversational-voice-brain"
    description = "Conversational reply generator built on the AI chat boundary."

    def __init__(
        self,
        ai_model: AIModel,
        *,
        system_prompt: str | None = None,
        max_history_messages: int = 40,
    ) -> None:
        if max_history_messages < 2:
            raise ValueError("max_history_messages must be at least 2")
        self._ai_model = ai_model
        self._system_prompt = (
            system_prompt or _DEFAULT_BRAIN_SYSTEM_PROMPT
        ).strip()
        self._max_history = max_history_messages
        self._history: list[AIMessage] = []
        self._logger = logging.getLogger(__name__)

    @property
    def history(self) -> tuple[AIMessage, ...]:
        return tuple(self._history)

    async def respond(self, request: VoiceBrainRequest) -> VoiceBrainResult:
        messages = self._build_messages(request)
        self._logger.info(
            "Conversational brain answering: session=%s turn=%d chars=%d",
            request.session_id,
            request.turn_id,
            len(request.text),
        )
        try:
            response = await self._ai_model.chat(messages)
        except Exception as exc:
            self._logger.warning(
                "Conversational brain chat raised %s", type(exc).__name__
            )
            return VoiceBrainResult.fail(
                "conversational brain provider raised an error"
            )
        content = (response.content or "").strip()
        if not response.success or not content:
            self._logger.warning(
                "Conversational brain failed: success=%s empty=%s",
                response.success,
                not content,
            )
            return VoiceBrainResult.fail(
                response.error or "conversational brain returned an empty response"
            )
        self._history.append(AIMessage(role="user", content=request.text))
        self._history.append(AIMessage(role="assistant", content=content))
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]
        self._logger.info(
            "Conversational brain replied: chars=%d history=%d",
            len(content),
            len(self._history),
        )
        return VoiceBrainResult.ok(content)

    def _build_messages(self, request: VoiceBrainRequest) -> list[AIMessage]:
        messages: list[AIMessage] = []
        if self._system_prompt:
            messages.append(AIMessage(role="system", content=self._system_prompt))
        guidance = request.style.guidance if request.style is not None else ""
        if guidance:
            messages.append(
                AIMessage(role="system", content=f"Response style: {guidance}")
            )
        messages.extend(self._history)
        messages.append(AIMessage(role="user", content=request.text))
        return messages


_DENY_MARKERS = (
    "denied by security policy",
    "requires confirmation",
    "no declared permission",
    "denied",
)


class OrchestratorVoiceBrain(VoiceBrain):
    """Task-oriented reply generator routed through the Orchestrator.

    The transcribed request becomes a task for the existing Orchestrator, so
    every tool/agent action it triggers flows through the normal CHUNK 30
    security seam. Each dispatch is recorded in the security audit trail with
    the origin ``voice`` (redacted, no transcript content).
    """

    name = "orchestrator-voice-brain"
    description = "Task-oriented reply generator routed through the Orchestrator."

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator
        self._logger = logging.getLogger(__name__)

    @property
    def orchestrator(self) -> Orchestrator:
        return self._orchestrator

    async def respond(self, request: VoiceBrainRequest) -> VoiceBrainResult:
        task = Task(description=request.text)
        self._logger.info(
            "Orchestrator brain dispatching: session=%s turn=%d task=%s",
            request.session_id,
            request.turn_id,
            task.task_id,
        )
        result: OrchestrationResult = await self._orchestrator.execute(task)
        self._audit_dispatch(result)
        if result.success:
            output = (result.output or "").strip()
            self._logger.info(
                "Orchestrator brain succeeded: task=%s output_chars=%d",
                result.task_id,
                len(output),
            )
            return VoiceBrainResult.ok(output or "Understood.")
        error = result.error or "task failed"
        denied = any(marker in error.lower() for marker in _DENY_MARKERS)
        self._logger.warning(
            "Orchestrator brain failed: task=%s denied=%s error=%s",
            result.task_id,
            denied,
            error,
        )
        return VoiceBrainResult.fail(
            error=error,
            denied=denied,
            reason_code="security_denial" if denied else "task_failure",
        )

    def _audit_dispatch(self, result: OrchestrationResult) -> None:
        security = self._orchestrator.security
        if security is None:
            return
        security.audit_event(
            action="voice:dispatch_task",
            permission="voice",
            success=result.success,
            task_id=str(result.task_id),
            actor=None,
            origin="voice",
            reason_code="voice_dispatch",
        )


class FakeVoiceBrain(VoiceBrain):
    """Deterministic scripted brain for offline tests."""

    name = "fake-voice-brain"
    description = "Deterministic scripted voice brain for offline tests."

    def __init__(
        self,
        results: Sequence[VoiceBrainResult] | None = None,
        *,
        default: VoiceBrainResult | None = None,
        raise_error: Exception | None = None,
    ) -> None:
        self._results = list(results or [])
        self._default = default or VoiceBrainResult.ok("Understood.")
        self._raise_error = raise_error
        self._requests: list[VoiceBrainRequest] = []
        self._logger = logging.getLogger(__name__)

    @property
    def requests(self) -> tuple[VoiceBrainRequest, ...]:
        return tuple(self._requests)

    async def respond(self, request: VoiceBrainRequest) -> VoiceBrainResult:
        self._requests.append(request)
        if self._raise_error is not None:
            self._logger.error(
                "Fake brain raising: %s", type(self._raise_error).__name__
            )
            raise self._raise_error
        if self._results:
            return self._results.pop(0)
        return self._default
