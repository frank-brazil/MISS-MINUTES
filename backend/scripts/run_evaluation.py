"""Run the full evaluation suite and save results."""

import sys
from pathlib import Path

_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

_project_root = Path(__file__).resolve().parent.parent.parent

from app.evaluation.reports import save_evaluation_report  # noqa: E402
from app.evaluation.runners import run_all_evaluation_sync  # noqa: E402

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

paths = save_evaluation_report(run, _project_root / "data" / "evaluation")
print(f"Markdown: {paths['markdown']}")
print(f"JSON: {paths['json']}")
