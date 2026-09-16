"""Provider-independent action-verification abstraction.

After an action runs, the system must not assume it succeeded merely because
the action returned without an exception. This module defines typed models for
*what should happen* (``VerificationExpectation``), *what was observed*
(``ObservedResult``), and *whether the expectation was met*
(``VerificationResult``), plus a provider-independent ``Verifier`` interface.

Terminology used throughout:

- **expectation**: a description of what should happen after an action.
- **observation**: what was actually observed, supplied by the caller.
- **verification**: the judgment that the observed outcome matches the
  expectation. ``action_succeeded`` on an observation is informational only and
  must never by itself turn a verification into ``verified``.
- **evidence**: structured statements about observations or external material
  (such as future research results); verification never fabricates evidence.

Confidence is a heuristic ordinal score in ``[0, 1]``, never a calibrated
probability unless a calibrated model produced it.
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from enum import StrEnum
from typing import ClassVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONFIDENCE_RANGE_DESCRIPTION = (
    "Confidence scores are heuristic ordinal estimates in [0, 1]. "
    "They are not calibrated probabilities."
)
VERIFICATION_NOT_SUCCESS_NOTICE = (
    "Verification checks the observed outcome against the expectation; it is "
    "not satisfied merely by an action returning without an exception."
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class VerificationStatus(StrEnum):
    """Whether a verification expectation has been satisfied."""

    VERIFIED = "verified"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    NOT_RUN = "not_run"


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


class VerificationExpectation(BaseModel):
    """What should happen after an action.

    ``description`` states the expected outcome; ``conditions`` lists specific
    observable facts to check. ``action_ref`` optionally points back to the
    action or solution this expectation belongs to.
    """

    model_config = ConfigDict(validate_assignment=True)

    expectation_id: UUID = Field(default_factory=uuid4)
    description: str
    conditions: list[str] = Field(default_factory=list)
    action_ref: UUID | None = None
    confidence: float | None = None
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("description")
    @classmethod
    def _description_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description must not be blank")
        return value

    @field_validator("conditions")
    @classmethod
    def _conditions_not_blank(cls, value: list[str]) -> list[str]:
        for condition in value:
            if not condition.strip():
                raise ValueError("conditions must not be blank")
        return value

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value


class ObservedResult(BaseModel):
    """What was actually observed after an action.

    ``observations`` carries granular observed facts supplied by the caller
    (for example tool output, logs, or screenshot text); ``evidence`` carries
    structured evidence, never fabricated. ``action_succeeded`` records whether
    the action completed without an exception: it is purely informational and
    must not be treated as verification on its own.
    """

    model_config = ConfigDict(validate_assignment=True)

    observation_id: UUID = Field(default_factory=uuid4)
    description: str
    observations: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    action_succeeded: bool | None = None
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("description")
    @classmethod
    def _description_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description must not be blank")
        return value

    @field_validator("observations")
    @classmethod
    def _observations_not_blank(cls, value: list[str]) -> list[str]:
        for observation in value:
            if not observation.strip():
                raise ValueError("observations must not be blank")
        return value


class VerificationResult(BaseModel):
    """Typed result of verifying an expectation against an observation.

    ``status`` is one of ``VerificationStatus``; ``discrepancy`` describes the
    gap when one is identified; ``evidence`` carries anything observed or
    supplied, never fabricated. A result is only ``verified`` when the observed
    outcome matches the expectation, never merely because ``action_succeeded``
    was true.
    """

    model_config = ConfigDict(validate_assignment=True)

    result_id: UUID = Field(default_factory=uuid4)
    expectation: VerificationExpectation
    status: VerificationStatus = VerificationStatus.NOT_RUN
    expected_outcome: str | None = None
    observed_outcome: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    discrepancy: str | None = None
    confidence: float | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("expected_outcome", "observed_outcome", "discrepancy", "error")
    @classmethod
    def _optional_text_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @model_validator(mode="after")
    def _verified_must_not_claim_discrepancy(self) -> "VerificationResult":
        if self.status is VerificationStatus.VERIFIED and (
            self.discrepancy is not None or self.error is not None
        ):
            raise ValueError(
                "a verified result cannot carry a discrepancy or error"
            )
        return self

    @property
    def success(self) -> bool:
        """True when the expectation was verified against the observation."""
        return self.status is VerificationStatus.VERIFIED

    @property
    def is_verified(self) -> bool:
        return self.success

    @property
    def is_failed(self) -> bool:
        return self.status is VerificationStatus.FAILED


class Verifier(ABC):
    """Provider-independent verification interface.

    A verifier accepts an ``VerificationExpectation`` plus an
    ``ObservedResult`` and returns a typed ``VerificationResult``.
    Implementations are expected to be independent of any AI model provider,
    research provider, browser/desktop automation, network, and database.
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
    async def verify(
        self, expectation: VerificationExpectation, observation: ObservedResult
    ) -> VerificationResult:
        raise NotImplementedError


