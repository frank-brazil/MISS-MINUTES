"""Report generation for evaluation results.

Produces both Markdown and machine-readable JSON reports.
Historical results are preserved with timestamps.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.evaluation.models import (
    EvaluationResult,
    EvaluationRun,
    ReliabilityResult,
    ResultClassification,
)


def generate_markdown_report(run: EvaluationRun) -> str:
    lines: list[str] = []
    lines.append("# MISSMINUTES Evaluation Report")
    lines.append("")
    lines.append(f"**Run ID:** `{run.run_id}`")
    lines.append(f"**Started:** {run.started_at}")
    if run.completed_at:
        lines.append(f"**Completed:** {run.completed_at}")
    lines.append(f"**Mode:** {run.environment.mode.value}")
    lines.append(f"**Python:** {run.environment.python_version}")
    lines.append(f"**Platform:** {run.environment.platform}")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## Executive Summary")
    lines.append("")
    if run.summary:
        s = run.summary
        lines.append("| Metric | Count |")
        lines.append("|---|---|")
        lines.append(f"| Total results | {s.total_metrics} |")
        lines.append(f"| PASS | {s.pass_count} |")
        lines.append(f"| FAIL | {s.fail_count} |")
        lines.append(f"| INCONCLUSIVE | {s.inconclusive_count} |")
        lines.append(f"| NOT_MEASURED | {s.not_measured_count} |")
        lines.append(f"| NOT_APPLICABLE | {s.not_applicable_count} |")
        lines.append(f"| Reliability PASS | {s.reliability_pass} |")
        lines.append(f"| Reliability FAIL | {s.reliability_fail} |")
        lines.append(f"| Reliability N/A | {s.reliability_not_applicable} |")
    else:
        lines.append("No summary available.")
    lines.append("")

    lines.append("---")
    lines.append("")

    lines.append("## Deterministic Fakes Used")
    lines.append("")
    for fake in run.environment.deterministic_fakes_used:
        lines.append(f"- `{fake}`")
    lines.append("")
    if run.environment.live_providers_used:
        lines.append("## Live Providers Used")
        lines.append("")
        for provider in run.environment.live_providers_used:
            lines.append(f"- `{provider}`")
        lines.append("")

    lines.append("---")
    lines.append("")

    lines.append("## Results by Scenario")
    lines.append("")
    scenarios: dict[str, list[EvaluationResult]] = {}
    for result in run.results:
        scenarios.setdefault(result.scenario, []).append(result)
    for scenario_name, results in scenarios.items():
        lines.append(f"### {scenario_name}")
        lines.append("")
        lines.append("| Metric | Value | Status | Evidence | Limitations |")
        lines.append("|---|---|---|---|---|")
        for r in results:
            value_str = f"{r.value:.4f}" if r.value is not None else "N/A"
            evidence_short = (r.evidence or "")[:60]
            limitations_short = (r.limitations or "")[:60]
            lines.append(
                f"| {r.metric} | {value_str} | {r.status.value} | {evidence_short} | {limitations_short} |"
            )
        lines.append("")

    lines.append("---")
    lines.append("")

    lines.append("## Reliability Results")
    lines.append("")
    lines.append("| Scenario | Status | Details |")
    lines.append("|---|---|---|")
    for r in run.reliability_results:
        details_short = (r.details or "")[:80]
        lines.append(f"| {r.scenario_name} | {r.status.value} | {details_short} |")
    lines.append("")

    lines.append("---")
    lines.append("")

    lines.append("## NOT_MEASURED Metrics")
    lines.append("")
    not_measured = [r for r in run.results if r.status == ResultClassification.NOT_MEASURED]
    if not_measured:
        for r in not_measured:
            lines.append(
                f"- **{r.metric}** ({r.scenario}): {r.limitations or 'No limitations specified.'}"
            )
    else:
        lines.append("No NOT_MEASURED metrics in this run.")
    lines.append("")

    lines.append("---")
    lines.append("")

    lines.append("## Limitations")
    lines.append("")
    lines.append("1. All results are from **DETERMINISTIC FIXTURE** evaluation.")
    lines.append("2. No real audio, STT, TTS, browser, or hardware measurements were taken.")
    lines.append("3. Research results are fixture-based, not real web search.")
    lines.append("4. Vision results are from FakeVisionProvider, not real screenshot analysis.")
    lines.append("5. Memory results use InMemoryMemory, not semantic/vector search.")
    lines.append("6. Prediction calibration is NOT_MEASURED (no calibrated ground truth).")
    lines.append(
        "7. Avatar lip-sync timing accuracy is NOT_MEASURED (no ground-truth timing dataset)."
    )
    lines.append("8. Voice latency values are fixture placeholders, not real measurements.")
    lines.append(
        "9. Computer task success uses FakeActionExecutor, not real filesystem operations."
    )
    lines.append("10. Security policy uses ConservativePolicy in isolation, not full integration.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Generated by MISSMINUTES Evaluation Framework (CHUNK 35)*")
    lines.append("")

    return "\n".join(lines)


def generate_json_report(run: EvaluationRun) -> dict[str, Any]:
    def _dt_str(dt):
        if dt is None:
            return None
        if isinstance(dt, str):
            return dt
        return dt.isoformat()

    return {
        "run_id": str(run.run_id),
        "started_at": _dt_str(run.started_at),
        "completed_at": _dt_str(run.completed_at),
        "environment": {
            "mode": run.environment.mode.value,
            "python_version": run.environment.python_version,
            "platform": run.environment.platform,
            "deterministic_fakes_used": run.environment.deterministic_fakes_used,
            "live_providers_used": run.environment.live_providers_used,
        },
        "results": [
            {
                "metric": r.metric,
                "scenario": r.scenario,
                "case_id": str(r.case_id) if r.case_id else None,
                "value": r.value,
                "status": r.status.value,
                "evidence": r.evidence,
                "limitations": r.limitations,
                "mode": r.mode.value,
            }
            for r in run.results
        ],
        "reliability_results": [
            {
                "scenario_id": str(r.scenario_id),
                "scenario_name": r.scenario_name,
                "status": r.status.value,
                "details": r.details,
                "evidence": r.evidence,
                "mode": r.mode.value,
            }
            for r in run.reliability_results
        ],
        "summary": {
            "total_metrics": run.summary.total_metrics if run.summary else 0,
            "pass_count": run.summary.pass_count if run.summary else 0,
            "fail_count": run.summary.fail_count if run.summary else 0,
            "inconclusive_count": run.summary.inconclusive_count if run.summary else 0,
            "not_measured_count": run.summary.not_measured_count if run.summary else 0,
            "not_applicable_count": run.summary.not_applicable_count if run.summary else 0,
            "reliability_pass": run.summary.reliability_pass if run.summary else 0,
            "reliability_fail": run.summary.reliability_fail if run.summary else 0,
            "reliability_not_applicable": run.summary.reliability_not_applicable
            if run.summary
            else 0,
        }
        if run.summary
        else None,
    }


def save_evaluation_report(run: EvaluationRun, output_dir: Path) -> dict[str, Path]:
    import json as _json
    from datetime import datetime as _dt

    class _DTEncoder(_json.JSONEncoder):
        def default(self, o):
            if isinstance(o, _dt):
                return o.isoformat()
            return super().default(o)

    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "EVALUATION_REPORT.md"
    json_path = output_dir / "latest.json"
    md_content = generate_markdown_report(run)
    md_path.write_text(md_content, encoding="utf-8")
    json_content = _json.dumps(
        generate_json_report(run), indent=2, ensure_ascii=False, cls=_DTEncoder
    )
    json_path.write_text(json_content, encoding="utf-8")
    return {"markdown": md_path, "json": json_path}


def load_previous_run(path: Path) -> EvaluationRun | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        from app.evaluation.models import (
            EnvironmentInfo,
            EvaluationMode,
            EvaluationSummary,
        )

        env_data = data.get("environment", {})
        environment = EnvironmentInfo(
            mode=EvaluationMode(env_data.get("mode", "deterministic")),
            python_version=env_data.get("python_version", ""),
            platform=env_data.get("platform", ""),
            deterministic_fakes_used=env_data.get("deterministic_fakes_used", []),
            live_providers_used=env_data.get("live_providers_used", []),
        )
        results = [
            EvaluationResult(
                metric=r["metric"],
                scenario=r["scenario"],
                case_id=r.get("case_id"),
                value=r.get("value"),
                status=ResultClassification(r["status"]),
                evidence=r.get("evidence"),
                limitations=r.get("limitations"),
                mode=EvaluationMode(r.get("mode", "deterministic")),
            )
            for r in data.get("results", [])
        ]
        reliability_results = [
            ReliabilityResult(
                scenario_id=r["scenario_id"],
                scenario_name=r["scenario_name"],
                status=ResultClassification(r["status"]),
                details=r.get("details"),
                evidence=r.get("evidence"),
                mode=EvaluationMode(r.get("mode", "deterministic")),
            )
            for r in data.get("reliability_results", [])
        ]
        summary_data = data.get("summary")
        summary = None
        if summary_data:
            summary = EvaluationSummary(**summary_data)
        return EvaluationRun(
            run_id=data.get("run_id", ""),
            started_at=data.get("started_at", ""),
            completed_at=data.get("completed_at"),
            environment=environment,
            results=results,
            reliability_results=reliability_results,
            summary=summary,
        )
    except Exception:
        return None


def compare_runs(previous: EvaluationRun, current: EvaluationRun) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    prev_map: dict[str, EvaluationResult] = {}
    for r in previous.results:
        key = f"{r.metric}::{r.scenario}"
        prev_map[key] = r
    for r in current.results:
        key = f"{r.metric}::{r.scenario}"
        prev = prev_map.get(key)
        prev_value = prev.value if prev else None
        comparisons.append(
            {
                "metric": r.metric,
                "scenario": r.scenario,
                "previous_value": prev_value,
                "current_value": r.value,
                "change": (r.value - prev_value)
                if (r.value is not None and prev_value is not None)
                else None,
                "previous_status": prev.status.value if prev else None,
                "current_status": r.status.value,
            }
        )
    return comparisons
