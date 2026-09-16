"""Provider-independent prediction and decision-support abstraction.

This module lets MISSMINUTES reason about possible future outcomes and compare
alternatives **without claiming certainty**. Predictions here are decision
support, not fact.

Terminology used throughout:

- **estimated probability**: the predicted likelihood that the stated outcome
  occurs, expressed in ``[0, 1]``. Unless a real calibrated model produced it,
  this is a heuristic ordinal estimate and must not be read as a calibrated
  probability (see ``Prediction.calibrated``).
- **confidence**: how strongly the predictor trusts its own estimate, in
  ``[0, 1]``. Like probability, it is heuristic, not calibrated.
- **risk**: an explicit qualitative-level judgment (low / medium / high /
  unknown).
- **evidence**: a structured statement about what is known, optionally with a
  source reference. Models never fabricate evidence.
- **assumption**: a stated premise an estimate relies on. Assumptions are
  labeled as assumptions, never presented as established fact.

This module is intentionally standalone: it does not depend on any model
provider, database, automation layer, or the problem-solving module.
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROBABILITY_RANGE_DESCRIPTION = (
    "Estimated probabilities are heuristic likelihoods in [0, 1]. "
    "They are not calibrated probabilities unless a calibrated model "
    "produced them."
)
CONFIDENCE_RANGE_DESCRIPTION = (
    "Confidence scores are heuristic ordinal estimates in [0, 1]. "
    "They are not calibrated probabilities."
)
BENEFIT_SCORE_RANGE_DESCRIPTION = (
    "Benefit scores are heuristic ordinal comparisons in [0, 1]; "
    "they are not measured utilities."
)
HEURISTIC_NOTICE = (
    "This is a heuristic estimate based on the supplied information."
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RiskLevel(StrEnum):
    """Explicit representation of how risky an outcome or option is."""

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


class Evidence(BaseModel):
    """A structured statement about what is known.

    ``source_ref`` preserves a reference (for example a research result's URL
    or reference string) so future research results can be attached later.
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


class Prediction(BaseModel):
    """A single predicted possible outcome.

    ``probability`` and ``confidence`` are heuristic estimates unless
    ``calibrated`` is True (which only a real calibrated model may set).
    ``evidence_refs`` carry references to where supporting evidence came from;
    they are never fabricated.
    """

    model_config = ConfigDict(validate_assignment=True)

    prediction_id: UUID = Field(default_factory=uuid4)
    outcome: str
    probability: float | None = None
    confidence: float | None = None
    risk: RiskLevel = RiskLevel.UNKNOWN
    assumptions: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    calibrated: bool = False

    @field_validator("outcome")
    @classmethod
    def _outcome_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("outcome must not be blank")
        return value

    @field_validator("probability")
    @classmethod
    def _probability_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("probability must be between 0 and 1")
        return value

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @field_validator("assumptions", "evidence_refs")
    @classmethod
    def _strings_not_blank(
        cls, value: list[str],
    ) -> list[str]:
        for item in value:
            if not item.strip():
                raise ValueError("entries must not be blank")
        return value


class DecisionOption(BaseModel):
    """An available option/action with its predicted outcomes and risk.

    ``benefit_score`` is a heuristic ordinal comparison, not a measured
    utility. ``required_capabilities`` lists capabilities or tools the action
    would need; ordering is not significant, so it uses an immutable frozenset.
    """

    model_config = ConfigDict(validate_assignment=True)

    option_id: UUID = Field(default_factory=uuid4)
    description: str
    predicted_outcomes: list[str] = Field(default_factory=list)
    benefit_score: float | None = None
    risk: RiskLevel = RiskLevel.UNKNOWN
    risk_note: str | None = None
    required_capabilities: frozenset[str] = Field(default_factory=frozenset)

    @field_validator("description")
    @classmethod
    def _description_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description must not be blank")
        return value

    @field_validator("predicted_outcomes")
    @classmethod
    def _outcomes_not_blank(cls, value: list[str]) -> list[str]:
        for item in value:
            if not item.strip():
                raise ValueError("predicted outcomes must not be blank")
        return value

    @field_validator("benefit_score")
    @classmethod
    def _benefit_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("benefit_score must be between 0 and 1")
        return value

    @field_validator("risk_note")
    @classmethod
    def _risk_note_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("risk_note must not be blank")
        return value

    @field_validator("required_capabilities")
    @classmethod
    def _capabilities_not_blank(cls, value: frozenset[str]) -> frozenset[str]:
        for capability in value:
            if not capability.strip():
                raise ValueError("required capabilities must not be blank")
        return value


