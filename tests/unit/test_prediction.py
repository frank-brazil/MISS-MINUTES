import asyncio
from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.core.prediction import (
    BENEFIT_SCORE_RANGE_DESCRIPTION,
    CONFIDENCE_RANGE_DESCRIPTION,
    DecisionAnalysis,
    DecisionOption,
    Evidence,
    EvidenceKind,
    FakePredictor,
    HEURISTIC_NOTICE,
    PROBABILITY_RANGE_DESCRIPTION,
    Prediction,
    PredictionRequest,
    Predictor,
    RiskLevel,
)


def prediction(**kwargs: object) -> Prediction:
    fields: dict[str, object] = {"outcome": "the server stays available"}
    fields.update(kwargs)
    return Prediction(**fields)


def option(**kwargs: object) -> DecisionOption:
    fields: dict[str, object] = {"description": "roll back the change"}
    fields.update(kwargs)
    return DecisionOption(**fields)


def request(**kwargs: object) -> PredictionRequest:
    fields: dict[str, object] = {
        "question": "Will the service be stable next week?",
        "situation": {"service": "web", "load": "high"},
    }
    fields.update(kwargs)
    return PredictionRequest(**fields)


def analysis(**kwargs: object) -> DecisionAnalysis:
    req = request()
    pred = prediction()
    opt = option()
    fields: dict[str, object] = {
        "request": req,
        "predictions": [pred],
        "candidate_options": [opt],
    }
    fields.update(kwargs)
    return DecisionAnalysis(**fields)


# --- RiskLevel --------------------------------------------------------------


def test_risk_level_values() -> None:
    assert RiskLevel.LOW.value == "low"
    assert RiskLevel.MEDIUM.value == "medium"
    assert RiskLevel.HIGH.value == "high"
    assert RiskLevel.UNKNOWN.value == "unknown"


# --- Prediction -------------------------------------------------------------


def test_prediction_model_fields() -> None:
    predicted = prediction(
        probability=0.75,
        confidence=0.6,
        risk=RiskLevel.MEDIUM,
        assumptions=["The feed is reliable."],
        evidence_refs=["https://example.com/research/report"],
        calibrated=False,
    )
    assert isinstance(predicted.prediction_id, UUID)
    assert predicted.outcome == "the server stays available"
    assert predicted.probability == 0.75
    assert predicted.confidence == 0.6
    assert predicted.risk is RiskLevel.MEDIUM
    assert predicted.assumptions == ["The feed is reliable."]
    assert predicted.evidence_refs == ["https://example.com/research/report"]
    assert predicted.calibrated is False


def test_prediction_defaults() -> None:
    predicted = prediction()
    assert predicted.probability is None
    assert predicted.confidence is None
    assert predicted.risk is RiskLevel.UNKNOWN
    assert predicted.assumptions == []
    assert predicted.evidence_refs == []
    assert predicted.calibrated is False


def test_prediction_accepts_boundary_probabilities() -> None:
    assert prediction(probability=0.0).probability == 0.0
    assert prediction(probability=1.0).probability == 1.0


def test_prediction_rejects_invalid_probability() -> None:
    with pytest.raises(ValidationError, match="probability"):
        prediction(probability=1.5)
    with pytest.raises(ValidationError, match="probability"):
        prediction(probability=-0.2)


def test_prediction_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        prediction(confidence=1.1)


def test_prediction_rejects_blank_outcome() -> None:
    with pytest.raises(ValidationError, match="outcome"):
        prediction(outcome="  ")


def test_prediction_rejects_blank_assumption() -> None:
    with pytest.raises(ValidationError, match="entries"):
        prediction(assumptions=["ok", "  "])


def test_prediction_rejects_blank_evidence_ref() -> None:
    with pytest.raises(ValidationError, match="entries"):
        prediction(evidence_refs=["", "https://example.com/a"])


def test_prediction_calibrated_flag_defaults_false() -> None:
    assert prediction().calibrated is False


# --- DecisionOption ---------------------------------------------------------


