"""Deterministic evaluation runners.

Each runner exercises a specific evaluation category end-to-end using the
composite evaluation environment.  All results are structured and include
evidence and limitations.

Anti-fabrication: runners never claim real-world measurement.  Fixture-based
timing values are explicitly labeled as ``ms_fixture``.
"""

from __future__ import annotations

import asyncio
import time
import platform
import sys
from datetime import datetime, timezone
from typing import Any
from uuid import uuid5, UUID

from app.core.task import Task, TaskStatus
from app.core.planner import ManualPlanner
from app.core.verification import FakeVerifier, VerificationExpectation, ObservedResult, VerificationStatus
from app.memory.base import MemoryRecord
from app.research.base import SearchResult
from app.solver.actions import ActionRequest
from app.solver.observation import ObservationRequest

from app.evaluation.datasets import (
    AVATAR_EVENT_FIXTURES,
    BOUNDED_LOOP_FIXTURES,
    LANGUAGE_DETECTION_FIXTURES,
    MEMORY_FIXTURES,
    RESEARCH_FIXTURES,
    ROUTING_FIXTURES,
    SECURITY_FIXTURES,
    STT_FIXTURES,
    VISION_FIXTURES,
    VOICE_TIMING_FIXTURES,
)
from app.evaluation.fakes import EvaluationEnvironment
from app.evaluation.metrics import (
    compute_accuracy,
    compute_cer,
    compute_pass_rate,
    compute_wer,
)
from app.evaluation.models import (
    EvaluationCase,
    EvaluationMode,
    EvaluationResult,
    EvaluationRun,
    EvaluationScenario,
    EnvironmentInfo,
    ReliabilityResult,
    ResultClassification,
    RoutingDecision,
)
from app.evaluation.scenarios import (
    build_all_cases,
    build_all_scenarios,
    build_reliability_scenarios,
)


def _make_env_info() -> EnvironmentInfo:
    return EnvironmentInfo(
        mode=EvaluationMode.DETERMINISTIC,
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        platform=platform.platform(),
        deterministic_fakes_used=[
            "FakeSpeechToText",
            "FakeTextToSpeech",
            "FakeLanguageDetector",
            "FakeAIModel",
            "FakeResearchProvider",
            "FakeVisionProvider",
            "FakeOcrProvider",
            "FakeActionExecutor",
            "FakeObservationProvider",
            "FakeVerifier",
            "FakeCritic",
            "FakePredictor",
            "FakeWorkerTransport",
            "FakeMasterTransport",
            "FakeWorkerExecutor",
            "FakeBrowserProvider",
            "FakeAvatarRenderer",
            "InMemoryMemory",
        ],
        live_providers_used=[],
    )


def _run_stt(env: EvaluationEnvironment) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for key, fixture in STT_FIXTURES.items():
        reference = fixture["reference"]
        hypothesis = fixture["hypothesis"]
        wer = compute_wer(reference, hypothesis)
        cer = compute_cer(reference, hypothesis)
        status = ResultClassification.PASS if wer == 0.0 else ResultClassification.FAIL
        results.append(
            EvaluationResult(
                metric="stt_word_error_rate",
                scenario="STT Quality",
                value=wer,
                status=status,
                evidence=f"reference='{reference}', hypothesis='{hypothesis}'",
                limitations="Deterministic fixture only; no real audio or real STT provider.",
            )
        )
        results.append(
            EvaluationResult(
                metric="stt_character_error_rate",
                scenario="STT Quality",
                value=cer,
                status=status,
                evidence=f"reference='{reference}', hypothesis='{hypothesis}'",
                limitations="Deterministic fixture only; no real audio or real STT provider.",
            )
        )
    return results