class PredictionRequest(BaseModel):
    """Typed input for a prediction.

    ``situation`` carries the current state; ``horizon`` is an optional
    timeframe for the estimate; ``candidate_options`` are optional suggested
    actions to evaluate (the predictor may also propose its own).
    """

    model_config = ConfigDict(validate_assignment=True)

    request_id: UUID = Field(default_factory=uuid4)
    question: str
    situation: dict[str, Any] = Field(default_factory=dict)
    horizon: str | None = None
    candidate_options: list[str] = Field(default_factory=list)

    @field_validator("question")
    @classmethod
    def _question_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value

    @field_validator("horizon")
    @classmethod
    def _horizon_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("horizon must not be blank")
        return value

    @field_validator("candidate_options")
    @classmethod
    def _options_not_blank(cls, value: list[str]) -> list[str]:
        for option in value:
            if not option.strip():
                raise ValueError("candidate options must not be blank")
        return value


class DecisionAnalysis(BaseModel):
    """Typed prediction and decision-support result.

    The analysis carries predicted outcomes, candidate options, an optional
    recommendation, uncertainty/limitations, and unresolved questions. It is
    decision support, not certainty, and never triggers actions by itself.
    """

    model_config = ConfigDict(validate_assignment=True)

    analysis_id: UUID = Field(default_factory=uuid4)
    request: PredictionRequest
    predictions: list[Prediction] = Field(default_factory=list)
    candidate_options: list[DecisionOption] = Field(default_factory=list)
    recommended_option_id: UUID | None = None
    recommendation_rationale: str | None = None
    uncertainty: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    confidence: float | None = None
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("recommendation_rationale")
    @classmethod
    def _rationale_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("recommendation_rationale must not be blank")
        return value

    @field_validator("uncertainty", "unresolved_questions")
    @classmethod
    def _notes_not_blank(cls, value: list[str]) -> list[str]:
        for item in value:
            if not item.strip():
                raise ValueError("entries must not be blank")
        return value

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @model_validator(mode="after")
    def _recommendation_must_be_option(self) -> "DecisionAnalysis":
        if self.recommended_option_id is not None:
            option_ids = {
                option.option_id for option in self.candidate_options
            }
            if self.recommended_option_id not in option_ids:
                raise ValueError(
                    "recommended option must refer to a candidate option"
                )
        return self

    @property
    def situation(self) -> dict[str, Any]:
        """The current situation the analysis reasons over."""
        return self.request.situation

    @property
    def recommended_option(self) -> "DecisionOption | None":
        """The recommended candidate option, if a recommendation exists."""
        if self.recommended_option_id is None:
            return None
        for option in self.candidate_options:
            if option.option_id == self.recommended_option_id:
                return option
        return None

    @property
    def assumptions(self) -> tuple[str, ...]:
        """All unique assumptions stated by the included predictions."""
        seen: list[str] = []
        for prediction in self.predictions:
            for assumption in prediction.assumptions:
                if assumption not in seen:
                    seen.append(assumption)
        return tuple(seen)


class Predictor(ABC):
    """Provider-independent prediction and decision-support interface.

    A predictor accepts a ``PredictionRequest`` and returns a typed
    ``DecisionAnalysis``. Implementations are expected to be independent of any
    AI model provider, database, computer automation, and browser automation.
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
    async def predict(self, request: PredictionRequest) -> DecisionAnalysis:
        raise NotImplementedError


def _stable_uuid(*parts: str) -> UUID:
    """Deterministic UUID from string parts (for the deterministic fake)."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return UUID(digest[:32])