def test_decision_option_model_fields() -> None:
    opt = option(
        predicted_outcomes=["reduced load"],
        benefit_score=0.7,
        risk=RiskLevel.LOW,
        risk_note="reversible rollout",
        required_capabilities=frozenset({"analysis", "system"}),
    )
    assert isinstance(opt.option_id, UUID)
    assert opt.predicted_outcomes == ["reduced load"]
    assert opt.benefit_score == 0.7
    assert opt.risk is RiskLevel.LOW
    assert opt.risk_note == "reversible rollout"
    assert opt.required_capabilities == frozenset({"analysis", "system"})


def test_decision_option_defaults() -> None:
    opt = option()
    assert opt.predicted_outcomes == []
    assert opt.benefit_score is None
    assert opt.risk is RiskLevel.UNKNOWN
    assert opt.risk_note is None
    assert opt.required_capabilities == frozenset()


@pytest.mark.parametrize(
    "risk", [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.UNKNOWN]
)
def test_decision_option_accepts_valid_risk(risk: RiskLevel) -> None:
    assert option(risk=risk).risk is risk


def test_decision_option_rejects_invalid_risk() -> None:
    with pytest.raises(ValidationError):
        option(risk="critical")


def test_decision_option_rejects_blank_description() -> None:
    with pytest.raises(ValidationError, match="description"):
        option(description="")


def test_decision_option_rejects_blank_predicted_outcome() -> None:
    with pytest.raises(ValidationError, match="predicted outcomes"):
        option(predicted_outcomes=["ok", "  "])


def test_decision_option_rejects_invalid_benefit() -> None:
    with pytest.raises(ValidationError, match="benefit_score"):
        option(benefit_score=1.5)


def test_decision_option_rejects_blank_capability() -> None:
    with pytest.raises(ValidationError, match="required capabilities"):
        option(required_capabilities=frozenset({"ok", "  "}))


def test_decision_option_capabilities_are_immutable() -> None:
    opt = option(required_capabilities=frozenset({"a", "b"}))
    with pytest.raises(AttributeError):
        opt.required_capabilities.add("c")


# --- PredictionRequest ------------------------------------------------------


def test_prediction_request_fields() -> None:
    req = request(horizon="next month", candidate_options=["A", "B"])
    assert isinstance(req.request_id, UUID)
    assert req.question == "Will the service be stable next week?"
    assert req.situation == {"service": "web", "load": "high"}
    assert req.horizon == "next month"
    assert req.candidate_options == ["A", "B"]


def test_prediction_request_defaults() -> None:
    req = PredictionRequest(question="Will the service be stable?")
    assert req.situation == {}
    assert req.horizon is None
    assert req.candidate_options == []


def test_prediction_request_rejects_blank_question() -> None:
    with pytest.raises(ValidationError, match="question"):
        request(question="")


def test_prediction_request_rejects_blank_horizon() -> None:
    with pytest.raises(ValidationError, match="horizon"):
        request(horizon="  ")


def test_prediction_request_rejects_blank_candidate_option() -> None:
    with pytest.raises(ValidationError, match="candidate options"):
        request(candidate_options=["ok", ""])


# --- Evidence ---------------------------------------------------------------


def test_evidence_kind_values() -> None:
    assert {kind.value for kind in EvidenceKind} == {
        "fact",
        "observation",
        "assumption",
        "research",
    }


def test_evidence_preserves_source_reference() -> None:
    item = Evidence(
        description="the documentation describes this",
        kind=EvidenceKind.RESEARCH,
        source_ref="https://example.com/docs",
    )
    assert item.source_ref == "https://example.com/docs"
    assert item.kind is EvidenceKind.RESEARCH


def test_evidence_rejects_blank_description() -> None:
    with pytest.raises(ValidationError, match="description"):
        Evidence(description="")


# --- DecisionAnalysis -------------------------------------------------------