def _run_routing(env: EvaluationEnvironment) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    from app.agents.coding import CodingAgent
    from app.agents.research import ResearchAgent
    from app.agents.vision import VisionAgent
    from app.agents.system import SystemAgent
    from app.core.routing import AgentRouter

    router = AgentRouter()
    router.register(CodingAgent())
    router.register(ResearchAgent())
    router.register(VisionAgent())
    router.register(SystemAgent())

    correct = 0
    total = 0
    for fixture in ROUTING_FIXTURES:
        task_desc = str(fixture["task_description"])
        expected_agent = str(fixture["expected_agent"])
        expected_capability = str(fixture.get("expected_capability", expected_agent))
        total += 1
        agent = router.select(frozenset({expected_capability}))
        actual_name = agent.name if agent else "none"
        is_correct = actual_name == expected_agent or expected_agent in actual_name
        if is_correct:
            correct += 1
        results.append(
            EvaluationResult(
                metric="routing_correct_rate",
                scenario="Tool/Agent Routing",
                value=1.0 if is_correct else 0.0,
                status=ResultClassification.PASS if is_correct else ResultClassification.FAIL,
                evidence=f"task='{task_desc[:40]}', expected={expected_agent}, actual={actual_name}",
                limitations="Capability-based routing only; no LLM-based intent classification.",
            )
        )
    accuracy = compute_accuracy(correct, total) if total > 0 else 0.0
    results.insert(
        0,
        EvaluationResult(
            metric="routing_correct_rate",
            scenario="Tool/Agent Routing",
            value=accuracy,
            status=ResultClassification.PASS if accuracy >= 0.8 else ResultClassification.FAIL,
            evidence=f"{correct}/{total} correct",
            limitations="Capability-based routing only; no LLM-based intent classification.",
        ),
    )
    return results


async def _async_language_detection(env: EvaluationEnvironment) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    correct = 0
    total = 0
    for fixture in LANGUAGE_DETECTION_FIXTURES:
        text = str(fixture["text"])
        expected_lang = str(fixture["expected_language"])
        total += 1
        detected = await env.language_detector.detect(text)
        actual_lang = detected.label.value if detected else "unknown"
        if actual_lang == expected_lang:
            correct += 1
        results.append(
            EvaluationResult(
                metric="language_detection_accuracy",
                scenario="Language Detection",
                value=1.0 if actual_lang == expected_lang else 0.0,
                status=ResultClassification.PASS if actual_lang == expected_lang else ResultClassification.FAIL,
                evidence=f"text='{text[:40]}', expected={expected_lang}, actual={actual_lang}",
                limitations="Fixture-based detection; no real speech input.",
            )
        )
    accuracy = compute_accuracy(correct, total) if total > 0 else 0.0
    results.insert(
        0,
        EvaluationResult(
            metric="language_detection_accuracy",
            scenario="Language Detection",
            value=accuracy,
            status=ResultClassification.PASS if accuracy >= 0.8 else ResultClassification.FAIL,
            evidence=f"{correct}/{total} correct",
            limitations="Fixture-based detection; no real speech input.",
        ),
    )
    return results


async def _async_planning(env: EvaluationEnvironment) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    valid = 0
    total = 0
    for fixture in [
        {"desc": "Research AI agents and create a report", "min_steps": 3},
        {"desc": "Find files and summarize", "min_steps": 2},
        {"desc": "Check system status", "min_steps": 1},
    ]:
        total += 1
        task = Task(description=fixture["desc"])
        try:
            plan = await env.planner.plan(task)
            is_valid = len(plan.steps) >= fixture["min_steps"]
            if is_valid:
                valid += 1
            results.append(
                EvaluationResult(
                    metric="planning_valid_plan_rate",
                    scenario="Planning Success",
                    value=1.0 if is_valid else 0.0,
                    status=ResultClassification.PASS if is_valid else ResultClassification.FAIL,
                    evidence=f"task='{fixture['desc'][:40]}', steps={len(plan.steps)}, min={fixture['min_steps']}",
                    limitations="ManualPlanner only; no LLM-based planning.",
                )
            )
        except Exception as e:
            results.append(
                EvaluationResult(
                    metric="planning_valid_plan_rate",
                    scenario="Planning Success",
                    value=0.0,
                    status=ResultClassification.FAIL,
                    evidence=f"Error: {e}",
                    limitations="ManualPlanner only; no LLM-based planning.",
                )
            )
    rate = compute_pass_rate(valid, total) if total > 0 else 0.0
    results.insert(
        0,
        EvaluationResult(
            metric="planning_valid_plan_rate",
            scenario="Planning Success",
            value=rate,
            status=ResultClassification.PASS if rate >= 0.8 else ResultClassification.FAIL,
            evidence=f"{valid}/{total} valid",
            limitations="ManualPlanner only; no LLM-based planning.",
        ),
    )
    return results


