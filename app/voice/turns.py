"""Conversation turn management for continuous voice sessions.

Associates each recognised utterance with the active task/session, preserves
the detected language style on the turn, and identifies when a user is
continuing an earlier request (rather than starting a new one). The manager is
deterministic: time is injected and markers are explicit.
"""

import logging
import time
from collections.abc import Iterable
from enum import StrEnum
from typing import Callable

from pydantic import BaseModel, field_validator

from app.voice.language import LanguageDetectionResult, LanguageLabel, ResponseStyle


class ConversationTurnKind(StrEnum):
    """Classification of a turn within a session."""

    FIRST = "first"
    FOLLOW_UP = "follow_up"
    CONTINUATION = "continuation"


class ConversationTurn(BaseModel):
    """A single user utterance processed within a voice session."""

    turn_id: int
    session_id: str
    kind: ConversationTurnKind
    transcription: str
    label: LanguageLabel
    confidence: float | None = None
    style: ResponseStyle | None = None
    continuation: bool = False
    audio_ref: str | None = None
    audio_bytes: int = 0
    started_at: float
    completed_at: float | None = None
    success: bool | None = None
    response_text: str | None = None
    interrupted: bool = False
    error: str | None = None

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @field_validator("audio_bytes")
    @classmethod
    def _audio_bytes_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("audio_bytes must not be negative")
        return value


_DEFAULT_CONTINUATION_PREFIXES = (
    "also",
    "and",
    "then",
    "accha",
    "acha",
    "achha",
    "ok",
    "okay",
    "aur",
    "aur phir",
    "and then",
    "ab",
)


class ConversationTurnManager:
    """Owns turn classification, ordering, and per-session history.

    A turn is a ``continuation`` when it arrives within the continuation
    window of the previous turn, or when its text starts with an explicit
    continuation marker. Otherwise a later turn in the same session is a plain
    ``follow_up``.
    """

    def __init__(
        self,
        *,
        continuation_window_seconds: float = 8.0,
        continuation_prefixes: Iterable[str] | None = None,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        if continuation_window_seconds <= 0:
            raise ValueError("continuation_window_seconds must be positive")
        self._window_seconds = continuation_window_seconds
        prefixes = [p.strip().lower() for p in (continuation_prefixes or _DEFAULT_CONTINUATION_PREFIXES) if p.strip()]
        self._prefixes = tuple(prefixes)
        self._now_fn = now_fn or time.time
        self._next_turn_id = 1
        self._by_session: dict[str, list[ConversationTurn]] = {}
        self._by_id: dict[int, ConversationTurn] = {}
        self._logger = logging.getLogger(__name__)

    @property
    def continuation_prefixes(self) -> tuple[str, ...]:
        return self._prefixes

    @property
    def continuation_window_seconds(self) -> float:
        return self._window_seconds

    def begin_turn(
        self,
        session_id: str,
        *,
        text: str,
        detection: LanguageDetectionResult,
        style: ResponseStyle | None = None,
        audio_bytes: int = 0,
        now: float | None = None,
    ) -> ConversationTurn:
        text = text.strip()
        if not text:
            raise ValueError("turn text must not be blank")
        timestamp = self._now_fn() if now is None else now
        previous = self.latest_turn(session_id)
        kind, continuation = self._classify(previous, text, timestamp)
        turn = ConversationTurn(
            turn_id=self._next_turn_id,
            session_id=session_id,
            kind=kind,
            transcription=text,
            label=detection.label,
            confidence=detection.confidence,
            style=style,
            continuation=continuation,
            audio_ref=f"audio:{session_id}/{self._next_turn_id}",
            audio_bytes=audio_bytes,
            started_at=timestamp,
        )
        self._next_turn_id += 1
        self._by_session.setdefault(session_id, []).append(turn)
        self._by_id[turn.turn_id] = turn
        self._logger.info(
            "Turn %d begun: session=%s kind=%s continuation=%s label=%s",
            turn.turn_id,
            session_id,
            kind.value,
            continuation,
            detection.label.value,
        )
        return turn

    def complete_turn(
        self,
        turn_id: int,
        *,
        response_text: str | None = None,
        success: bool = True,
        error: str | None = None,
        interrupted: bool = False,
        now: float | None = None,
    ) -> ConversationTurn:
        turn = self._by_id.get(turn_id)
        if turn is None:
            raise KeyError(f"unknown turn {turn_id}")
        timestamp = self._now_fn() if now is None else now
        completed = turn.model_copy(
            update={
                "response_text": response_text,
                "success": success,
                "error": error,
                "interrupted": interrupted,
                "completed_at": timestamp,
            }
        )
        self._by_id[turn_id] = completed
        turns = self._by_session.get(turn.session_id)
        if turns is not None:
            for index, stored in enumerate(turns):
                if stored.turn_id == turn_id:
                    turns[index] = completed
                    break
        self._logger.info(
            "Turn %d completed: success=%s interrupted=%s",
            turn_id,
            success,
            interrupted,
        )
        return completed

    def latest_turn(self, session_id: str) -> ConversationTurn | None:
        turns = self._by_session.get(session_id)
        if not turns:
            return None
        return turns[-1]

    def turns(self, session_id: str) -> tuple[ConversationTurn, ...]:
        return tuple(self._by_session.get(session_id, ()))

    def is_continuation(
        self,
        previous: ConversationTurn | None,
        text: str,
        *,
        now: float | None = None,
    ) -> bool:
        _, continuation = self._classify(previous, text, now)
        return continuation

    def _classify(
        self,
        previous: ConversationTurn | None,
        text: str,
        now: float | None,
    ) -> tuple[ConversationTurnKind, bool]:
        if previous is None:
            return ConversationTurnKind.FIRST, False
        timestamp = self._now_fn() if now is None else now
        anchor = previous.completed_at or previous.started_at
        recent = (timestamp - anchor) <= self._window_seconds
        lowered = text.lower().strip()
        marker = any(lowered.startswith(prefix) for prefix in self._prefixes)
        continuation = recent or marker
        if continuation:
            return ConversationTurnKind.CONTINUATION, True
        return ConversationTurnKind.FOLLOW_UP, False
