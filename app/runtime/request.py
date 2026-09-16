"""Unified request/response models for the MISSMINUTES runtime.

Normalizes text and voice inputs into a single request abstraction
and wraps orchestration results into a uniform response.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class UnifiedRequest(BaseModel):
    """Normalized input for the unified request handler."""

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    source: Literal["text", "voice"] = "text"
    text: str | None = None
    audio: bytes | None = None
    language_hint: str | None = None
    session_id: str | None = None
    timeout_seconds: float | None = None

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("text must not be blank when provided")
        return v

    @field_validator("session_id", "language_hint")
    @classmethod
    def _optional_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("must not be blank")
        return v


class UnifiedResponse(BaseModel):
    """Uniform response from the runtime request handler."""

    request_id: str
    success: bool
    source: Literal["text", "voice"] = "text"
    text_response: str | None = None
    audio_response: bytes | None = None
    task_id: UUID | None = None
    error: str | None = None
    audit_id: str | None = None

    @classmethod
    def ok(
        cls,
        request_id: str,
        *,
        source: Literal["text", "voice"] = "text",
        text_response: str | None = None,
        audio_response: bytes | None = None,
        task_id: UUID | None = None,
        audit_id: str | None = None,
    ) -> UnifiedResponse:
        return cls(
            request_id=request_id,
            success=True,
            source=source,
            text_response=text_response,
            audio_response=audio_response,
            task_id=task_id,
            audit_id=audit_id,
        )

    @classmethod
    def fail(
        cls,
        request_id: str,
        *,
        source: Literal["text", "voice"] = "text",
        error: str,
        audit_id: str | None = None,
    ) -> UnifiedResponse:
        return cls(
            request_id=request_id,
            success=False,
            source=source,
            error=error,
            audit_id=audit_id,
        )