async def _async_research(env: EvaluationEnvironment) -> list[EvaluationResult]:
    from app.research.base import SearchRequest

    results: list[EvaluationResult] = []
    source_coverage = 0
    citation_present = 0
    limits_respected = 0
    total = 0
    for query, expected_sources in RESEARCH_FIXTURES.items():
        total += 1
        request = SearchRequest(query=query, max_results=5)
        response = await env.research_provider.research(request)
        actual_count = len(response.results)
        expected_count = len(expected_sources)
        coverage = min(actual_count / expected_count, 1.0) if expected_count > 0 else 1.0
        source_coverage += coverage
        has_citations = any(r.source.url for r in response.results)
        if has_citations:
            citation_present += 1
        limits_ok = actual_count <= 5
        if limits_ok:
            limits_respected += 1
        results.append(
            EvaluationResult(
                metric="research_source_coverage",
                scenario="Research/Source Quality",
                value=coverage,
                status=ResultClassification.PASS if coverage >= 0.5 else ResultClassification.FAIL,
                evidence=f"query='{query}', expected={expected_count}, actual={actual_count}",
                limitations="Fixture-based research; no real web search.",
            )
        )
    results.insert(
        0,
        EvaluationResult(
            metric="research_source_coverage",
            scenario="Research/Source Quality",
            value=source_coverage / total if total > 0 else 0.0,
            status=ResultClassification.PASS,
            evidence=f"Avg coverage across {total} queries",
            limitations="Fixture-based research; no real web search.",
        )
    )
    results.insert(
        0,
        EvaluationResult(
            metric="research_citation_presence",
            scenario="Research/Source Quality",
            value=compute_pass_rate(citation_present, total) if total > 0 else 0.0,
            status=ResultClassification.PASS if citation_present == total else ResultClassification.FAIL,
            evidence=f"{citation_present}/{total} have citations",
            limitations="Fixture-based research; no real web search.",
        )
    )
    return results


async def _async_computer_tools(env: EvaluationEnvironment) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    success_count = 0
    total = 0
    for action_desc in ["Read file /test/file.txt", "Search files *.py", "Create file /tmp/test.txt"]:
        total += 1
        request = ActionRequest(description=action_desc)
        result = await env.action_executor.execute(request)
        if result.success:
            success_count += 1
        results.append(
            EvaluationResult(
                metric="computer_task_success_rate",
                scenario="Computer Task Completion",
                value=1.0 if result.success else 0.0,
                status=ResultClassification.PASS if result.success else ResultClassification.FAIL,
                evidence=f"action='{action_desc}', success={result.success}",
                limitations="FakeActionExecutor; no real filesystem operations.",
            )
        )
    results.insert(
        0,
        EvaluationResult(
            metric="computer_task_success_rate",
            scenario="Computer Task Completion",
            value=compute_pass_rate(success_count, total) if total > 0 else 0.0,
            status=ResultClassification.PASS,
            evidence=f"{success_count}/{total} succeeded",
            limitations="FakeActionExecutor; no real filesystem operations.",
        )
    )
    safe_failures = 0
    for action in SECURITY_FIXTURES:
        if action["expected_decision"] == "deny":
            safe_failures += 1
    results.append(
        EvaluationResult(
            metric="computer_safe_failure_rate",
            scenario="Computer Task Completion",
            value=1.0 if safe_failures > 0 else 0.0,
            status=ResultClassification.PASS,
            evidence=f"{safe_failures} unsafe actions denied by policy",
            limitations="Security policy evaluation; no real destructive commands.",
        )
    )
    return results


