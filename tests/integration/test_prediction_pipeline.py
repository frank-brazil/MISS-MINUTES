import asyncio
import logging

from app.core.prediction import (
    DecisionAnalysis,
    DecisionOption,
    FakePredictor,
    HEURISTIC_NOTICE,
    Prediction,
    PredictionRequest,
    Predictor,
    RiskLevel,
)


async def _decide(
    predictor: Predictor, request: PredictionRequest
) -> DecisionAnalysis:
    return await predictor.predict(request)


def test_prediction_pipeline_decision_support_flows_through() -> None:
    predictor = FakePredictor()
    request = PredictionRequest(
        question="Will the nightly build stay green?",
        situation={"branch": "main"},
    )
    result = asyncio.run(_decide(predictor, request))
    assert isinstance(result, DecisionAnalysis)
    assert result.recommended_option is not None
    assert result.request is request
    assert all(
        0.0 <= (item.probability or 0.0) <= 1.0 for item in result.predictions
    )
    assert all(opt.risk in RiskLevel for opt in result.candidate_options)
    assert HEURISTIC_NOTICE in result.uncertainty
    assert any(item.calibrated is False for item in result.predictions)


def test_prediction_providers_are_interchangeable() -> None:
    fake = FakePredictor()

    class EchoPredictor(Predictor):
        name = "echo-predictor"
        description = "Returns a single fixed deterministic prediction."

        async def predict(
            self, request: PredictionRequest
        ) -> DecisionAnalysis:
            prediction = Prediction(
                outcome="the outcome follows the supplied question",
                probability=0.8,
            )
            option = DecisionOption(
                description="take the low-risk course",
                benefit_score=0.8,
                risk=RiskLevel.LOW,
            )
            return DecisionAnalysis(
                request=request,
                predictions=[prediction],
                candidate_options=[option],
                recommended_option_id=option.option_id,
                uncertainty=[HEURISTIC_NOTICE],
            )

    for predictor in (fake, EchoPredictor()):
        result = asyncio.run(
            _decide(
                predictor,
                PredictionRequest(
                    question="Will the rollout proceed cleanly?"
                ),
            )
        )
        assert isinstance(result, DecisionAnalysis)
        assert result.recommended_option is not None
        assert result.assumptions or result.uncertainty


def test_prediction_logs_do_not_leak_question_text(caplog) -> None:
    predictor = FakePredictor()
    with caplog.at_level(logging.INFO, logger="app.core.prediction"):
        asyncio.run(
            _decide(
                predictor,
                PredictionRequest(
                    question="A private question about an internal plan?"
                ),
            )
        )
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "request_id=" in messages
    assert "A private question about an internal plan?" not in messages


def test_prediction_decision_support_is_standalone() -> None:
    assert "app.core.prediction" == FakePredictor.__module__
    import sys

    module = sys.modules[FakePredictor.__module__]
    source = module.__file__ or ""
    with open(source, encoding="utf-8") as handle:
        content = handle.read()
    assert "httpx" not in content
    assert "openai" not in content
    assert "async def predict" in content