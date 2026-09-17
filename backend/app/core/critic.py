"""Provider-independent critique abstraction.

A critic examines a proposed solution or analysis before (or after) execution
and reports weaknesses, risks, unsupported assumptions, missing evidence,
contradictions, and alternative explanations. A critique is **not** a fact: it
is a structured, heuristic judgment about the supplied material.

Terminology used throughout:

- **critique**: the typed output (``Critique``) containing categorized points.
- **critique point**: a single observation (``CritiquePoint``) tagged with an
  aspect such as ``weakness`` or ``risk``.
- **severity**: how serious a point is (``Severity``), a qualitative judgment.
- **evidence**: a structured statement about what is known; critique models
  never fabricate evidence, they only carry what a caller or provider supplies
  (see ``evidence_refs`` on ``CritiquePoint``).

This module is intentionally standalone and provider-independent: it depends
on neither FastAPI nor OpenAI nor any other model provider, browser/desktop
automation, or database.
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

CONFIDENCE_RANGE_DESCRIPTION = (
    "Confidence scores are heuristic ordinal estimates in [0, 1]. "
    "They are not calibrated probabilities."
)
CRITIQUE_IS_ESTIMATE_NOTICE = (
    "Critique points are heuristic judgments based on the supplied "
    "information; they are not established facts."
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Severity(StrEnum):
    """How serious a critique point (or the whole critique) is."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class CritiqueAspect(StrEnum):
    """Category of a critique point."""

    WEAKNESS = "weakness"
    RISK = "risk"
    UNSUPPORTED_ASSUMPTION = "unsupported_assumption"
    MISSING_EVIDENCE = "missing_evidence"
    CONTRADICTION = "contradiction"
    ALTERNATIVE_EXPLANATION = "alternative_explanation"


class CritiquePoint(BaseModel):
    """A single critique observation.

    ``evidence_refs`` carry references (for example research result URLs or
    reference strings) to supporting material; they are never fabricated.
    """

    model_config = ConfigDict(validate_assignment=True)

    point_id: UUID = Field(default_factory=uuid4)
    aspect: CritiqueAspect
    description: str
    severity: Severity = Severity.UNKNOWN
    confidence: float | None = None
    suggestion: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("description")
    @classmethod
    def _description_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description must not be blank")
        return value

    @field_validator("suggestion")
    @classmethod
    def _suggestion_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("suggestion must not be blank")
        return value

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @field_validator("evidence_refs")
    @classmethod
    def _refs_not_blank(cls, value: list[str]) -> list[str]:
        for reference in value:
            if not reference.strip():
                raise ValueError("evidence refs must not be blank")
        return value


class CritiqueRequest(BaseModel):
    """Typed input for a critic.

    ``target`` describes the proposed solution or analysis to examine;
    ``supporting_evidence_refs`` optionally carries references to supplied
    evidence (never fabricated) so the critic can weigh them.
    """

    model_config = ConfigDict(validate_assignment=True)

    request_id: UUID = Field(default_factory=uuid4)
    target: str
    context: dict[str, Any] = Field(default_factory=dict)
    supporting_evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("target")
    @classmethod
    def _target_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("target must not be blank")
        return value

    @field_validator("supporting_evidence_refs")
    @classmethod
    def _evidence_refs_not_blank(cls, value: list[str]) -> list[str]:
        for reference in value:
            if not reference.strip():
                raise ValueError("evidence refs must not be blank")
        return value


class Critique(BaseModel):
    """Typed result of examining a proposed solution or analysis.

    Points are grouped by aspect through the ``weaknesses``, ``risks``,
    ``unsupported_assumptions``, ``missing_evidence``, ``contradictions``, and
    ``alternative_explanations`` properties. The critique is heuristic judgment,
    not fact; ``notes`` always carries ``CRITIQUE_IS_ESTIMATE_NOTICE`` when a
    provider produces one.
    """

    model_config = ConfigDict(validate_assignment=True)

    critique_id: UUID = Field(default_factory=uuid4)
    target: str
    points: list[CritiquePoint] = Field(default_factory=list)
    summary: str | None = None
    overall_severity: Severity = Severity.UNKNOWN
    confidence: float | None = None
    notes: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("target")
    @classmethod
    def _target_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("target must not be blank")
        return value

    @field_validator("summary")
    @classmethod
    def _summary_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("summary must not be blank")
        return value

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @field_validator("notes", "unresolved_questions")
    @classmethod
    def _notes_not_blank(cls, value: list[str]) -> list[str]:
        for note in value:
            if not note.strip():
                raise ValueError("entries must not be blank")
        return value

    def _points_for(self, aspect: CritiqueAspect) -> tuple[CritiquePoint, ...]:
        return tuple(point for point in self.points if point.aspect is aspect)

    @property
    def weaknesses(self) -> tuple[CritiquePoint, ...]:
        return self._points_for(CritiqueAspect.WEAKNESS)

    @property
    def risks(self) -> tuple[CritiquePoint, ...]:
        return self._points_for(CritiqueAspect.RISK)

    @property
    def unsupported_assumptions(self) -> tuple[CritiquePoint, ...]:
        return self._points_for(CritiqueAspect.UNSUPPORTED_ASSUMPTION)

    @property
    def missing_evidence(self) -> tuple[CritiquePoint, ...]:
        return self._points_for(CritiqueAspect.MISSING_EVIDENCE)

    @property
    def contradictions(self) -> tuple[CritiquePoint, ...]:
        return self._points_for(CritiqueAspect.CONTRADICTION)

    @property
    def alternative_explanations(self) -> tuple[CritiquePoint, ...]:
        return self._points_for(CritiqueAspect.ALTERNATIVE_EXPLANATION)

    @property
    def highest_severity(self) -> Severity:
        """The most severe point severity, or ``overall_severity`` if empty."""
        if not self.points:
            return self.overall_severity
        ranked = {
            Severity.LOW: 1,
            Severity.MEDIUM: 2,
            Severity.HIGH: 3,
            Severity.CRITICAL: 4,
            Severity.UNKNOWN: 0,
        }
        return max(
            self.points,
            key=lambda point: ranked[point.severity],
        ).severity


