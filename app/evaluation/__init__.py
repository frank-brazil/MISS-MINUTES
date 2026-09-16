"""Evaluation and reliability framework for MISSMINUTES.

Provides deterministic benchmark scenarios, metric definitions, structured
result collection, reliability testing, and report generation.

All evaluation in this package runs fully offline using deterministic fakes.
No API keys, network access, microphone, browser, or GUI are required.
"""

from app.evaluation.models import (
    EvaluationCase,
    EvaluationCategory,
    EvaluationMetric,
    EvaluationMode,
    EvaluationResult,
    EvaluationRun,
    EvaluationScenario,
    EvaluationSummary,
    EnvironmentInfo,
    FailureCategory,
    RegressionGate,
    REGRESSION_GATES,
    ReliabilityResult,
    ReliabilityScenario,
    ResultClassification,
    RoutingDecision,
    RoutingMetadata,
)

__all__ = [
    "EvaluationCase",
    "EvaluationCategory",
    "EvaluationMetric",
    "EvaluationMode",
    "EvaluationResult",
    "EvaluationRun",
    "EvaluationScenario",
    "EvaluationSummary",
    "EnvironmentInfo",
    "FailureCategory",
    "RegressionGate",
    "REGRESSION_GATES",
    "ReliabilityResult",
    "ReliabilityScenario",
    "ResultClassification",
    "RoutingDecision",
    "RoutingMetadata",
]