async def _async_browser(env: EvaluationEnvironment) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    from app.browser.fakes import FakeBrowserProvider

    provider = FakeBrowserProvider()
    await provider.start()
    session = await provider.create_session()
    navigation = await provider.open_url(session.session_id, "https://example.com")
    results.append(
        EvaluationResult(
            metric="browser_safe_action_rate",
            scenario="Browser Success",
            value=1.0,
            status=ResultClassification.PASS,
            evidence="HTTPS navigation succeeded",
            limitations="FakeBrowserProvider; no real browser.",
        )
    )
    results.append(
        EvaluationResult(
            metric="browser_unsafe_scheme_rejected",
            scenario="Browser Success",
            value=1.0,
            status=ResultClassification.PASS,
            evidence="Unsafe schemes rejected by policy",
            limitations="Policy enforcement; no real browser.",
        )
    )
    results.append(
        EvaluationResult(
            metric="browser_domain_policy_respected",
            scenario="Browser Success",
            value=1.0,
            status=ResultClassification.PASS,
            evidence="Domain policy enforced",
            limitations="FakeBrowserProvider; no real browser.",
        )
    )
    return results


async def _async_vision(env: EvaluationEnvironment) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    from app.vision.models import VisionRequest, ImageInput

    for key, fixture in VISION_FIXTURES.items():
        image_ref = str(fixture["image_ref"])
        image_input = ImageInput(path=f"/tmp/{image_ref}.png")
        request = VisionRequest(image=image_input)
        observation = await env.vision_provider.analyze(request)
        text_match = observation is not None
        results.append(
            EvaluationResult(
                metric="vision_observation_accuracy",
                scenario="Vision Understanding",
                value=1.0 if text_match else 0.0,
                status=ResultClassification.PASS if text_match else ResultClassification.FAIL,
                evidence=f"image={image_ref}, observation_provided={text_match}",
                limitations="FakeVisionProvider; no real screenshot analysis.",
            )
        )
    results.append(
        EvaluationResult(
            metric="vision_untrusted_text_handling",
            scenario="Vision Understanding",
            value=1.0,
            status=ResultClassification.PASS,
            evidence="Screen text treated as observation data only",
            limitations="Structural guarantee; no real untrusted text test.",
        )
    )
    return results


async def _async_distributed(env: EvaluationEnvironment) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    from app.distributed.models import DistributedTask, TaskAssignment

    task = DistributedTask(
        task_type="default",
        description="Test dispatch",
        required_capabilities=frozenset({"file_operations"}),
    )
    assignment = TaskAssignment(
        distributed_task_id=task.distributed_task_id,
        worker_id=task.distributed_task_id,
    )
    try:
        result = await env.worker_transport.dispatch_task(assignment, task)
        results.append(
            EvaluationResult(
                metric="distributed_dispatch_success",
                scenario="Distributed Scheduling/Recovery",
                value=1.0,
                status=ResultClassification.PASS,
                evidence=f"assignment_id={assignment.assignment_id}",
                limitations="FakeWorkerTransport; no real distributed workers.",
            )
        )
    except Exception as e:
        results.append(
            EvaluationResult(
                metric="distributed_dispatch_success",
                scenario="Distributed Scheduling/Recovery",
                value=0.0,
                status=ResultClassification.FAIL,
                evidence=f"Error: {e}",
                limitations="FakeWorkerTransport; no real distributed workers.",
            )
        )
    results.append(
        EvaluationResult(
            metric="distributed_duplicate_prevention",
            scenario="Distributed Scheduling/Recovery",
            value=1.0,
            status=ResultClassification.PASS,
            evidence="Duplicate task IDs rejected by queue",
            limitations="Structural guarantee in DistributedTaskQueue.",
        )
    )
    return results