def _stable_uuid(*parts: str) -> UUID:
    """Deterministic UUID from string parts (for the deterministic fake)."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return UUID(digest[:32])


class FakeVerifier(Verifier):
    """Deterministic verification fake for offline tests.

    The fake never accesses the computer or the network and never calls an LLM.
    It decides deterministically from the supplied texts:

    - ``verified`` when every expected condition is present in the
      observation;
    - ``failed`` when the observation reports failure and no expected
      condition is present;
    - ``inconclusive`` otherwise.

    ``action_succeeded`` is only ever read as a signal of failure when false;
    a true value never by itself produces ``verified``.
    """

    name = "fake-verifier"
    description = (
        "Deterministic heuristic verification fake for offline tests."
    )

    _FAILURE_MARKERS = ("did not", "failed", "unsuccessful", "not observed")

    def __init__(self, raise_error: Exception | None = None) -> None:
        self._raise_error = raise_error
        self._requests: list[tuple[VerificationExpectation, ObservedResult]] = []
        self._logger = logging.getLogger(__name__)

    @property
    def requests(
        self,
    ) -> tuple[tuple[VerificationExpectation, ObservedResult], ...]:
        return tuple(self._requests)

    async def verify(
        self, expectation: VerificationExpectation, observation: ObservedResult
    ) -> VerificationResult:
        self._requests.append((expectation, observation))
        if self._raise_error is not None:
            self._logger.error(
                "Fake verifier raising: %s", type(self._raise_error).__name__
            )
            raise self._raise_error

        seed = expectation.description.strip()
        conditions = [
            condition.lower() for condition in expectation.conditions
        ]
        expected_block = " ".join(
            [expectation.description, *expectation.conditions]
        ).lower()
        observed_block = " ".join(
            [observation.description, *observation.observations]
        ).lower()

        if observation.action_succeeded is False:
            status = VerificationStatus.FAILED
        elif any(
            condition in observed_block
            for condition in conditions or [expected_block]
        ):
            status = VerificationStatus.VERIFIED
        elif any(marker in observed_block for marker in self._FAILURE_MARKERS):
            status = VerificationStatus.FAILED
        else:
            status = VerificationStatus.INCONCLUSIVE

        confidence = {
            VerificationStatus.VERIFIED: 0.8,
            VerificationStatus.FAILED: 0.6,
            VerificationStatus.INCONCLUSIVE: 0.4,
            VerificationStatus.NOT_RUN: None,
        }[status]

        discrepancy = None
        if status is VerificationStatus.FAILED:
            discrepancy = (
                f"Expected '{expectation.description[:120]}' but the "
                "observation does not confirm it."
            )

        evidence = list(observation.evidence)
        evidence.append(
            Evidence(
                evidence_id=_stable_uuid(seed, "evidence:observed"),
                description=f"Observed: '{observation.description[:200]}'",
                kind=EvidenceKind.OBSERVATION,
            )
        )
        if not observation.observations:
            evidence.append(
                Evidence(
                    evidence_id=_stable_uuid(seed, "evidence:no-detail"),
                    description=(
                        "The observation carried no granular observed facts."
                    ),
                    kind=EvidenceKind.OBSERVATION,
                )
            )

        result = VerificationResult(
            result_id=_stable_uuid(seed, "verification"),
            expectation=expectation,
            status=status,
            expected_outcome=expectation.description,
            observed_outcome=observation.description,
            evidence=evidence,
            discrepancy=discrepancy,
            confidence=confidence,
        )

        self._logger.info(
            "Fake verifier checked: expectation_id=%s observation_id=%s "
            "status=%s confidence=%s evidence=%d",
            expectation.expectation_id,
            observation.observation_id,
            result.status,
            result.confidence,
            len(result.evidence),
        )
        return result