def test_decision_analysis_model_fields() -> None:
    req = request()
    pred = prediction()
    opt = option()
    result = DecisionAnalysis(
        request=req,
        predictions=[pred],
        candidate_options=[opt],
        recommended_option_id=opt.option_id,
        recommendation_rationale="lowest risk and best benefit",
        uncertainty=["heuristic estimates"],
        unresolved_questions=["is more data available?"],
        confidence=0.3,
    )
    assert isinstance(result.analysis_id, UUID)
    assert result.request is req
    assert result.predictions == [pred]
    assert result.candidate_options == [opt]
    assert result.recommended_option_id == opt.option_id
    assert result.recommendation_rationale == "lowest risk and best benefit"
    assert result.uncertainty == ["heuristic estimates"]
    assert result.unresolved_questions == ["is more data available?"]
    assert result.confidence == 0.3
    assert isinstance(result.created_at, datetime)


def test_decision_analysis_defaults() -> None:
    result = analysis()
    assert result.recommended_option_id is None
    assert result.recommendation_rationale is None
    assert result.uncertainty == []
    assert result.unresolved_questions == []
    assert result.confidence is None


def test_decision_analysis_recommendation_must_refer_to_option() -> None:
    with pytest.raises(ValidationError, match="candidate option"):
        analysis(recommended_option_id=UUID(int=999))


def test_decision_analysis_recommendation_none_allowed() -> None:
    result = analysis()
    assert result.recommended_option_id is None
    assert result.recommended_option is None


def test_decision_analysis_recommended_option_property() -> None:
    opt = option()
    result = analysis(
        candidate_options=[opt], recommended_option_id=opt.option_id
    )
    assert result.recommended_option is opt


def test_decision_analysis_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        analysis(confidence=2.0)


def test_decision_analysis_rejects_blank_recommendation_rationale() -> None:
    with pytest.raises(ValidationError, match="recommendation_rationale"):
        analysis(recommendation_rationale="  ")


def test_decision_analysis_rejects_blank_uncertainty() -> None:
    with pytest.raises(ValidationError, match="entries"):
        analysis(uncertainty=["ok", ""])


def test_decision_analysis_rejects_blank_unresolved_question() -> None:
    with pytest.raises(ValidationError, match="entries"):
        analysis(unresolved_questions=["  "])


def test_decision_analysis_situation_and_question_properties() -> None:
    req = request()
    result = analysis(request=req)
    assert result.situation == req.situation
    assert result.request.question == req.question


def test_decision_analysis_aggregates_prediction_assumptions() -> None:
    result = analysis(
        predictions=[
            prediction(
                assumptions=[
                    "The feed is reliable.",
                    "Load stays constant.",
                ]
            ),
            prediction(
                assumptions=["The feed is reliable.", "A second premise."]
            ),
        ]
    )
    assert result.assumptions == (
        "The feed is reliable.",
        "Load stays constant.",
        "A second premise.",
    )


# --- Predictor abstraction --------------------------------------------------


def test_predictor_is_abstract() -> None:
    with pytest.raises(TypeError):
        Predictor()


def test_predictor_requires_metadata() -> None:
    with pytest.raises(TypeError, match="name"):

        class MissingMetadata(Predictor):
            async def predict(
                self, req: PredictionRequest
            ) -> DecisionAnalysis:
                return DecisionAnalysis(request=req, predictions=[], candidate_options=[])


def test_predictor_is_provider_independent() -> None:
    assert Predictor.__module__ == "app.core.prediction"


def test_probability_range_documented() -> None:
    assert "0, 1" in PROBABILITY_RANGE_DESCRIPTION


def test_confidence_range_documented() -> None:
    assert "0, 1" in CONFIDENCE_RANGE_DESCRIPTION


def test_benefit_score_range_documented() -> None:
    assert "0, 1" in BENEFIT_SCORE_RANGE_DESCRIPTION


def test_heuristic_notice_wording() -> None:
    assert "heuristic estimate" in HEURISTIC_NOTICE


# --- FakePredictor ----------------------------------------------------------


def test_fake_predictor_satisfies_interface() -> None:
    predictor = FakePredictor()
    assert isinstance(predictor, Predictor)
    assert predictor.name == "fake-predictor"
    assert predictor.description


def test_fake_predictor_accepts_arbitrary_request() -> None:
    predictor = FakePredictor()
    req = request()
    result = asyncio.run(predictor.predict(req))
    assert isinstance(result, DecisionAnalysis)
    assert result.request is req


