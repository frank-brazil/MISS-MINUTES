"""Tests for evaluation data models."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.evaluation.models import (
    REGRESSION_GATES,
    EnvironmentInfo,
    EvaluationCase,
    EvaluationCategory,
    EvaluationMetric,
    EvaluationMode,
    EvaluationResult,
    EvaluationRun,
    EvaluationScenario,
    EvaluationSummary,
    FailureCategory,
    RegressionGate,
    ReliabilityResult,
    ReliabilityScenario,
    ResultClassification,
    RoutingDecision,
    RoutingMetadata,
)


def _run(coro):
    return __import__("asyncio").run(coro)


class TestEvaluationCategory:
    def test_all_values_exist(self):
        values = list(EvaluationCategory)
        assert len(values) == 18
        assert EvaluationCategory.STT in values
        assert EvaluationCategory.SECURITY in values
        assert EvaluationCategory.RELIABILITY in values

    def test_string_values(self):
        assert EvaluationCategory.STT.value == "stt"
        assert EvaluationCategory.VOICE.value == "voice"
        assert EvaluationCategory.END_TO_END.value == "end_to_end"


class TestResultClassification:
    def test_all_values(self):
        assert ResultClassification.PASS.value == "pass"
        assert ResultClassification.FAIL.value == "fail"
        assert ResultClassification.INCONCLUSIVE.value == "inconclusive"
        assert ResultClassification.NOT_MEASURED.value == "not_measured"
        assert ResultClassification.NOT_APPLICABLE.value == "not_applicable"


class TestEvaluationMode:
    def test_modes(self):
        assert EvaluationMode.DETERMINISTIC.value == "deterministic"
        assert EvaluationMode.LIVE.value == "live"


class TestRoutingDecision:
    def test_all_values(self):
        assert RoutingDecision.CORRECT.value == "correct"
        assert RoutingDecision.INCORRECT_AGENT.value == "incorrect_agent"
        assert RoutingDecision.SECURITY_DENIED.value == "security_denied"


class TestFailureCategory:
    def test_all_values(self):
        assert FailureCategory.PROVIDER_ERROR.value == "provider_error"
        assert FailureCategory.TIMEOUT.value == "timeout"
        assert FailureCategory.DUPLICATE_RESULT.value == "duplicate_result"


class TestEvaluationScenario:
    def test_create_minimal(self):
        scenario = EvaluationScenario(
            name="Test Scenario",
            category=EvaluationCategory.STT,
            description="A test scenario",
        )
        assert scenario.name == "Test Scenario"
        assert scenario.category == EvaluationCategory.STT
        assert isinstance(scenario.scenario_id, type(uuid4()))

    def test_create_with_tags(self):
        scenario = EvaluationScenario(
            name="Tagged",
            category=EvaluationCategory.VOICE,
            description="Has tags",
            tags=frozenset({"tag1", "tag2"}),
        )
        assert "tag1" in scenario.tags
        assert "tag2" in scenario.tags

    def test_blank_name_raises(self):
        with pytest.raises(ValueError, match="name must not be blank"):
            EvaluationScenario(name="  ", category=EvaluationCategory.STT, description="desc")

    def test_blank_description_raises(self):
        with pytest.raises(ValueError, match="description must not be blank"):
            EvaluationScenario(name="Test", category=EvaluationCategory.STT, description="  ")


class TestRoutingMetadata:
    def test_create(self):
        meta = RoutingMetadata(expected_agent="coding", expected_tool="file_read")
        assert meta.expected_agent == "coding"
        assert meta.decision == RoutingDecision.CORRECT

    def test_defaults(self):
        meta = RoutingMetadata(expected_agent="research")
        assert meta.expected_tool is None
        assert meta.actual_agent is None
        assert meta.actual_tool is None


class TestEvaluationCase:
    def test_create(self):
        case = EvaluationCase(
            scenario_id=uuid4(),
            input={"text": "test"},
            expected_behavior="Should detect language",
        )
        assert case.input["text"] == "test"
        assert case.expected_result is None
        assert case.expected_routing is None

    def test_blank_behavior_raises(self):
        with pytest.raises(ValueError, match="expected_behavior must not be blank"):
            EvaluationCase(scenario_id=uuid4(), expected_behavior="  ")


class TestEvaluationMetric:
    def test_create(self):
        metric = EvaluationMetric(
            name="test_metric",
            category=EvaluationCategory.STT,
            definition="A test metric",
            unit="ratio",
            target=0.95,
        )
        assert metric.name == "test_metric"
        assert metric.target == 0.95

    def test_blank_name_raises(self):
        with pytest.raises(ValueError, match="name must not be blank"):
            EvaluationMetric(name="  ", category=EvaluationCategory.STT, definition="def")

    def test_blank_definition_raises(self):
        with pytest.raises(ValueError, match="definition must not be blank"):
            EvaluationMetric(name="m", category=EvaluationCategory.STT, definition="  ")


class TestEvaluationResult:
    def test_create(self):
        result = EvaluationResult(
            metric="test",
            scenario="Test Scenario",
            value=0.95,
            status=ResultClassification.PASS,
            evidence="Evidence here",
            limitations="Some limitations",
        )
        assert result.metric == "test"
        assert result.value == 0.95
        assert result.status == ResultClassification.PASS

    def test_defaults(self):
        result = EvaluationResult(metric="m", scenario="s", status=ResultClassification.PASS)
        assert result.value is None
        assert result.case_id is None
        assert result.mode == EvaluationMode.DETERMINISTIC


class TestEvaluationSummary:
    def test_create(self):
        summary = EvaluationSummary(
            total_metrics=100,
            pass_count=80,
            fail_count=10,
            inconclusive_count=5,
            not_measured_count=3,
            not_applicable_count=2,
        )
        assert summary.total_metrics == 100
        assert summary.pass_count == 80

    def test_defaults(self):
        summary = EvaluationSummary()
        assert summary.total_metrics == 0
        assert summary.reliability_pass == 0


class TestReliabilityScenario:
    def test_create(self):
        scenario = ReliabilityScenario(
            name="provider_failure",
            description="AI provider fails",
            failure_type=FailureCategory.PROVIDER_ERROR,
            expected_behavior="Structured error returned",
        )
        assert scenario.failure_type == FailureCategory.PROVIDER_ERROR

    def test_blank_name_raises(self):
        with pytest.raises(ValueError, match="name must not be blank"):
            ReliabilityScenario(
                name="  ",
                description="desc",
                failure_type=FailureCategory.TIMEOUT,
                expected_behavior="behavior",
            )


class TestReliabilityResult:
    def test_create(self):
        result = ReliabilityResult(
            scenario_id=uuid4(),
            scenario_name="test",
            status=ResultClassification.PASS,
            details="All good",
            evidence="Evidence here",
        )
        assert result.status == ResultClassification.PASS


class TestEvaluationRun:
    def test_create(self):
        run = EvaluationRun(
            started_at=datetime.now(UTC),
            environment=EnvironmentInfo(),
            results=[],
            reliability_results=[],
        )
        assert run.results == []
        assert run.completed_at is None

    def test_with_summary(self):
        summary = EvaluationSummary(total_metrics=5, pass_count=3)
        run = EvaluationRun(
            started_at=datetime.now(UTC),
            results=[],
            reliability_results=[],
            summary=summary,
        )
        assert run.summary.total_metrics == 5


class TestRegressionGate:
    def test_create(self):
        gate = RegressionGate(
            name="test_gate",
            description="Test gate",
            metric_name="test_metric",
            required_status=ResultClassification.PASS,
        )
        assert gate.enabled is True

    def test_gates_defined(self):
        assert len(REGRESSION_GATES) == 7
        names = {g.name for g in REGRESSION_GATES}
        assert "zero_security_bypasses" in names
        assert "zero_infinite_loops" in names
        assert "unsafe_terminal_denied" in names
        assert "unsafe_browser_denied" in names
