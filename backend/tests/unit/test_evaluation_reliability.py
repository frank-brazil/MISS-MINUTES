"""Tests for evaluation reliability testing."""

import asyncio

from app.evaluation.datasets import RELIABILITY_SCENARIOS
from app.evaluation.fakes import EvaluationEnvironment
from app.evaluation.models import ResultClassification
from app.evaluation.reliability import (
    RELIABILITY_TEST_MAP,
    run_all_reliability_sync,
    run_all_reliability_tests,
    run_reliability_test,
)


def _run(coro):
    return asyncio.run(coro)


class TestReliabilityTestMap:
    def test_all_scenarios_have_tests(self):
        scenario_names = {s.name for s in RELIABILITY_SCENARIOS}
        test_names = set(RELIABILITY_TEST_MAP.keys())
        assert scenario_names == test_names

    def test_map_not_empty(self):
        assert len(RELIABILITY_TEST_MAP) == 15


class TestRunReliabilityTest:
    def test_provider_failure(self):
        env = EvaluationEnvironment()
        scenario = next(s for s in RELIABILITY_SCENARIOS if s.name == "provider_failure")
        result = _run(run_reliability_test(scenario, env))
        assert result.status == ResultClassification.PASS
        assert "Provider failure" in result.details or "structured error" in result.details

    def test_tool_failure(self):
        env = EvaluationEnvironment()
        scenario = next(s for s in RELIABILITY_SCENARIOS if s.name == "tool_failure")
        result = _run(run_reliability_test(scenario, env))
        assert result.status == ResultClassification.PASS

    def test_agent_failure(self):
        env = EvaluationEnvironment()
        scenario = next(s for s in RELIABILITY_SCENARIOS if s.name == "agent_failure")
        result = _run(run_reliability_test(scenario, env))
        assert result.status == ResultClassification.PASS

    def test_planner_failure(self):
        env = EvaluationEnvironment()
        scenario = next(s for s in RELIABILITY_SCENARIOS if s.name == "planner_failure")
        result = _run(run_reliability_test(scenario, env))
        assert result.status == ResultClassification.PASS

    def test_timeout(self):
        env = EvaluationEnvironment()
        scenario = next(s for s in RELIABILITY_SCENARIOS if s.name == "timeout")
        result = _run(run_reliability_test(scenario, env))
        assert result.status == ResultClassification.PASS

    def test_cancellation(self):
        env = EvaluationEnvironment()
        scenario = next(s for s in RELIABILITY_SCENARIOS if s.name == "cancellation")
        result = _run(run_reliability_test(scenario, env))
        assert result.status == ResultClassification.PASS

    def test_verification_failure(self):
        env = EvaluationEnvironment()
        scenario = next(s for s in RELIABILITY_SCENARIOS if s.name == "verification_failure")
        result = _run(run_reliability_test(scenario, env))
        assert result.status == ResultClassification.PASS

    def test_inconclusive_verification(self):
        env = EvaluationEnvironment()
        scenario = next(s for s in RELIABILITY_SCENARIOS if s.name == "inconclusive_verification")
        result = _run(run_reliability_test(scenario, env))
        assert result.status == ResultClassification.PASS

    def test_worker_failure(self):
        env = EvaluationEnvironment()
        scenario = next(s for s in RELIABILITY_SCENARIOS if s.name == "worker_failure")
        result = _run(run_reliability_test(scenario, env))
        assert result.status == ResultClassification.PASS

    def test_worker_heartbeat_timeout(self):
        env = EvaluationEnvironment()
        scenario = next(s for s in RELIABILITY_SCENARIOS if s.name == "worker_heartbeat_timeout")
        result = _run(run_reliability_test(scenario, env))
        assert result.status == ResultClassification.PASS

    def test_browser_failure(self):
        env = EvaluationEnvironment()
        scenario = next(s for s in RELIABILITY_SCENARIOS if s.name == "browser_failure")
        result = _run(run_reliability_test(scenario, env))
        assert result.status == ResultClassification.PASS

    def test_voice_interruption(self):
        env = EvaluationEnvironment()
        scenario = next(s for s in RELIABILITY_SCENARIOS if s.name == "voice_interruption")
        result = _run(run_reliability_test(scenario, env))
        assert result.status == ResultClassification.PASS

    def test_tts_failure(self):
        env = EvaluationEnvironment()
        scenario = next(s for s in RELIABILITY_SCENARIOS if s.name == "tts_failure")
        result = _run(run_reliability_test(scenario, env))
        assert result.status == ResultClassification.PASS

    def test_stt_failure(self):
        env = EvaluationEnvironment()
        scenario = next(s for s in RELIABILITY_SCENARIOS if s.name == "stt_failure")
        result = _run(run_reliability_test(scenario, env))
        assert result.status == ResultClassification.PASS

    def test_avatar_renderer_failure(self):
        env = EvaluationEnvironment()
        scenario = next(s for s in RELIABILITY_SCENARIOS if s.name == "avatar_renderer_failure")
        result = _run(run_reliability_test(scenario, env))
        assert result.status == ResultClassification.PASS


class TestRunAllReliability:
    def test_sync(self):
        results = run_all_reliability_sync()
        assert len(results) == 15
        for r in results:
            assert r.status in (
                ResultClassification.PASS,
                ResultClassification.FAIL,
                ResultClassification.NOT_MEASURED,
            )

    def test_async(self):
        results = _run(run_all_reliability_tests())
        assert len(results) == 15

    def test_all_pass(self):
        results = run_all_reliability_sync()
        pass_count = sum(1 for r in results if r.status == ResultClassification.PASS)
        assert pass_count == 15

    def test_no_infinite_loops(self):
        results = run_all_reliability_sync()
        for r in results:
            assert r.status != ResultClassification.FAIL, (
                f"Reliability test failed: {r.scenario_name}"
            )
