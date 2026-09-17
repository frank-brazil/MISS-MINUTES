"""Run the full evaluation suite and save results."""

from pathlib import Path

from app.evaluation.reports import save_evaluation_report
from app.evaluation.runners import run_all_evaluation_sync

run = run_all_evaluation_sync()
s = run.summary
print(f"Total: {s.total_metrics}")
print(f"PASS: {s.pass_count}")
print(f"FAIL: {s.fail_count}")
print(f"INCONCLUSIVE: {s.inconclusive_count}")
print(f"NOT_MEASURED: {s.not_measured_count}")
print(f"NOT_APPLICABLE: {s.not_applicable_count}")
print(f"Reliability PASS: {s.reliability_pass}")
print(f"Reliability FAIL: {s.reliability_fail}")
print(f"Reliability N/A: {s.reliability_not_applicable}")
print()

paths = save_evaluation_report(run, Path("data/evaluation"))
print(f"Markdown: {paths['markdown']}")
print(f"JSON: {paths['json']}")
