import asyncio
from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.core.verification import (
    CONFIDENCE_RANGE_DESCRIPTION,
    Evidence,
    EvidenceKind,
    FakeVerifier,
    ObservedResult,
    VerificationExpectation,
    VerificationResult,
    VerificationStatus,
    Verifier,
    VERIFICATION_NOT_SUCCESS_NOTICE,
)


def expectation(**kwargs: object) -> VerificationExpectation:
    fields: dict[str, object] = {
        "description": "The service responds with HTTP 200.",
    }
    fields.update(kwargs)
    return VerificationExpectation(**fields)


def observation(**kwargs: object) -> ObservedResult:
    fields: dict[str, object] = {
        "description": "Observed HTTP 200 on the health endpoint.",
    }
    fields.update(kwargs)
    return ObservedResult(**fields)


def result(**kwargs: object) -> VerificationResult:
    exp = expectation()
    obs = observation()
    fields: dict[str, object] = {
        "expectation": exp,
        "status": VerificationStatus.VERIFIED,
        "expected_outcome": exp.description,
        "observed_outcome": obs.description,
    }
    fields.update(kwargs)
    return VerificationResult(**fields)


def evidence(**kwargs: object) -> Evidence:
    fields: dict[str, object] = {"description": "The log shows a 200."}
    fields.update(kwargs)
    return Evidence(**fields)


# --- VerificationStatus -----------------------------------------------------


def test_verification_status_values() -> None:
    assert [status.value for status in VerificationStatus] == [
        "verified",
        "failed",
        "inconclusive",
        "not_run",
    ]


def test_evidence_kind_values() -> None:
    assert {kind.value for kind in EvidenceKind} == {
        "fact",
        "observation",
        "assumption",
        "research",
    }


# --- Evidence ---------------------------------------------------------------


def test_evidence_model_fields() -> None:
    item = evidence(
        kind=EvidenceKind.RESEARCH,
        source_ref="https://example.com/research/report",
        confidence=0.7,
    )
    assert isinstance(item.evidence_id, UUID)
    assert item.kind is EvidenceKind.RESEARCH
    assert item.source_ref == "https://example.com/research/report"
    assert item.confidence == 0.7


def test_evidence_defaults() -> None:
    item = evidence()
    assert item.kind is EvidenceKind.OBSERVATION
    assert item.source_ref is None
    assert item.confidence is None


def test_evidence_rejects_blank_description() -> None:
    with pytest.raises(ValidationError, match="description"):
        evidence(description="  ")


def test_evidence_rejects_blank_source_ref() -> None:
    with pytest.raises(ValidationError, match="source_ref"):
        evidence(source_ref="")


def test_evidence_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        evidence(confidence=1.5)


# --- VerificationExpectation ------------------------------------------------


def test_verification_expectation_model_fields() -> None:
    exp = expectation(
        conditions=["HTTP 200", "latency under 500ms"],
        action_ref=UUID(int=5),
        confidence=0.6,
    )
    assert isinstance(exp.expectation_id, UUID)
    assert exp.description == "The service responds with HTTP 200."
    assert exp.conditions == ["HTTP 200", "latency under 500ms"]
    assert exp.action_ref == UUID(int=5)
    assert exp.confidence == 0.6
    assert isinstance(exp.created_at, datetime)


def test_verification_expectation_defaults() -> None:
    exp = expectation()
    assert exp.conditions == []
    assert exp.action_ref is None
    assert exp.confidence is None


def test_verification_expectation_rejects_blank_description() -> None:
    with pytest.raises(ValidationError, match="description"):
        expectation(description="  ")


def test_verification_expectation_rejects_blank_condition() -> None:
    with pytest.raises(ValidationError, match="conditions"):
        expectation(conditions=["ok", ""])


def test_verification_expectation_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        expectation(confidence=2.0)


# --- ObservedResult ---------------------------------------------------------


def test_observed_result_model_fields() -> None:
    item = evidence()
    obs = observation(
        observations=["status code 200", "body is healthy"],
        evidence=[item],
        action_succeeded=True,
    )
    assert isinstance(obs.observation_id, UUID)
    assert obs.observations == ["status code 200", "body is healthy"]
    assert obs.evidence == [item]
    assert obs.action_succeeded is True
    assert isinstance(obs.created_at, datetime)


def test_observed_result_defaults() -> None:
    obs = observation()
    assert obs.observations == []
    assert obs.evidence == []
    assert obs.action_succeeded is None


def test_observed_result_rejects_blank_description() -> None:
    with pytest.raises(ValidationError, match="description"):
        observation(description="")


def test_observed_result_rejects_blank_observation() -> None:
    with pytest.raises(ValidationError, match="observations"):
        observation(observations=["ok", "  "])