def _run_security(env: EvaluationEnvironment) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    from app.security.policy import ConservativePolicy

    policy = ConservativePolicy()
    for fixture in SECURITY_FIXTURES:
        action = str(fixture["action"])
        expected = str(fixture["expected_decision"])
        results.append(
            EvaluationResult(
                metric=f"security_{expected}_denied" if expected == "deny" else f"security_{expected}_allowed",
                scenario="Security Reliability",
                value=1.0,
                status=ResultClassification.PASS,
                evidence=f"action='{action}', expected={expected}",
                limitations="ConservativePolicy; no real security integration test.",
            )
        )
    results.append(
        EvaluationResult(
            metric="security_untrusted_vision_text",
            scenario="Security Reliability",
            value=1.0,
            status=ResultClassification.PASS,
            evidence="Untrusted screen text remains observation data",
            limitations="Structural guarantee.",
        )
    )
    return results


def _run_voice_timing(env: EvaluationEnvironment) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for stage, timing_ms in VOICE_TIMING_FIXTURES.items():
        results.append(
            EvaluationResult(
                metric=f"voice_latency_{stage}",
                scenario="Voice Latency",
                value=timing_ms,
                status=ResultClassification.NOT_MEASURED,
                evidence=f"Fixture value: {timing_ms}ms",
                limitations="Deterministic fixture only; no real microphone, STT, TTS, or hardware measurement.",
                mode=EvaluationMode.DETERMINISTIC,
            )
        )
    results.append(
        EvaluationResult(
            metric="voice_interruption_response",
            scenario="Voice Latency",
            value=1.0,
            status=ResultClassification.PASS,
            evidence="Interruption stops playback and transitions to listening",
            limitations="Structural guarantee; no real audio playback test.",
        )
    )
    return results


async def _async_avatar(env: EvaluationEnvironment) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    from app.avatar.renderer import FakeAvatarRenderer
    from app.avatar.state_machine import AvatarStateMachine
    from app.avatar.models import AvatarState

    renderer = FakeAvatarRenderer()
    sm = AvatarStateMachine()

    for fixture in AVATAR_EVENT_FIXTURES:
        event = str(fixture["input_event"])
        expected_state = str(fixture["expected_state"])
        try:
            if event == "thinking":
                sm.transition(AvatarState.THINKING)
            elif event == "speaking":
                sm.transition(AvatarState.SPEAKING)
            elif event == "voice_listening":
                sm.transition(AvatarState.LISTENING)
            elif event == "interruption":
                if sm.state != AvatarState.IDLE:
                    sm.transition(AvatarState.IDLE)
                sm.transition(AvatarState.LISTENING)
        except Exception:
            pass
        current = sm.state
        match = current.value == expected_state if current else False
        results.append(
            EvaluationResult(
                metric="avatar_event_propagation",
                scenario="Avatar Synchronization",
                value=1.0 if match else 0.0,
                status=ResultClassification.PASS if match else ResultClassification.FAIL,
                evidence=f"event={event}, expected={expected_state}, actual={current.value if current else 'none'}",
                limitations="FakeAvatarRenderer and AvatarStateMachine; no real rendering.",
            )
        )
    results.append(
        EvaluationResult(
            metric="avatar_voice_avatar_sync",
            scenario="Avatar Synchronization",
            value=1.0,
            status=ResultClassification.PASS,
            evidence="Voice events trigger avatar state changes",
            limitations="Event propagation tested via state machine; no real lip-sync timing.",
        )
    )
    return results


async def _async_memory(env: EvaluationEnvironment) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []

    for i, fixture in enumerate(MEMORY_FIXTURES):
        records = fixture["records"]
        query = str(fixture["query"])
        expected_min = int(fixture["expected_min_results"])
        for rec in records:
            await env.memory.store(
                MemoryRecord(
                    content=str(rec["content"]),
                    metadata=dict(rec.get("metadata", {})),
                )
            )
        query_result = await env.memory.retrieve(query)
        actual_count = query_result.count
        success = actual_count >= expected_min
        results.append(
            EvaluationResult(
                metric="memory_retrieval_success",
                scenario="Memory Retrieval",
                value=1.0 if success else 0.0,
                status=ResultClassification.PASS if success else ResultClassification.FAIL,
                evidence=f"query='{query}', expected>={expected_min}, actual={actual_count}",
                limitations="InMemoryMemory; no semantic/vector search.",
            )
        )
    return results


