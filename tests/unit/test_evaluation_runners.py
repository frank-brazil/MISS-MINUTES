"""Tests for evaluation runners."""

import asyncio

from app.evaluation.fakes import EvaluationEnvironment
from app.evaluation.models import EvaluationMode, ResultClassification
from app.evaluation.runners import (
    _async_avatar,
    _async_bounded_loops,
    _async_browser,
    _async_computer_tools,
    _async_distributed,
    _async_e2e,
    _async_language_detection,
    _async_memory,
    _async_planning,
    _async_prediction,
    _async_research,
    _async_verification,
    _async_vision,
    _make_env_info,
    _run_routing,
    _run_security,
    _run_stt,
    _run_voice_timing,
    run_all_evaluation_async,
    run_all_evaluation_sync,
)


def _run(coro):
    return asyncio.run(coro)


class TestMakeEnvInfo:
    def test_create(self):
        info = _make_env_info()
        assert info.mode == EvaluationMode.DETERMINISTIC
        assert info.python_version
        assert info.platform
        assert len(info.deterministic_fakes_used) > 0
        assert info.live_providers_used == []


class TestRunStt:
    def test_returns_results(self):
        env = EvaluationEnvironment()
        results = _run_stt(env)
        assert len(results) > 0
        for r in results:
            assert r.metric.startswith("stt_")
            assert r.status in (ResultClassification.PASS, ResultClassification.FAIL)

    def test_perfect_transcripts_pass(self):
        env = EvaluationEnvironment()
        results = _run_stt(env)
        pass_results = [r for r in results if r.status == ResultClassification.PASS]
        assert len(pass_results) > 0


class TestRunLanguageDetection:
    def test_returns_results(self):
        env = EvaluationEnvironment()
        results = _run(_async_language_detection(env))
        assert len(results) > 0
        for r in results:
            assert r.metric == "language_detection_accuracy"


class TestRunRouting:
    def test_returns_results(self):
        env = EvaluationEnvironment()
        results = _run_routing(env)
        assert len(results) > 0
        for r in results:
            assert r.metric == "routing_correct_rate"


class TestRunPlanning:
    def test_returns_results(self):
        env = EvaluationEnvironment()
        results = _run(_async_planning(env))
        assert len(results) > 0
        for r in results:
            assert r.metric == "planning_valid_plan_rate"


class TestRunResearch:
    def test_returns_results(self):
        env = EvaluationEnvironment()
        results = _run(_async_research(env))
        assert len(results) > 0
        metrics = {r.metric for r in results}
        assert "research_source_coverage" in metrics


class TestRunComputerTools:
    def test_returns_results(self):
        env = EvaluationEnvironment()
        results = _run(_async_computer_tools(env))
        assert len(results) > 0
        metrics = {r.metric for r in results}
        assert "computer_task_success_rate" in metrics


class TestRunBrowser:
    def test_returns_results(self):
        env = EvaluationEnvironment()
        results = _run(_async_browser(env))
        assert len(results) > 0
        metrics = {r.metric for r in results}
        assert "browser_safe_action_rate" in metrics


class TestRunVision:
    def test_returns_results(self):
        env = EvaluationEnvironment()
        results = _run(_async_vision(env))
        assert len(results) > 0
        metrics = {r.metric for r in results}
        assert "vision_observation_accuracy" in metrics


class TestRunDistributed:
    def test_returns_results(self):
        env = EvaluationEnvironment()
        results = _run(_async_distributed(env))
        assert len(results) > 0
        metrics = {r.metric for r in results}
        assert "distributed_dispatch_success" in metrics


class TestRunSecurity:
    def test_returns_results(self):
        env = EvaluationEnvironment()
        results = _run_security(env)
        assert len(results) > 0


class TestRunVoiceTiming:
    def test_returns_results(self):
        env = EvaluationEnvironment()
        results = _run_voice_timing(env)
        assert len(results) > 0
        for r in results:
            assert (
                r.status == ResultClassification.NOT_MEASURED
                or r.status == ResultClassification.PASS
            )


class TestRunAvatar:
    def test_returns_results(self):
        env = EvaluationEnvironment()
        results = _run(_async_avatar(env))
        assert len(results) > 0
        metrics = {r.metric for r in results}
        assert "avatar_event_propagation" in metrics


class TestRunMemory:
    def test_returns_results(self):
        env = EvaluationEnvironment()
        results = _run(_async_memory(env))
        assert len(results) > 0
        for r in results:
            assert r.metric == "memory_retrieval_success"


class TestRunE2E:
    def test_returns_results(self):
        env = EvaluationEnvironment()
        results = _run(_async_e2e(env))
        assert len(results) > 0
        for r in results:
            assert r.metric == "e2e_task_completion_rate"


class TestRunBoundedLoops:
    def test_returns_results(self):
        env = EvaluationEnvironment()
        results = _run(_async_bounded_loops(env))
        assert len(results) > 0
        for r in results:
            assert r.metric == "reliability_no_infinite_loops"
            assert r.status == ResultClassification.PASS


class TestRunVerification:
    def test_returns_results(self):
        env = EvaluationEnvironment()
        results = _run(_async_verification(env))
        assert len(results) > 0
        for r in results:
            assert r.metric == "verification_accuracy"


class TestRunPrediction:
    def test_returns_results(self):
        env = EvaluationEnvironment()
        results = _run(_async_prediction(env))
        assert len(results) > 0
        for r in results:
            assert r.status == ResultClassification.NOT_MEASURED


class TestRunAllEvaluation:
    def test_sync(self):
        run = run_all_evaluation_sync()
        assert run.results
        assert run.reliability_results
        assert run.summary
        assert run.environment.mode == EvaluationMode.DETERMINISTIC

    def test_async(self):
        run = _run(run_all_evaluation_async())
        assert run.results
        assert run.summary
        assert run.completed_at is not None

    def test_summary_counts(self):
        run = run_all_evaluation_sync()
        s = run.summary
        assert s.total_metrics > 0
        assert (
            s.pass_count
            + s.fail_count
            + s.inconclusive_count
            + s.not_measured_count
            + s.not_applicable_count
            == s.total_metrics
        )

    def test_reliability_results(self):
        run = run_all_evaluation_sync()
        assert len(run.reliability_results) == 15
        for r in run.reliability_results:
            assert r.status in (
                ResultClassification.PASS,
                ResultClassification.FAIL,
                ResultClassification.NOT_MEASURED,
                ResultClassification.INCONCLUSIVE,
            )

    def test_no_fabricated_results(self):
        run = run_all_evaluation_sync()
        for r in run.results:
            if r.status == ResultClassification.NOT_MEASURED:
                assert r.limitations is not None
                assert len(r.limitations) > 0

    def test_all_fixtures_are_deterministic(self):
        run = run_all_evaluation_sync()
        assert run.environment.live_providers_used == []
        assert len(run.environment.deterministic_fakes_used) > 0
