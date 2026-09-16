"""Prediction agent for decision analysis and risk assessment.

This agent wraps the existing ``Prediction`` abstraction behind the ``Agent``
interface.  It accepts a ``Predictor`` via dependency injection and delegates
to it when a task arrives.  It never calls an LLM or makes network requests
on its own.

Terminology:

- **predictor**: an injected ``Predictor`` instance that performs the actual
  decision analysis.  The agent does not duplicate its behaviour.
- **decision analysis**: the typed ``DecisionAnalysis`` produced by the
  predictor, serialised into the ``AgentResult`` output.
"""

import json
import logging
from typing import ClassVar

from app.agents.base import Agent, AgentResult
from app.core.prediction import PredictionRequest, Predictor
from app.core.task import Task


class PredictionAgent(Agent):
    """Agent specialised in prediction, decision analysis, and risk assessment.

    Requires a ``Predictor`` at construction time.  Without one the agent
    operates in deterministic stub mode.
    """

    name: ClassVar[str] = "prediction"
    description: ClassVar[str] = (
        "Performs prediction, decision analysis, and risk assessment."
    )
    capabilities: ClassVar[frozenset[str]] = frozenset(
        {"prediction", "decision_analysis", "risk_analysis"}
    )

    def __init__(self, predictor: Predictor | None = None) -> None:
        self._predictor = predictor
        self._logger = logging.getLogger(__name__)

    @property
    def predictor(self) -> Predictor | None:
        return self._predictor

    async def execute(self, task: Task) -> AgentResult:
        self._logger.info(
            "PredictionAgent executing task %s: %s",
            task.task_id,
            task.description[:80],
        )

        if self._predictor is None:
            return AgentResult.ok(
                output=(
                    f"No predictor configured for task "
                    f"'{task.description[:120]}'. "
                    "Inject a Predictor to enable decision analysis."
                )
            )

        request = PredictionRequest(question=task.description)

        try:
            analysis = await self._predictor.predict(request)
        except Exception as exc:
            error_msg = f"Predictor raised: {type(exc).__name__}: {exc}"
            self._logger.error(error_msg)
            return AgentResult.fail(error=error_msg)

        summary = {
            "analysis_id": str(analysis.analysis_id),
            "predictions_count": len(analysis.predictions),
            "options_count": len(analysis.candidate_options),
            "has_recommendation": analysis.recommended_option_id is not None,
            "confidence": analysis.confidence,
        }
        return AgentResult.ok(output=json.dumps(summary))