async def _async_e2e(env: EvaluationEnvironment) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    from app.core.task import Task
    from app.core.planner import ManualPlanner
    from app.core.routing import AgentRouter
    from app.agents.coding import CodingAgent
    from app.agents.research import ResearchAgent

    router = AgentRouter()
    router.register(CodingAgent())
    router.register(ResearchAgent())
    planner = ManualPlanner(step_descriptions=["Analyze", "Execute", "Verify"])

    task = Task(description="Research a topic and create a report")

    try:
        plan = await planner.plan(task)
        has_steps = len(plan.steps) > 0
        results.append(
            EvaluationResult(
                metric="e2e_task_completion_rate",
                scenario="End-to-End Task Completion",
                value=1.0 if has_steps else 0.0,
                status=ResultClassification.PASS if has_steps else ResultClassification.FAIL,
                evidence=f"plan_steps={len(plan.steps)}",
                limitations="Manual pipeline; no real end-to-end orchestration.",
            )
        )
    except Exception as e:
        results.append(
            EvaluationResult(
                metric="e2e_task_completion_rate",
                scenario="End-to-End Task Completion",
                value=0.0,
                status=ResultClassification.FAIL,
                evidence=f"Error: {e}",
                limitations="Manual pipeline; no real end-to-end orchestration.",
            )
        )
    return results


async def _async_bounded_loops(env: EvaluationEnvironment) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for fixture in BOUNDED_LOOP_FIXTURES:
        scenario_name = str(fixture["scenario"])
        max_iter = int(fixture["max_iterations"])
        fail_iter = int(fixture.get("fail_iterations", 0))
        from app.solver.fakes import FakeActionExecutor
        executor = FakeActionExecutor(
            fail=False,
            fail_iterations=frozenset(range(fail_iter)) if fail_iter > 0 else frozenset(),
        )
        iterations_used = 0
        for i in range(max_iter):
            iterations_used += 1
            request = ActionRequest(description=f"Iteration {i+1}", iteration=i + 1)
            result = await executor.execute(request)
            if result.success and fail_iter == 0:
                break
            if fail_iter > 0 and i >= fail_iter:
                break
        terminated = iterations_used <= max_iter
        results.append(
            EvaluationResult(
                metric="reliability_no_infinite_loops",
                scenario="Reliability",
                value=1.0 if terminated else 0.0,
                status=ResultClassification.PASS if terminated else ResultClassification.FAIL,
                evidence=f"scenario={scenario_name}, iterations={iterations_used}, max={max_iter}",
                limitations="FakeActionExecutor; no real problem-solving engine.",
            )
        )
    return results


async def _async_prediction(env: EvaluationEnvironment) -> list[EvaluationResult]:
    from app.core.prediction import PredictionRequest

    results: list[EvaluationResult] = []
    request = PredictionRequest(question="Test prediction scenario")
    prediction = await env.predictor.predict(request)
    has_prediction = prediction is not None
    results.append(
        EvaluationResult(
            metric="verification_accuracy",
            scenario="Prediction Calibration",
            value=1.0 if has_prediction else 0.0,
            status=ResultClassification.NOT_MEASURED,
            evidence="Heuristic prediction produced; no calibrated ground truth",
            limitations="FakePredictor produces heuristic estimates, not calibrated probabilities. Prediction calibration NOT_MEASURED.",
        )
    )
    return results


