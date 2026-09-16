"""Provider-independent general problem-solving abstraction.

This module defines typed domain models for problem analysis and a
provider-independent solver interface. It deliberately stays separate from
prediction, simulation, the critic, verification, and any execution layer.

Terminology used throughout:

- **fact/evidence**: a structured statement (`Evidence`) about what is known;
  an evidence item is never fabricated by these models.
- **hypothesis**: a possible cause or explanation (`Hypothesis`).
- **proposed solution**: a possible action to try (`Solution`).
- **prediction**: a statement about a future outcome. Predictions and
  simulation are intentionally out of scope here.
- **recommendation**: the analysis' chosen next step
  (`ProblemAnalysis.recommended_solution_id`).

Confidence is a heuristic ordinal score in ``[0, 1]``. It documents relative
strength of the models' reasoning for a human reader; it is **not** a
statistically calibrated probability.
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONFIDENCE_RANGE_DESCRIPTION = (
    "Confidence scores are heuristic ordinal estimates in [0, 1]. "
    "They are not calibrated probabilities."
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RiskLevel(StrEnum):
    """Explicit representation of how risky a proposed solution is."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class EvidenceKind(StrEnum):
    """Category of a piece of evidence.

    ``RESEARCH`` marks evidence that references an external research result;
    models never invent evidence, they only carry what a caller or provider
    supplies.
    """

    FACT = "fact"
    OBSERVATION = "observation"
    ASSUMPTION = "assumption"
    RESEARCH = "research"


class Problem(BaseModel):
    """A problem to analyze.

    ``context`` carries structured surrounding information (for example what
    was tried, the environment, or an error message); it is not required.
    """

    model_config = ConfigDict(validate_assignment=True)

    problem_id: UUID = Field(default_factory=uuid4)
    description: str
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("description")
    @classmethod
    def _description_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description must not be blank")
        return value


class Evidence(BaseModel):
    """A structured statement about what is known.

    ``source_ref`` is an optional reference (for example a research result's
    URL or reference string) so evidence can point back to where it came from.
    """

    model_config = ConfigDict(validate_assignment=True)

    evidence_id: UUID = Field(default_factory=uuid4)
    description: str
    kind: EvidenceKind = EvidenceKind.OBSERVATION
    source_ref: str | None = None
    confidence: float | None = None

    @field_validator("description")
    @classmethod
    def _description_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description must not be blank")
        return value

    @field_validator("source_ref")
    @classmethod
    def _source_ref_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("source_ref must not be blank")
        return value

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value


class Hypothesis(BaseModel):
    """A possible cause or explanation of the problem.

    ``evidence_for`` and ``evidence_against`` carry supporting and
    contradicting evidence respectively; the model does not fabricate either.
    """

    model_config = ConfigDict(validate_assignment=True)

    hypothesis_id: UUID = Field(default_factory=uuid4)
    description: str
    confidence: float | None = None
    evidence_for: list[Evidence] = Field(default_factory=list)
    evidence_against: list[Evidence] = Field(default_factory=list)

    @field_validator("description")
    @classmethod
    def _description_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description must not be blank")
        return value

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value


class Solution(BaseModel):
    """A possible solution or next action.

    ``required_capabilities`` lists capabilities or tools the action would
    need; ordering is not significant, so it uses an immutable frozenset.
    """

    model_config = ConfigDict(validate_assignment=True)

    solution_id: UUID = Field(default_factory=uuid4)
    description: str
    expected_outcome: str | None = None
    confidence: float | None = None
    risk: RiskLevel = RiskLevel.UNKNOWN
    risk_note: str | None = None
    required_capabilities: frozenset[str] = Field(default_factory=frozenset)

    @field_validator("description")
    @classmethod
    def _description_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description must not be blank")
        return value

    @field_validator("expected_outcome", "risk_note")
    @classmethod
    def _optional_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @field_validator("required_capabilities")
    @classmethod
    def _capabilities_not_blank(cls, value: frozenset[str]) -> frozenset[str]:
        for capability in value:
            if not capability.strip():
                raise ValueError("required capabilities must not be blank")
        return value


class ProblemAnalysis(BaseModel):
    """Typed result of analyzing a problem.

    The analysis proposes hypotheses and candidate solutions and, when one is
    recommended, points at it via ``recommended_solution_id``. It records what
    remains unknown in ``unresolved_questions``. It deliberately does not
    include predictions or calibrated probabilities.
    """

    model_config = ConfigDict(validate_assignment=True)

    analysis_id: UUID = Field(default_factory=uuid4)
    problem: Problem
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    candidate_solutions: list[Solution] = Field(default_factory=list)
    recommended_solution_id: UUID | None = None
    confidence: float | None = None
    unresolved_questions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @field_validator("unresolved_questions")
    @classmethod
    def _questions_not_blank(cls, value: list[str]) -> list[str]:
        for question in value:
            if not question.strip():
                raise ValueError("unresolved questions must not be blank")
        return value

    @model_validator(mode="after")
    def _recommendation_must_be_candidate(self) -> "ProblemAnalysis":
        if self.recommended_solution_id is not None:
            candidate_ids = {
                solution.solution_id for solution in self.candidate_solutions
            }
            if self.recommended_solution_id not in candidate_ids:
                raise ValueError(
                    "recommended solution must refer to a candidate solution"
                )
        return self

    @property
    def recommended_solution(self) -> "Solution | None":
        """The recommended candidate solution, if a recommendation exists."""
        if self.recommended_solution_id is None:
            return None
        for solution in self.candidate_solutions:
            if solution.solution_id == self.recommended_solution_id:
                return solution
        return None