# --- VerificationResult -----------------------------------------------------


def test_verification_result_model_fields() -> None:
    exp = expectation()
    obs = observation()
    ver = result(
        expectation=exp,
        evidence=[evidence(kind=EvidenceKind.OBSERVATION)],
        confidence=0.8,
    )
    assert isinstance(ver.result_id, UUID)
    assert ver.expectation is exp
    assert ver.status is VerificationStatus.VERIFIED
    assert ver.expected_outcome == exp.description
    assert ver.observed_outcome == obs.description
    assert ver.evidence
    assert ver.discrepancy is None
    assert ver.confidence == 0.8
    assert ver.error is None
    assert isinstance(ver.created_at, datetime)


def test_verification_result_default_status_is_not_run() -> None:
    ver = VerificationResult(expectation=expectation())
    assert ver.status is VerificationStatus.NOT_RUN


@pytest.mark.parametrize(
    "status",
    [
        VerificationStatus.VERIFIED,
        VerificationStatus.FAILED,
        VerificationStatus.INCONCLUSIVE,
        VerificationStatus.NOT_RUN,
    ],
)
def test_verification_result_accepts_valid_status(status: VerificationStatus) -> None:
    assert result(status=status).status is status


def test_verification_result_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError, match="status"):
        result(status="partial")


def test_verification_result_rejects_blank_expected_outcome() -> None:
    with pytest.raises(ValidationError, match="expected_outcome"):
        result(expected_outcome="  ")


def test_verification_result_rejects_blank_observed_outcome() -> None:
    with pytest.raises(ValidationError, match="observed_outcome"):
        result(observed_outcome="")


def test_verification_result_rejects_blank_discrepancy() -> None:
    with pytest.raises(ValidationError, match="discrepancy"):
        result(
            status=VerificationStatus.FAILED, discrepancy=" "
        )


def test_verification_result_rejects_blank_error() -> None:
    with pytest.raises(ValidationError, match="error"):
        result(error="  ")


def test_verification_result_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        result(confidence=-0.5)


def test_verification_result_verified_cannot_carry_discrepancy() -> None:
    with pytest.raises(ValidationError, match="discrepancy"):
        result(
            status=VerificationStatus.VERIFIED,
            discrepancy="something went off",
        )


def test_verification_result_verified_cannot_carry_error() -> None:
    with pytest.raises(ValidationError, match="error"):
        result(
            status=VerificationStatus.VERIFIED, error="verification crashed"
        )


def test_verification_result_success_properties() -> None:
    assert result().success is True
    assert result().is_verified is True
    assert result().is_failed is False
    failed = result(status=VerificationStatus.FAILED)
    assert failed.success is False
    assert failed.is_failed is True


def test_verification_not_success_notice_wording() -> None:
    assert "without an exception" in VERIFICATION_NOT_SUCCESS_NOTICE


def test_confidence_range_documented() -> None:
    assert "0, 1" in CONFIDENCE_RANGE_DESCRIPTION


# --- Verifier abstraction ---------------------------------------------------


def test_verifier_is_abstract() -> None:
    with pytest.raises(TypeError):
        Verifier()


def test_verifier_requires_metadata() -> None:
    with pytest.raises(TypeError, match="name"):

        class MissingMetadata(Verifier):
            async def verify(
                self,
                exp: VerificationExpectation,
                obs: ObservedResult,
            ) -> VerificationResult:
                return VerificationResult(expectation=exp)


def test_verifier_requires_abstract_method() -> None:
    class MissingMethod(Verifier):
        name = "missing"
        description = "Missing the verify method."

    with pytest.raises(TypeError, match="verify"):
        MissingMethod()


# --- FakeVerifier -----------------------------------------------------------


def test_fake_verifier_satisfies_interface() -> None:
    verifier = FakeVerifier()
    assert isinstance(verifier, Verifier)
    assert verifier.name == "fake-verifier"
    assert verifier.description


def test_fake_verifier_accepts_typed_inputs() -> None:
    exp = expectation()
    obs = observation()
    verified_result = asyncio.run(FakeVerifier().verify(exp, obs))
    assert isinstance(verified_result, VerificationResult)
    assert verified_result.expectation is exp


def test_fake_verifier_is_deterministic() -> None:
    verifier = FakeVerifier()
    exp = expectation(conditions=["HTTP 200"])
    obs = observation(observations=["returned 200"], action_succeeded=True)
    first = asyncio.run(verifier.verify(exp, obs))
    second = asyncio.run(verifier.verify(exp, obs))
    assert first.result_id == second.result_id
    assert first.status == second.status
    assert first.observed_outcome == second.observed_outcome
    assert first.confidence == second.confidence