class Critic(ABC):
    """Provider-independent critique interface.

    A critic accepts a ``CritiqueRequest`` and returns a typed ``Critique``.
    Implementations are expected to be independent of any AI model provider,
    research provider, browser/desktop automation, and database.
    """

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
    async def critique(self, request: CritiqueRequest) -> Critique:
        raise NotImplementedError


def _stable_uuid(*parts: str) -> UUID:
    """Deterministic UUID from string parts (for the deterministic fake)."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return UUID(digest[:32])


class FakeCritic(Critic):
    """Deterministic critique fake for offline tests.

    The fake accepts any target, never calls an LLM, never touches the network,
    and does not special-case any single user's problem. Given the same request
    it returns the same categorized points, overall severity, and confidence.
    Point descriptions are generic categories, never claims of established
    fact; empty contradiction lists simply mean no contradiction was identified.
    """

    name = "fake-critic"
    description = "Deterministic heuristic critique fake for offline tests."

    def __init__(self, raise_error: Exception | None = None) -> None:
        self._raise_error = raise_error
        self._requests: list[CritiqueRequest] = []
        self._logger = logging.getLogger(__name__)

    @property
    def requests(self) -> tuple[CritiqueRequest, ...]:
        return tuple(self._requests)

    async def critique(self, request: CritiqueRequest) -> Critique:
        self._requests.append(request)
        if self._raise_error is not None:
            self._logger.error("Fake critic raising: %s", type(self._raise_error).__name__)
            raise self._raise_error

        seed = request.target.strip()
        points: list[CritiquePoint] = [
            CritiquePoint(
                point_id=_stable_uuid(seed, "point:weakness"),
                aspect=CritiqueAspect.WEAKNESS,
                description=(
                    "The target considers only the information supplied to it; "
                    "anything outside that material may be missed."
                ),
                severity=Severity.LOW,
                confidence=0.4,
                suggestion=("Provide more context so the review can consider it."),
            ),
            CritiquePoint(
                point_id=_stable_uuid(seed, "point:risk"),
                aspect=CritiqueAspect.RISK,
                description=(
                    "The target includes estimated claims that are not guaranteed to hold."
                ),
                severity=Severity.MEDIUM,
                confidence=0.5,
            ),
            CritiquePoint(
                point_id=_stable_uuid(seed, "point:assumption"),
                aspect=CritiqueAspect.UNSUPPORTED_ASSUMPTION,
                description=(
                    "The target's assumptions are stated, but no external evidence confirms them."
                ),
                severity=Severity.MEDIUM,
                confidence=0.5,
            ),
            CritiquePoint(
                point_id=_stable_uuid(seed, "point:evidence"),
                aspect=CritiqueAspect.MISSING_EVIDENCE,
                description=(
                    "No cited research evidence is attached; stronger "
                    "conclusions would benefit from references."
                ),
                severity=Severity.LOW,
                confidence=0.4,
            ),
            CritiquePoint(
                point_id=_stable_uuid(seed, "point:alternative"),
                aspect=CritiqueAspect.ALTERNATIVE_EXPLANATION,
                description=(
                    "An alternative explanation may exist that the supplied "
                    "information does not rule out."
                ),
                severity=Severity.LOW,
                confidence=0.4,
            ),
        ]

        critique = Critique(
            critique_id=_stable_uuid(seed, "critique"),
            target=request.target,
            points=points,
            summary=(
                "The target has pragmatic weaknesses and relies on stated "
                "assumptions; evidence would strengthen it."
            ),
            overall_severity=Severity.MEDIUM,
            confidence=0.4,
            notes=[CRITIQUE_IS_ESTIMATE_NOTICE],
            unresolved_questions=[
                "What additional evidence is available?",
                "What would rule out the alternative explanation?",
            ],
        )

        self._logger.info(
            "Fake critic examined: request_id=%s critique_id=%s "
            "points=%d overall_severity=%s confidence=%s",
            request.request_id,
            critique.critique_id,
            len(critique.points),
            critique.overall_severity,
            critique.confidence,
        )
        return critique
