import asyncio
from datetime import datetime
from uuid import UUID

import pytest
from app.core.critic import (
    CONFIDENCE_RANGE_DESCRIPTION,
    CRITIQUE_IS_ESTIMATE_NOTICE,
    Critic,
    Critique,
    CritiqueAspect,
    CritiquePoint,
    CritiqueRequest,
    FakeCritic,
    Severity,
)
from pydantic import ValidationError


def point(**kwargs: object) -> CritiquePoint:
    fields: dict[str, object] = {
        "aspect": CritiqueAspect.WEAKNESS,
        "description": "the target depends on untested assumptions",
    }
    fields.update(kwargs)
    return CritiquePoint(**fields)


def request(**kwargs: object) -> CritiqueRequest:
    fields: dict[str, object] = {
        "target": "Proposed solution: retry the database connection.",
    }
    fields.update(kwargs)
    return CritiqueRequest(**fields)


def critique(**kwargs: object) -> Critique:
    pts = point()
    fields: dict[str, object] = {
        "target": "Proposed solution: retry the database connection.",
        "points": [pts],
    }
    fields.update(kwargs)
    return Critique(**fields)


# --- Severity and aspects ---------------------------------------------------


def test_severity_values() -> None:
    assert [severity.value for severity in Severity] == [
        "low",
        "medium",
        "high",
        "critical",
        "unknown",
    ]


def test_critique_aspect_values() -> None:
    assert {aspect.value for aspect in CritiqueAspect} == {
        "weakness",
        "risk",
        "unsupported_assumption",
        "missing_evidence",
        "contradiction",
        "alternative_explanation",
    }


@pytest.mark.parametrize(
    "severity",
    [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL],
)
def test_critique_point_accepts_valid_severity(severity: Severity) -> None:
    assert point(severity=severity).severity is severity


def test_critique_point_rejects_invalid_severity() -> None:
    with pytest.raises(ValidationError, match="severity"):
        point(severity="severe")


# --- CritiquePoint ----------------------------------------------------------


def test_critique_point_model_fields() -> None:
    item = point(
        severity=Severity.HIGH,
        confidence=0.6,
        suggestion="gather evidence before proceeding",
        evidence_refs=["https://example.com/research/report"],
    )
    assert isinstance(item.point_id, UUID)
    assert item.aspect is CritiqueAspect.WEAKNESS
    assert item.description
    assert item.severity is Severity.HIGH
    assert item.confidence == 0.6
    assert item.suggestion == "gather evidence before proceeding"
    assert item.evidence_refs == ["https://example.com/research/report"]


def test_critique_point_defaults() -> None:
    item = point()
    assert item.severity is Severity.UNKNOWN
    assert item.confidence is None
    assert item.suggestion is None
    assert item.evidence_refs == []


def test_critique_point_rejects_blank_description() -> None:
    with pytest.raises(ValidationError, match="description"):
        point(description="  ")


def test_critique_point_rejects_blank_suggestion() -> None:
    with pytest.raises(ValidationError, match="suggestion"):
        point(suggestion="")


def test_critique_point_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        point(confidence=1.2)


def test_critique_point_rejects_blank_evidence_ref() -> None:
    with pytest.raises(ValidationError, match="evidence refs"):
        point(evidence_refs=["ok", "  "])


# --- CritiqueRequest --------------------------------------------------------


def test_critique_request_fields() -> None:
    req = request(
        context={"service": "db"},
        supporting_evidence_refs=["https://example.com/research/report"],
    )
    assert isinstance(req.request_id, UUID)
    assert req.target.startswith("Proposed solution:")
    assert req.context == {"service": "db"}
    assert req.supporting_evidence_refs == ["https://example.com/research/report"]
    assert isinstance(req.created_at, datetime)


def test_critique_request_defaults() -> None:
    req = request()
    assert req.context == {}
    assert req.supporting_evidence_refs == []


def test_critique_request_rejects_blank_target() -> None:
    with pytest.raises(ValidationError, match="target"):
        request(target="")


def test_critique_request_rejects_blank_evidence_ref() -> None:
    with pytest.raises(ValidationError, match="evidence refs"):
        request(supporting_evidence_refs=["https://example.com/a", ""])


# --- Critique ---------------------------------------------------------------


def test_critique_model_fields() -> None:
    result = critique(
        summary="A summary of the review.",
        overall_severity=Severity.HIGH,
        confidence=0.6,
        notes=["note one"],
        unresolved_questions=["what evidence exists?"],
    )
    assert isinstance(result.critique_id, UUID)
    assert result.points
    assert result.summary == "A summary of the review."
    assert result.overall_severity is Severity.HIGH
    assert result.confidence == 0.6
    assert result.notes == ["note one"]
    assert result.unresolved_questions == ["what evidence exists?"]
    assert isinstance(result.created_at, datetime)


def test_critique_defaults() -> None:
    result = Critique(target="a target without points")
    assert result.points == []
    assert result.summary is None
    assert result.overall_severity is Severity.UNKNOWN
    assert result.confidence is None
    assert result.notes == []
    assert result.unresolved_questions == []


def test_critique_rejects_blank_target() -> None:
    with pytest.raises(ValidationError, match="target"):
        critique(target="  ")


def test_critique_rejects_blank_summary() -> None:
    with pytest.raises(ValidationError, match="summary"):
        critique(summary="")


def test_critique_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        critique(confidence=-0.1)


def test_critique_rejects_blank_note() -> None:
    with pytest.raises(ValidationError, match="entries"):
        critique(notes=["ok", "  "])


def test_critique_rejects_blank_unresolved_question() -> None:
    with pytest.raises(ValidationError, match="entries"):
        critique(unresolved_questions=[" "])