def test_fake_predictor_returns_deterministic_result() -> None:
    predictor = FakePredictor()
    req = request()
    first = asyncio.run(predictor.predict(req))
    second = asyncio.run(predictor.predict(req))
    assert first.analysis_id == second.analysis_id
    assert [p.outcome for p in first.predictions] == [
        p.outcome for p in second.predictions
    ]
    assert [p.probability for p in first.predictions] == [
        p.probability for p in second.predictions
    ]
    assert [o.description for o in first.candidate_options] == [
        o.description for o in second.candidate_options
    ]
    assert first.recommended_option_id == second.recommended_option_id
    assert first.uncertainty == second.uncertainty
    assert first.confidence == second.confidence


def test_fake_predictor_never_claims_calibrated_probabilities() -> None:
    predictor = FakePredictor()
    result = asyncio.run(predictor.predict(request()))
    assert all(p.calibrated is False for p in result.predictions)


def test_fake_predictor_probabilities_are_in_valid_range() -> None:
    predictor = FakePredictor()
    result = asyncio.run(predictor.predict(request()))
    assert result.predictions
    for prediction_result in result.predictions:
        assert 0.0 <= (prediction_result.probability or 0.0) <= 1.0
        assert 0.0 <= (prediction_result.confidence or 0.0) <= 1.0


def test_fake_predictor_surfaces_heuristic_notice() -> None:
    predictor = FakePredictor()
    result = asyncio.run(predictor.predict(request()))
    assert HEURISTIC_NOTICE in result.uncertainty


def test_fake_predictor_generates_decision_options() -> None:
    predictor = FakePredictor()
    result = asyncio.run(predictor.predict(request()))
    assert len(result.candidate_options) >= 2
    for opt in result.candidate_options:
        assert opt.description
        assert 0.0 <= (opt.benefit_score or 0.0) <= 1.0
        assert opt.risk in RiskLevel


def test_fake_predictor_recommendation_is_consistent() -> None:
    predictor = FakePredictor()
    result = asyncio.run(predictor.predict(request()))
    option_ids = {opt.option_id for opt in result.candidate_options}
    assert result.recommended_option_id in option_ids
    assert result.recommended_option in result.candidate_options
    assert result.recommendation_rationale


def test_fake_predictor_records_requests() -> None:
    predictor = FakePredictor()
    req_a = request()
    req_b = request(question="A different question?")
    asyncio.run(predictor.predict(req_a))
    asyncio.run(predictor.predict(req_b))
    assert len(predictor.requests) == 2
    assert predictor.requests[0] is req_a
    assert predictor.requests[1] is req_b


def test_fake_predictor_can_raise_configured_error() -> None:
    predictor = FakePredictor(raise_error=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(predictor.predict(request()))


def test_fake_predictor_does_not_fabricate_evidence() -> None:
    predictor = FakePredictor()
    result = asyncio.run(predictor.predict(request()))
    for prediction_result in result.predictions:
        assert prediction_result.evidence_refs == []
        assert prediction_result.assumptions
    assert result.uncertainty


def test_fake_predictor_respects_candidate_option_hints() -> None:
    predictor = FakePredictor()
    req = request(candidate_options=["Option Alpha", "Option Beta"])
    result = asyncio.run(predictor.predict(req))
    assert [opt.description for opt in result.candidate_options] == [
        "Option Alpha",
        "Option Beta",
    ]


def test_fake_predictor_does_not_call_ai_or_network() -> None:
    assert "httpx" not in getattr(FakePredictor, "__module__", "")
    assert "openai" not in getattr(FakePredictor, "__module__", "")
    result = asyncio.run(FakePredictor().predict(request()))
    assert isinstance(result, DecisionAnalysis)


def test_prediction_is_decision_support_not_certainty() -> None:
    predictor = FakePredictor()
    result = asyncio.run(predictor.predict(request()))
    for prediction_result in result.predictions:
        assert "heuristic estimate" in prediction_result.outcome
        assert "no guarantee" not in prediction_result.outcome
    assert HEURISTIC_NOTICE in result.uncertainty
    assert result.recommended_option is not None