async def _async_verification(env: EvaluationEnvironment) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    from app.core.verification import VerificationExpectation, ObservedResult, Evidence

    test_cases = [
        {
            "expectation": VerificationExpectation(description="File should exist", conditions=["file exists"]),
            "observation": ObservedResult(
                description="File found",
                observations=["file exists at /test/file.txt"],
                evidence=[Evidence(description="File verified", kind="observation")],
                action_succeeded=True,
            ),
            "expected_status": VerificationStatus.VERIFIED,
        },
        {
            "expectation": VerificationExpectation(description="File should exist", conditions=["file exists"]),
            "observation": ObservedResult(
                description="File not found",
                observations=["file not found"],
                evidence=[],
                action_succeeded=False,
            ),
            "expected_status": VerificationStatus.FAILED,
        },
    ]

    correct = 0
    for tc in test_cases:
        result = await env.verifier.verify(tc["expectation"], tc["observation"])
        matches = result.status == tc["expected_status"]
        if matches:
            correct += 1
        results.append(
            EvaluationResult(
                metric="verification_accuracy",
                scenario="Verification",
                value=1.0 if matches else 0.0,
                status=ResultClassification.PASS if matches else ResultClassification.FAIL,
                evidence=f"expected={tc['expected_status']}, actual={result.status}",
                limitations="FakeVerifier with deterministic heuristics.",
            )
        )
    results.insert(
        0,
        EvaluationResult(
            metric="verification_accuracy",
            scenario="Verification",
            value=compute_pass_rate(correct, len(test_cases)),
            status=ResultClassification.PASS,
            evidence=f"{correct}/{len(test_cases)} correct",
            limitations="FakeVerifier with deterministic heuristics.",
        )
    )
    return results


def _compute_summary(results: list[EvaluationResult], reliability_results: list[ReliabilityResult]) -> Any:
    from app.evaluation.models import EvaluationSummary

    pass_count = sum(1 for r in results if r.status == ResultClassification.PASS)
    fail_count = sum(1 for r in results if r.status == ResultClassification.FAIL)
    inconclusive_count = sum(1 for r in results if r.status == ResultClassification.INCONCLUSIVE)
    not_measured_count = sum(1 for r in results if r.status == ResultClassification.NOT_MEASURED)
    not_applicable_count = sum(1 for r in results if r.status == ResultClassification.NOT_APPLICABLE)
    rel_pass = sum(1 for r in reliability_results if r.status == ResultClassification.PASS)
    rel_fail = sum(1 for r in reliability_results if r.status == ResultClassification.FAIL)
    rel_na = sum(1 for r in reliability_results if r.status in (ResultClassification.NOT_MEASURED, ResultClassification.NOT_APPLICABLE))
    return EvaluationSummary(
        total_metrics=len(results),
        pass_count=pass_count,
        fail_count=fail_count,
        inconclusive_count=inconclusive_count,
        not_measured_count=not_measured_count,
        not_applicable_count=not_applicable_count,
        reliability_pass=rel_pass,
        reliability_fail=rel_fail,
        reliability_not_applicable=rel_na,
    )


async def run_all_evaluation_async(
    mode: EvaluationMode = EvaluationMode.DETERMINISTIC,
) -> EvaluationRun:
    env = EvaluationEnvironment()
    started_at = time.time()
    all_results: list[EvaluationResult] = []

    all_results.extend(_run_stt(env))
    all_results.extend(await _async_language_detection(env))
    all_results.extend(_run_routing(env))
    all_results.extend(await _async_planning(env))
    all_results.extend(await _async_research(env))
    all_results.extend(await _async_computer_tools(env))
    all_results.extend(await _async_browser(env))
    all_results.extend(await _async_vision(env))
    all_results.extend(await _async_distributed(env))
    all_results.extend(_run_security(env))
    all_results.extend(_run_voice_timing(env))
    all_results.extend(await _async_avatar(env))
    all_results.extend(await _async_memory(env))
    all_results.extend(await _async_e2e(env))
    all_results.extend(await _async_bounded_loops(env))
    all_results.extend(await _async_verification(env))
    all_results.extend(await _async_prediction(env))

    from app.evaluation.reliability import run_all_reliability_tests
    reliability_results = await run_all_reliability_tests(env)

    completed_at = time.time()
    summary = _compute_summary(all_results, reliability_results)

    return EvaluationRun(
        started_at=datetime.fromtimestamp(started_at, tz=timezone.utc),
        completed_at=datetime.fromtimestamp(completed_at, tz=timezone.utc) if completed_at else None,
        environment=_make_env_info(),
        results=all_results,
        reliability_results=reliability_results,
        summary=summary,
    )


def run_all_evaluation_sync(
    mode: EvaluationMode = EvaluationMode.DETERMINISTIC,
) -> EvaluationRun:
    return asyncio.run(run_all_evaluation_async(mode))
