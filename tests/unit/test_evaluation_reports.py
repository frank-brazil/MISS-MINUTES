"""Tests for evaluation report generation."""

import json
import tempfile
from pathlib import Path
from uuid import uuid4

from app.evaluation.models import (
    EnvironmentInfo,
    EvaluationMode,
    EvaluationResult,
    EvaluationRun,
    EvaluationSummary,
    ReliabilityResult,
    ResultClassification,
)
from app.evaluation.reports import (
    compare_runs,
    generate_json_report,
    generate_markdown_report,
    load_previous_run,
    save_evaluation_report,
)


def _make_run() -> EvaluationRun:
    return EvaluationRun(
        run_id=uuid4(),
        started_at="2026-01-01T00:00:00Z",
        completed_at="2026-01-01T00:01:00Z",
        environment=EnvironmentInfo(
            mode=EvaluationMode.DETERMINISTIC,
            python_version="3.11.0",
            platform="test-platform",
            deterministic_fakes_used=["FakeAI", "FakeSTT"],
            live_providers_used=[],
        ),
        results=[
            EvaluationResult(
                metric="stt_word_error_rate",
                scenario="STT Quality",
                value=0.0,
                status=ResultClassification.PASS,
                evidence="Perfect match",
                limitations="Fixture only",
            ),
            EvaluationResult(
                metric="routing_correct_rate",
                scenario="Routing",
                value=0.9,
                status=ResultClassification.PASS,
                evidence="9/10 correct",
                limitations="Capability routing only",
            ),
            EvaluationResult(
                metric="voice_latency",
                scenario="Voice",
                value=150.0,
                status=ResultClassification.NOT_MEASURED,
                evidence="Fixture value",
                limitations="No real hardware",
            ),
        ],
        reliability_results=[
            ReliabilityResult(
                scenario_id=uuid4(),
                scenario_name="provider_failure",
                status=ResultClassification.PASS,
                details="Handled safely",
            ),
            ReliabilityResult(
                scenario_id=uuid4(),
                scenario_name="timeout",
                status=ResultClassification.PASS,
                details="Timeout enforced",
            ),
        ],
        summary=EvaluationSummary(
            total_metrics=3,
            pass_count=2,
            fail_count=0,
            inconclusive_count=0,
            not_measured_count=1,
            not_applicable_count=0,
            reliability_pass=2,
            reliability_fail=0,
            reliability_not_applicable=0,
        ),
    )


class TestGenerateMarkdownReport:
    def test_contains_title(self):
        run = _make_run()
        report = generate_markdown_report(run)
        assert "# MISSMINUTES Evaluation Report" in report

    def test_contains_summary(self):
        run = _make_run()
        report = generate_markdown_report(run)
        assert "## Executive Summary" in report
        assert "Total results" in report

    def test_contains_results(self):
        run = _make_run()
        report = generate_markdown_report(run)
        assert "## Results by Scenario" in report
        assert "stt_word_error_rate" in report

    def test_contains_reliability(self):
        run = _make_run()
        report = generate_markdown_report(run)
        assert "## Reliability Results" in report
        assert "provider_failure" in report

    def test_contains_not_measured(self):
        run = _make_run()
        report = generate_markdown_report(run)
        assert "## NOT_MEASURED Metrics" in report

    def test_contains_limitations(self):
        run = _make_run()
        report = generate_markdown_report(run)
        assert "## Limitations" in report
        assert "DETERMINISTIC FIXTURE" in report

    def test_contains_fakes_used(self):
        run = _make_run()
        report = generate_markdown_report(run)
        assert "FakeAI" in report
        assert "FakeSTT" in report

    def test_empty_run(self):
        run = EvaluationRun(
            started_at="2026-01-01T00:00:00Z",
            environment=EnvironmentInfo(),
            results=[],
            reliability_results=[],
        )
        report = generate_markdown_report(run)
        assert "# MISSMINUTES Evaluation Report" in report
        assert "No NOT_MEASURED metrics" in report


class TestGenerateJsonReport:
    def test_structure(self):
        run = _make_run()
        report = generate_json_report(run)
        assert "run_id" in report
        assert "environment" in report
        assert "results" in report
        assert "reliability_results" in report
        assert "summary" in report

    def test_results_serialized(self):
        run = _make_run()
        report = generate_json_report(run)
        assert len(report["results"]) == 3
        assert report["results"][0]["metric"] == "stt_word_error_rate"

    def test_summary_serialized(self):
        run = _make_run()
        report = generate_json_report(run)
        assert report["summary"]["total_metrics"] == 3
        assert report["summary"]["pass_count"] == 2

    def test_json_serializable(self):
        run = _make_run()
        report = generate_json_report(run)
        json_str = json.dumps(report)
        assert len(json_str) > 0


class TestSaveEvaluationReport:
    def test_saves_both_files(self):
        run = _make_run()
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = save_evaluation_report(run, Path(tmpdir))
            assert "markdown" in paths
            assert "json" in paths
            assert paths["markdown"].exists()
            assert paths["json"].exists()

    def test_markdown_content(self):
        run = _make_run()
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = save_evaluation_report(run, Path(tmpdir))
            content = paths["markdown"].read_text(encoding="utf-8")
            assert "# MISSMINUTES Evaluation Report" in content

    def test_json_content(self):
        run = _make_run()
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = save_evaluation_report(run, Path(tmpdir))
            content = paths["json"].read_text(encoding="utf-8")
            data = json.loads(content)
            assert "results" in data


class TestLoadPreviousRun:
    def test_load_existing(self):
        run = _make_run()
        with tempfile.TemporaryDirectory() as tmpdir:
            save_evaluation_report(run, Path(tmpdir))
            loaded = load_previous_run(Path(tmpdir) / "latest.json")
            assert loaded is not None
            assert loaded.run_id == run.run_id

    def test_load_nonexistent(self):
        loaded = load_previous_run(Path("/nonexistent/path.json"))
        assert loaded is None

    def test_load_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "latest.json"
            path.write_text("not json", encoding="utf-8")
            loaded = load_previous_run(path)
            assert loaded is None


class TestCompareRuns:
    def test_compare_identical(self):
        run = _make_run()
        comparisons = compare_runs(run, run)
        assert len(comparisons) == 3
        for comp in comparisons:
            assert comp["change"] == 0.0

    def test_compare_different(self):
        run1 = _make_run()
        run2 = _make_run()
        run2.results[0].value = 0.1
        comparisons = compare_runs(run1, run2)
        assert len(comparisons) == 3
        stt_comp = [c for c in comparisons if c["metric"] == "stt_word_error_rate"][0]
        assert stt_comp["previous_value"] == 0.0
        assert stt_comp["current_value"] == 0.1
        assert stt_comp["change"] == 0.1