def test_critique_groups_points_by_aspect() -> None:
    weakness = point(aspect=CritiqueAspect.WEAKNESS)
    risk = point(aspect=CritiqueAspect.RISK, description="a risk statement")
    assumption = point(
        aspect=CritiqueAspect.UNSUPPORTED_ASSUMPTION,
        description="an assumption statement",
    )
    missing = point(
        aspect=CritiqueAspect.MISSING_EVIDENCE,
        description="evidence is missing",
    )
    contradiction = point(
        aspect=CritiqueAspect.CONTRADICTION,
        description="two statements conflict",
    )
    alternative = point(
        aspect=CritiqueAspect.ALTERNATIVE_EXPLANATION,
        description="an alternative exists",
    )
    result = critique(points=[weakness, risk, assumption, missing, contradiction, alternative])
    assert result.weaknesses == (weakness,)
    assert result.risks == (risk,)
    assert result.unsupported_assumptions == (assumption,)
    assert result.missing_evidence == (missing,)
    assert result.contradictions == (contradiction,)
    assert result.alternative_explanations == (alternative,)


def test_critique_highest_severity() -> None:
    result = critique(
        points=[
            point(severity=Severity.LOW),
            point(
                aspect=CritiqueAspect.RISK,
                description="a risk",
                severity=Severity.CRITICAL,
            ),
        ]
    )
    assert result.highest_severity is Severity.CRITICAL


def test_critique_highest_severity_from_overall_when_empty() -> None:
    result = critique(points=[], overall_severity=Severity.UNKNOWN)
    assert result.highest_severity is Severity.UNKNOWN


def test_confidence_range_documented() -> None:
    assert "0, 1" in CONFIDENCE_RANGE_DESCRIPTION


# --- Critic abstraction -----------------------------------------------------


def test_critic_is_abstract() -> None:
    with pytest.raises(TypeError):
        Critic()


def test_critic_requires_metadata() -> None:
    with pytest.raises(TypeError, match="name"):

        class MissingMetadata(Critic):
            async def critique(self, req: CritiqueRequest) -> Critique:
                return Critique(target=req.target)


def test_critic_requires_abstract_method() -> None:
    class MissingMethod(Critic):
        name = "missing"
        description = "Missing the critique method."

    with pytest.raises(TypeError, match="critique"):
        MissingMethod()


def test_critic_metadata_enforced_on_subclass() -> None:
    class MetaCritic(Critic):
        name = "meta-critic"
        description = "A critic with metadata."

        async def critique(self, req: CritiqueRequest) -> Critique:
            return Critique(target=req.target)

    assert MetaCritic.name == "meta-critic"
    assert MetaCritic.description
    result = asyncio.run(MetaCritic().critique(request()))
    assert result.target == request().target


# --- FakeCritic -------------------------------------------------------------


def test_fake_critic_satisfies_interface() -> None:
    critic = FakeCritic()
    assert isinstance(critic, Critic)
    assert critic.name == "fake-critic"
    assert critic.description


def test_fake_critic_accepts_arbitrary_target() -> None:
    result = asyncio.run(FakeCritic().critique(request()))
    assert isinstance(result, Critique)
    assert result.target == request().target


def test_fake_critic_reports_all_expected_aspects() -> None:
    result = asyncio.run(FakeCritic().critique(request()))
    assert len(result.weaknesses) >= 1
    assert len(result.risks) >= 1
    assert len(result.unsupported_assumptions) >= 1
    assert len(result.missing_evidence) >= 1
    assert len(result.alternative_explanations) >= 1


def test_fake_critic_is_deterministic() -> None:
    critic = FakeCritic()
    first = asyncio.run(critic.critique(request()))
    second = asyncio.run(critic.critique(request()))
    assert first.critique_id == second.critique_id
    assert [(p.aspect, p.severity) for p in first.points] == [
        (p.aspect, p.severity) for p in second.points
    ]
    assert first.overall_severity == second.overall_severity
    assert first.confidence == second.confidence
    assert first.unresolved_questions == second.unresolved_questions


def test_fake_critic_is_not_hardcoded_to_one_problem() -> None:
    critic = FakeCritic()
    first = asyncio.run(critic.critique(request(target="Target about the database.")))
    second = asyncio.run(critic.critique(request(target="Completely different target text.")))
    assert first.critique_id != second.critique_id
    assert first.target != second.target
    assert [p.aspect for p in first.points] == [p.aspect for p in second.points]


def test_fake_critic_marks_own_output_as_estimate() -> None:
    result = asyncio.run(FakeCritic().critique(request()))
    assert CRITIQUE_IS_ESTIMATE_NOTICE in result.notes
    assert result.summary


def test_fake_critic_never_claims_fact_or_fabricates_evidence() -> None:
    result = asyncio.run(FakeCritic().critique(request()))
    for item in result.points:
        assert item.confidence is None or 0.0 <= item.confidence <= 1.0
        assert item.evidence_refs == []
    assert any(item.severity in (Severity.LOW, Severity.MEDIUM) for item in result.points)
    assert result.confidence is not None and 0.0 <= result.confidence <= 1.0


def test_fake_critic_records_requests() -> None:
    critic = FakeCritic()
    first = request()
    second = request(target="Another target to examine.")
    asyncio.run(critic.critique(first))
    asyncio.run(critic.critique(second))
    assert len(critic.requests) == 2
    assert critic.requests[0] is first
    assert critic.requests[1] is second


def test_fake_critic_can_raise_configured_error() -> None:
    critic = FakeCritic(raise_error=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(critic.critique(request()))


def test_fake_critic_is_offline() -> None:
    import sys

    module = sys.modules[FakeCritic.__module__]
    with open(module.__file__, encoding="utf-8") as handle:
        content = handle.read()
    assert "httpx" not in content
    assert "openai" not in content
    assert "import requests" not in content