class ProblemSolver(ABC):
    """Provider-independent problem-solving interface.

    A solver accepts a ``Problem`` and returns a typed ``ProblemAnalysis``.
    Implementations are expected to be independent of any AI model provider,
    research provider, browser automation, and operating-system automation.
    """

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
    async def solve(self, problem: Problem) -> ProblemAnalysis:
        raise NotImplementedError


def _stable_uuid(*parts: str) -> UUID:
    """Deterministic UUID from string parts (for the deterministic fake)."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return UUID(digest[:32])


class FakeProblemSolver(ProblemSolver):
    """Deterministic problem-solving fake for offline tests.

    The fake accepts any problem, never touches the network, never calls an AI
    provider, and does not special-case any single user's problem. Given the
    same problem description it returns the same hypotheses, candidate
    solutions, recommendation, and confidence. Evidence is only ever a
    restatement of the input (``observation``) or an explicitly labeled
    assumption; the fake does not fabricate facts.
    """

    name = "fake-problem-solver"
    description = (
        "Deterministic heuristic problem-solving fake for offline tests."
    )

    def __init__(self, raise_error: Exception | None = None) -> None:
        self._raise_error = raise_error
        self._requests: list[Problem] = []
        self._logger = logging.getLogger(__name__)

    @property
    def requests(self) -> tuple[Problem, ...]:
        return tuple(self._requests)

    async def solve(self, problem: Problem) -> ProblemAnalysis:
        self._requests.append(problem)
        if self._raise_error is not None:
            self._logger.error(
                "Fake problem solver raising: %s", type(self._raise_error).__name__
            )
            raise self._raise_error

        seed = problem.description.strip()
        reported = Evidence(
            evidence_id=_stable_uuid(seed, "evidence:reported"),
            description=f"Problem statement: '{problem.description[:200]}'",
            kind=EvidenceKind.OBSERVATION,
        )
        primary = Hypothesis(
            hypothesis_id=_stable_uuid(seed, "hypothesis:primary"),
            description=(
                "The problem as stated is the primary subject to investigate."
            ),
            confidence=0.5,
            evidence_for=[reported],
        )

        if problem.context:
            context_evidence = Evidence(
                evidence_id=_stable_uuid(seed, "evidence:context"),
                description=(
                    "The problem includes structured context that may explain "
                    "contributing causes."
                ),
                kind=EvidenceKind.OBSERVATION,
            )
        else:
            context_evidence = Evidence(
                evidence_id=_stable_uuid(seed, "evidence:no-context"),
                description=(
                    "No structured context was provided; additional causes "
                    "remain unknown."
                ),
                kind=EvidenceKind.ASSUMPTION,
            )
        secondary = Hypothesis(
            hypothesis_id=_stable_uuid(seed, "hypothesis:secondary"),
            description=(
                "Contributing causes may only become clear after gathering "
                "more information."
            ),
            confidence=0.3,
            evidence_for=[context_evidence],
        )

        first_action = Solution(
            solution_id=_stable_uuid(seed, "solution:research"),
            description=(
                "Gather more information about the problem before choosing an "
                "action."
            ),
            expected_outcome=(
                "A clearer understanding of causes, constraints, and context."
            ),
            confidence=0.4,
            risk=RiskLevel.LOW,
            required_capabilities=frozenset({"research"}),
        )
        second_action = Solution(
            solution_id=_stable_uuid(seed, "solution:first-step"),
            description=(
                "Take a small, reversible first action based on the stated "
                "problem."
            ),
            expected_outcome=(
                "Early feedback that either resolves the problem or narrows it."
            ),
            confidence=0.3,
            risk=RiskLevel.MEDIUM,
            required_capabilities=frozenset({"analysis"}),
        )

        analysis = ProblemAnalysis(
            analysis_id=_stable_uuid(seed, "analysis"),
            problem=problem,
            hypotheses=[primary, secondary],
            candidate_solutions=[first_action, second_action],
            recommended_solution_id=first_action.solution_id,
            confidence=0.3,
            unresolved_questions=[
                "What steps have already been tried?",
                "What would define the problem as successfully solved?",
            ],
        )

        self._logger.info(
            "Fake problem solver analyzed: problem_id=%s analysis_id=%s "
            "hypotheses=%d solutions=%d confidence=%s",
            problem.problem_id,
            analysis.analysis_id,
            len(analysis.hypotheses),
            len(analysis.candidate_solutions),
            analysis.confidence,
        )
        return analysis