# MISSMINUTES Evaluation Architecture

## Overview

The evaluation framework provides deterministic benchmark scenarios, metric definitions, structured result collection, reliability testing, and report generation for MISSMINUTES.

All evaluation runs fully offline using deterministic fakes. No API keys, network access, microphone, browser, or GUI are required.

## Architecture

```
app/evaluation/
    __init__.py          Package exports
    models.py            Data models for scenarios, metrics, results
    metrics.py           Metric definitions and computation functions
    scenarios.py         Benchmark scenario dataset (10 groups A-J)
    datasets.py          Fixture datasets for all scenarios
    fakes.py             Composite evaluation environment
    runners.py           Deterministic evaluation runners
    reliability.py       Reliability testing scenarios
    reports.py           Report generation (Markdown + JSON)
```

## Scenario Groups

| Group | Category | Description |
|-------|----------|-------------|
| A | STT | Speech-to-text accuracy |
| B | Language Detection | Language and style detection |
| C | Routing | Agent/tool selection |
| D | Planning | Plan generation and validation |
| E | Problem Solving | Bounded loop behavior |
| F | Research | Source retrieval and evidence |
| G | Computer | Safe tool operations |
| H | Browser | Safe browser operations |
| I | Vision | Structured visual observations |
| J | Distributed | Worker dispatch and recovery |
| K | Security | Policy enforcement |
| V | Voice | Pipeline timing (fixtures) |
| AV | Avatar | Event propagation |
| M | Memory | Retrieval success |
| E2E | End-to-End | Full pipeline |
| R | Reliability | Failure handling |

## Metric Definitions

Each metric has:
- **name**: unique identifier
- **category**: evaluation area
- **definition**: what the metric measures
- **unit**: ratio, count, bool, or ms_fixture
- **target**: optional target value

## Deterministic Mode

The default and only required mode. Uses:
- FakeSpeechToText / FakeTextToSpeech
- FakeLanguageDetector
- FakeAIModel
- FakeResearchProvider
- FakeVisionProvider / FakeOcrProvider
- FakeActionExecutor / FakeObservationProvider
- FakeVerifier / FakeCritic / FakePredictor
- FakeWorkerTransport / FakeMasterTransport
- FakeBrowserProvider
- FakeAvatarRenderer
- InMemoryMemory

No real providers, network, or hardware.

## Optional Live Benchmark Mode

If real providers are configured, an optional live mode can measure real-world performance. This is explicitly optional and timestamped.

Live mode results are always labeled separately from deterministic results.

## Reliability Testing

15 reliability scenarios test:
- Provider failure
- Tool failure
- Agent failure
- Planner failure
- Timeout
- Cancellation
- Verification failure
- Inconclusive verification
- Worker failure
- Heartbeat timeout
- Browser failure
- Voice interruption
- TTS failure
- STT failure
- Avatar renderer failure

## Result Classification

| Status | Meaning |
|--------|---------|
| PASS | Metric met expected threshold |
| FAIL | Metric did not meet threshold |
| INCONCLUSIVE | Result ambiguous, not converted to PASS |
| NOT_MEASURED | No real data/provider available |
| NOT_APPLICABLE | Metric not relevant to scenario |

## Anti-Fabrication Policy

1. Never invent STT accuracy
2. Never invent latency
3. Never invent avatar synchronization accuracy
4. Never invent prediction calibration
5. Never invent browser success rate
6. Never invent real-world computer task success
7. Never invent research freshness
8. Never invent memory semantic quality

If unavailable: report NOT_MEASURED and explain why.

## How to Run

```python
from app.evaluation.runners import run_all_evaluation_sync

run = run_all_evaluation_sync()
```

Or from the command line:

```bash
python -c "from app.evaluation.runners import run_all_evaluation_sync; run = run_all_evaluation_sync(); print(f'PASS: {run.summary.pass_count}, FAIL: {run.summary.fail_count}')"
```

## How to Interpret Results

1. Check the summary for pass/fail counts
2. Review NOT_MEASURED metrics for what was not tested
3. Check reliability results for failure handling
4. Review limitations for each result
5. Compare with previous runs if available

## Regression Gates

The framework enforces:
- Zero security bypasses
- Zero infinite loops
- Zero unhandled deterministic failures
- INCONCLUSIVE != PASS
- Duplicate results not applied
- Unsafe terminal commands denied
- Unsafe browser schemes denied
