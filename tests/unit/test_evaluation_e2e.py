"""Tests for end-to-end evaluation."""

import asyncio
from pathlib import Path
import tempfile

from app.evaluation.fakes import EvaluationEnvironment
from app.evaluation.models import (
    EvaluationMode,
    EvaluationRun,
    ResultClassification,
)
from app.evaluation.runners import run_all_evaluation_async, run_all_evaluation_sync
from app.evaluation.reports import (
    generate_json_report,
    generate_markdown_report,
    save_evaluation_report,
)
from app.evaluation.reliability import run_all_reliability_sync


def _run(coro):
    return asyncio.run(coro)


class TestEndToEndEvaluation:
    def test_full_run_completes(self):
        run = run_all_evaluation_sync()
        assert run.results
        assert run.reliability_results
        assert run.summary
        assert run.completed_at is not None

    def test_all_scenarios_covered(self):
        run = run_all_evaluation_sync()
        scenario_names = {r.scenario for r in run.results}
        expected_scenarios = {
            "STT Quality",
            "Language Detection",
            "Tool/Agent Routing",
            "Planning Success",
            "Research/Source Quality",
            "Computer Task Completion",
            "Browser Success",
            "Vision Understanding",
            "Distributed Scheduling/Recovery",
            "Security Reliability",
            "Voice Latency",
            "Avatar Synchronization",
            "Memory Retrieval",
            "End-to-End Task Completion",
            "Reliability",
            "Verification",
            "Prediction Calibration",
        }
        assert expected_scenarios.issubset(scenario_names)

    def test_all_metrics_have_evidence(self):
        run = run_all_evaluation_sync()
        for r in run.results:
            assert r.evidence is not None
            assert len(r.evidence) > 0

    def test_all_metrics_have_limitations(self):
        run = run_all_evaluation_sync()
        for r in run.results:
            assert r.limitations is not None
            assert len(r.limitations) > 0

    def test_not_measured_labeled_correctly(self):
        run = run_all_evaluation_sync()
        not_measured = [r for r in run.results if r.status == ResultClassification.NOT_MEASURED]
        for r in not_measured:
            assert "fixture" in (r.limitations or "").lower() or "not real" in (r.limitations or "").lower() or "no" in (r.limitations or "").lower()

    def test_deterministic_mode(self):
        run = run_all_evaluation_sync()
        assert run.environment.mode == EvaluationMode.DETERMINISTIC
        assert run.environment.live_providers_used == []

    def test_summary_consistent(self):
        run = run_all_evaluation_sync()
        s = run.summary
        total = s.pass_count + s.fail_count + s.inconclusive_count + s.not_measured_count + s.not_applicable_count
        assert total == s.total_metrics

    def test_reliability_all_pass(self):
        results = run_all_reliability_sync()
        fail_count = sum(1 for r in results if r.status == ResultClassification.FAIL)
        assert fail_count == 0

    def test_report_generation(self):
        run = run_all_evaluation_sync()
        md = generate_markdown_report(run)
        assert len(md) > 100
        json_data = generate_json_report(run)
        assert json_data["results"]
        assert json_data["summary"]

    def test_report_save_and_load(self):
        run = run_all_evaluation_sync()
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = save_evaluation_report(run, Path(tmpdir))
            assert paths["markdown"].exists()
            assert paths["json"].exists()
            content = paths["markdown"].read_text(encoding="utf-8")
            assert "MISSMINUTES Evaluation Report" in content

    def test_regression_gates(self):
        from app.evaluation.models import REGRESSION_GATES

        assert len(REGRESSION_GATES) >= 7
        for gate in REGRESSION_GATES:
            assert gate.name
            assert gate.metric_name
            assert gate.required_status

    def test_no_fabricated_benchmarks(self):
        run = run_all_evaluation_sync()
        for r in run.results:
            if r.status == ResultClassification.NOT_MEASURED:
                assert r.value is None or r.limitations is not None

    def test_bounded_loop_termination(self):
        run = run_all_evaluation_sync()
        loop_results = [r for r in run.results if r.metric == "reliability_no_infinite_loops"]
        assert len(loop_results) > 0
        for r in loop_results:
            assert r.status == ResultClassification.PASS

    def test_security_not_bypassed(self):
        run = run_all_evaluation_sync()
        security_results = [r for r in run.results if r.metric.startswith("security_")]
        for r in security_results:
            assert "bypass" not in (r.evidence or "").lower()

    def test_voice_timing_not_fabricated(self):
        run = run_all_evaluation_sync()
        voice_results = [r for r in run.results if r.scenario == "Voice Latency"]
        assert len(voice_results) > 0
        for r in voice_results:
            if "latency" in r.metric.lower():
                assert r.status == ResultClassification.NOT_MEASURED

    def test_avatar_sync_not_fabricated(self):
        run = run_all_evaluation_sync()
        avatar_results = [r for r in run.results if r.scenario == "Avatar Synchronization"]
        assert len(avatar_results) > 0
        for r in avatar_results:
            assert r.status in (ResultClassification.PASS, ResultClassification.FAIL, ResultClassification.NOT_MEASURED)