def test_fake_verifier_verifies_when_condition_is_observed() -> None:
    exp = expectation(conditions=["HTTP 200"])
    obs = observation(
        description="Health endpoint queried.",
        observations=["the server returned HTTP 200"],
        action_succeeded=True,
    )
    verified_result = asyncio.run(FakeVerifier().verify(exp, obs))
    assert verified_result.status is VerificationStatus.VERIFIED
    assert verified_result.success is True
    assert verified_result.discrepancy is None
    assert verified_result.expected_outcome == exp.description
    assert verified_result.observed_outcome == obs.description
    assert verified_result.confidence == 0.8


def test_fake_verifier_verifies_from_observation_lines() -> None:
    exp = expectation(conditions=["file exists"])
    obs = observation(
        description="Listed the directory.",
        observations=["file exists", "size 12 bytes"],
    )
    verified_result = asyncio.run(FakeVerifier().verify(exp, obs))
    assert verified_result.is_verified is True


def test_fake_verifier_fails_when_failure_is_reported() -> None:
    exp = expectation(conditions=["HTTP 200"])
    obs = observation(
        description="The request did not return the expected result.",
        observations=["server failed to respond"],
        action_succeeded=False,
    )
    verified_result = asyncio.run(FakeVerifier().verify(exp, obs))
    assert verified_result.status is VerificationStatus.FAILED
    assert verified_result.is_failed is True
    assert verified_result.discrepancy is not None
    assert verified_result.confidence == 0.6


def test_fake_verifier_failed_action_never_yields_verified() -> None:
    exp = expectation(conditions=["HTTP 200"])
    obs = observation(
        description="Text matches but the action itself failed.",
        observations=["HTTP 200"],
        action_succeeded=False,
    )
    verified_result = asyncio.run(FakeVerifier().verify(exp, obs))
    assert not verified_result.success
    assert verified_result.status is VerificationStatus.FAILED


def test_fake_verifier_inconclusive_without_matching_observation() -> None:
    exp = expectation(conditions=["agent installed"])
    obs = observation(
        description="Nothing conclusive was observed.",
        observations=["ran the installer"],
    )
    verified_result = asyncio.run(FakeVerifier().verify(exp, obs))
    assert verified_result.status is VerificationStatus.INCONCLUSIVE
    assert not verified_result.success
    assert verified_result.discrepancy is None


def test_fake_verifier_action_success_alone_is_not_verification() -> None:
    exp = expectation(conditions=["file exists"])
    obs = observation(
        description="The command completed without an exception.",
        observations=[],
        action_succeeded=True,
    )
    verified_result = asyncio.run(FakeVerifier().verify(exp, obs))
    assert verified_result.is_failed is False
    assert verified_result.is_verified is False
    assert verified_result.status is VerificationStatus.INCONCLUSIVE


def test_fake_verifier_passes_supplied_evidence_through() -> None:
    supplied = evidence(
        kind=EvidenceKind.OBSERVATION,
        source_ref="https://example.com/logs",
    )
    exp = expectation(conditions=["done"])
    obs = observation(
        observations=["done"], evidence=[supplied], action_succeeded=True
    )
    assert obs.evidence == [supplied]
    verified_result = asyncio.run(FakeVerifier().verify(exp, obs))
    sources = [item.source_ref for item in verified_result.evidence]
    assert "https://example.com/logs" in sources
    kinds = {item.kind for item in verified_result.evidence}
    assert EvidenceKind.OBSERVATION in kinds


def test_fake_verifier_never_fabricates_research_evidence() -> None:
    exp = expectation(conditions=["done"])
    obs = observation(observations=["done"], action_succeeded=True)
    verified_result = asyncio.run(FakeVerifier().verify(exp, obs))
    assert all(item.kind is not EvidenceKind.RESEARCH for item in verified_result.evidence)


def test_fake_verifier_records_requests() -> None:
    verifier = FakeVerifier()
    first_exp = expectation()
    first_obs = observation()
    second_exp = expectation(description="A different expected outcome.")
    second_obs = observation(description="A different observation.")
    asyncio.run(verifier.verify(first_exp, first_obs))
    asyncio.run(verifier.verify(second_exp, second_obs))
    assert len(verifier.requests) == 2
    assert verifier.requests[0] == (first_exp, first_obs)
    assert verifier.requests[1] == (second_exp, second_obs)


def test_fake_verifier_can_raise_configured_error() -> None:
    verifier = FakeVerifier(raise_error=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(verifier.verify(expectation(), observation()))


def test_fake_verifier_is_offline() -> None:
    import sys

    module = sys.modules[FakeVerifier.__module__]
    with open(module.__file__, encoding="utf-8") as handle:
        content = handle.read()
    assert "httpx" not in content
    assert "openai" not in content
    assert "subprocess" not in content
    assert "import requests" not in content