class FakePredictor(Predictor):
    """Deterministic prediction fake for offline tests.

    The fake accepts any prediction request, never touches the network, never
    calls an LLM, and does not special-case any single question. Given the same
    request it returns the same predictions, options, recommendation, and
    confidence. Probabilities and confidences are always heuristic: the fake
    never sets ``calibrated`` to True and always documents the uncertainty.
    """

    name = "fake-predictor"
    description = "Deterministic heuristic prediction fake for offline tests."

    def __init__(self, raise_error: Exception | None = None) -> None:
        self._raise_error = raise_error
        self._requests: list[PredictionRequest] = []
        self._logger = logging.getLogger(__name__)

    @property
    def requests(self) -> tuple[PredictionRequest, ...]:
        return tuple(self._requests)

    async def predict(self, request: PredictionRequest) -> DecisionAnalysis:
        self._requests.append(request)
        if self._raise_error is not None:
            self._logger.error(
                "Fake predictor raising: %s", type(self._raise_error).__name__
            )
            raise self._raise_error

        seed = request.question.strip()
        favourable = Prediction(
            prediction_id=_stable_uuid(seed, "prediction:favourable"),
            outcome=(
                f"'{request.question}' proceeds with no major disruption "
                "(heuristic estimate)."
            ),
            probability=0.55,
            confidence=0.5,
            risk=RiskLevel.LOW,
            assumptions=[
                "The supplied situation is accurate.",
                "Conditions relevant to the question remain broadly stable.",
            ],
        )
        complications = Prediction(
            prediction_id=_stable_uuid(seed, "prediction:complications"),
            outcome=(
                f"'{request.question}' encounters material complications "
                "(heuristic estimate)."
            ),
            probability=0.35,
            confidence=0.4,
            risk=RiskLevel.MEDIUM,
            assumptions=[
                "Future conditions may differ from the current situation.",
                "The estimate relies only on information in the request.",
            ],
        )

        option_texts = list(request.candidate_options) or [
            "Proceed with the most favorable course given the estimated "
            "likelihood.",
            "Gather more information before committing to a course.",
        ]
        options: list[DecisionOption] = []
        for index, text in enumerate(option_texts):
            options.append(
                DecisionOption(
                    option_id=_stable_uuid(seed, f"option:{index}"),
                    description=text,
                    predicted_outcomes=[
                        f"Outcome for option {index + 1} is estimated "
                        "heuristically (no guarantee)."
                    ],
                    benefit_score=round(max(0.6 - 0.1 * index, 0.1), 2),
                    risk=RiskLevel.LOW if index == 0 else RiskLevel.MEDIUM,
                    required_capabilities=frozenset(
                        {"analysis"} if index == 0 else {"research"}
                    ),
                )
            )

        analysis = DecisionAnalysis(
            analysis_id=_stable_uuid(seed, "analysis"),
            request=request,
            predictions=[favourable, complications],
            candidate_options=options,
            recommended_option_id=options[0].option_id,
            recommendation_rationale=(
                "The option with the highest estimated benefit and lowest "
                "estimated risk is recommended."
            ),
            uncertainty=[
                HEURISTIC_NOTICE,
                "Estimated probabilities and confidence are heuristic and are "
                "not calibrated.",
            ],
            unresolved_questions=[
                "What additional information could reduce uncertainty?",
            ],
            confidence=0.4,
        )

        self._logger.info(
            "Fake predictor analyzed: request_id=%s analysis_id=%s "
            "predictions=%d options=%d confidence=%s "
            "recommended=%s",
            request.request_id,
            analysis.analysis_id,
            len(analysis.predictions),
            len(analysis.candidate_options),
            analysis.confidence,
            analysis.recommended_option_id is not None,
        )
        return analysis