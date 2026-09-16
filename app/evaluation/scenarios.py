"""Benchmark scenario definitions for evaluation.

Each scenario maps to a specific evaluation category and contains one or more
evaluation cases with deterministic inputs and expected behaviors.

Scenarios are labeled A-J following the PRD specification.
"""

import uuid

from app.evaluation.datasets import (
    AVATAR_EVENT_FIXTURES,
    BOUNDED_LOOP_FIXTURES,
    DISTRIBUTED_FIXTURES,
    LANGUAGE_DETECTION_FIXTURES,
    MEMORY_FIXTURES,
    PLANNING_FIXTURES,
    RELIABILITY_SCENARIOS,
    RESEARCH_FIXTURES,
    ROUTING_FIXTURES,
    SECURITY_FIXTURES,
    STT_FIXTURES,
    VISION_FIXTURES,
    VOICE_TIMING_FIXTURES,
)
from app.evaluation.models import (
    EvaluationCase,
    EvaluationCategory,
    EvaluationScenario,
    ReliabilityScenario,
    RoutingDecision,
    RoutingMetadata,
)


def build_stt_scenario() -> EvaluationScenario:
    return EvaluationScenario(
        scenario_id=uuid.UUID("a0000000-0000-0000-0000-000000000001"),
        name="STT Quality",
        category=EvaluationCategory.STT,
        description="Evaluate speech-to-text accuracy using deterministic fixture transcripts.",
        tags=frozenset({"stt", "fixture"}),
    )


def build_language_detection_scenario() -> EvaluationScenario:
    return EvaluationScenario(
        scenario_id=uuid.UUID("a0000000-0000-0000-0000-000000000002"),
        name="Language Detection",
        category=EvaluationCategory.LANGUAGE_DETECTION,
        description="Evaluate language and style detection accuracy across English, Hindi, and Hinglish.",
        tags=frozenset({"language", "multilingual", "fixture"}),
    )


def build_routing_scenario() -> EvaluationScenario:
    return EvaluationScenario(
        scenario_id=uuid.UUID("a0000000-0000-0000-0000-000000000003"),
        name="Tool/Agent Routing",
        category=EvaluationCategory.TOOL_AGENT_ROUTING,
        description="Evaluate agent and tool selection correctness.",
        tags=frozenset({"routing", "agents", "tools"}),
    )


def build_planning_scenario() -> EvaluationScenario:
    return EvaluationScenario(
        scenario_id=uuid.UUID("a0000000-0000-0000-0000-000000000004"),
        name="Planning Success",
        category=EvaluationCategory.PLANNING,
        description="Evaluate plan generation and validation.",
        tags=frozenset({"planning", "validation"}),
    )


def build_problem_solving_scenario() -> EvaluationScenario:
    return EvaluationScenario(
        scenario_id=uuid.UUID("a0000000-0000-0000-0000-000000000005"),
        name="Problem-Solving Completion",
        category=EvaluationCategory.PROBLEM_SOLVING,
        description="Evaluate bounded problem-solving loop behavior and completion.",
        tags=frozenset({"solver", "bounded", "loop"}),
    )


def build_research_scenario() -> EvaluationScenario:
    return EvaluationScenario(
        scenario_id=uuid.UUID("a0000000-0000-0000-0000-000000000006"),
        name="Research/Source Quality",
        category=EvaluationCategory.RESEARCH,
        description="Evaluate research source retrieval and evidence handling.",
        tags=frozenset({"research", "sources", "fixture"}),
    )


def build_computer_scenario() -> EvaluationScenario:
    return EvaluationScenario(
        scenario_id=uuid.UUID("a0000000-0000-0000-0000-000000000007"),
        name="Computer Task Completion",
        category=EvaluationCategory.COMPUTER,
        description="Evaluate safe computer tool operations.",
        tags=frozenset({"computer", "tools", "files", "terminal"}),
    )


def build_browser_scenario() -> EvaluationScenario:
    return EvaluationScenario(
        scenario_id=uuid.UUID("a0000000-0000-0000-0000-000000000008"),
        name="Browser Success",
        category=EvaluationCategory.BROWSER,
        description="Evaluate safe browser operations and policy enforcement.",
        tags=frozenset({"browser", "security", "policy"}),
    )


def build_vision_scenario() -> EvaluationScenario:
    return EvaluationScenario(
        scenario_id=uuid.UUID("a0000000-0000-0000-0000-000000000009"),
        name="Vision Understanding",
        category=EvaluationCategory.VISION,
        description="Evaluate structured visual observation accuracy.",
        tags=frozenset({"vision", "ocr", "fixture"}),
    )


def build_distributed_scenario() -> EvaluationScenario:
    return EvaluationScenario(
        scenario_id=uuid.UUID("a0000000-0000-0000-0000-000000000010"),
        name="Distributed Scheduling/Recovery",
        category=EvaluationCategory.DISTRIBUTED,
        description="Evaluate worker dispatch, retry, reroute, and duplicate prevention.",
        tags=frozenset({"distributed", "workers", "scheduling"}),
    )


def build_security_scenario() -> EvaluationScenario:
    return EvaluationScenario(
        scenario_id=uuid.UUID("a0000000-0000-0000-0000-000000000011"),
        name="Security Reliability",
        category=EvaluationCategory.SECURITY,
        description="Evaluate security denial, confirmation, and policy enforcement.",
        tags=frozenset({"security", "policy", "confirmation"}),
    )


def build_voice_scenario() -> EvaluationScenario:
    return EvaluationScenario(
        scenario_id=uuid.UUID("a0000000-0000-0000-0000-000000000012"),
        name="Voice Latency",
        category=EvaluationCategory.VOICE,
        description="Evaluate voice pipeline timing using deterministic fixture measurements.",
        tags=frozenset({"voice", "latency", "fixture"}),
    )


def build_avatar_scenario() -> EvaluationScenario:
    return EvaluationScenario(
        scenario_id=uuid.UUID("a0000000-0000-0000-0000-000000000013"),
        name="Avatar Synchronization",
        category=EvaluationCategory.AVATAR,
        description="Evaluate avatar event propagation and voice/avatar synchronization.",
        tags=frozenset({"avatar", "events", "synchronization"}),
    )


def build_memory_scenario() -> EvaluationScenario:
    return EvaluationScenario(
        scenario_id=uuid.UUID("a0000000-0000-0000-0000-000000000014"),
        name="Memory Retrieval",
        category=EvaluationCategory.MEMORY,
        description="Evaluate memory retrieval success and relevance.",
        tags=frozenset({"memory", "retrieval"}),
    )


def build_e2e_scenario() -> EvaluationScenario:
    return EvaluationScenario(
        scenario_id=uuid.UUID("a0000000-0000-0000-0000-000000000015"),
        name="End-to-End Task Completion",
        category=EvaluationCategory.END_TO_END,
        description="Evaluate full pipeline from input to verified response.",
        tags=frozenset({"e2e", "pipeline", "integration"}),
    )


def build_reliability_scenario_group() -> EvaluationScenario:
    return EvaluationScenario(
        scenario_id=uuid.UUID("a0000000-0000-0000-0000-000000000016"),
        name="Reliability",
        category=EvaluationCategory.RELIABILITY,
        description="Evaluate failure handling, bounded loops, timeout, and cancellation.",
        tags=frozenset({"reliability", "failure", "bounded"}),
    )


ALL_SCENARIOS: list[EvaluationScenario] = [
    build_stt_scenario(),
    build_language_detection_scenario(),
    build_routing_scenario(),
    build_planning_scenario(),
    build_problem_solving_scenario(),
    build_research_scenario(),
    build_computer_scenario(),
    build_browser_scenario(),
    build_vision_scenario(),
    build_distributed_scenario(),
    build_security_scenario(),
    build_voice_scenario(),
    build_avatar_scenario(),
    build_memory_scenario(),
    build_e2e_scenario(),
    build_reliability_scenario_group(),
]


def build_stt_cases(scenario_id: uuid.UUID) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for key, fixture in STT_FIXTURES.items():
        cases.append(
            EvaluationCase(
                case_id=uuid.uuid5(scenario_id, key),
                scenario_id=scenario_id,
                input={"audio_ref": fixture["audio_ref"], "reference": fixture["reference"]},
                expected_behavior=f"STT produces transcript for {key}",
                expected_result={
                    "reference": fixture["reference"],
                    "hypothesis": fixture["hypothesis"],
                },
            )
        )
    return cases


def build_language_cases(scenario_id: uuid.UUID) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for i, fixture in enumerate(LANGUAGE_DETECTION_FIXTURES):
        cases.append(
            EvaluationCase(
                case_id=uuid.uuid5(scenario_id, f"lang_{i}"),
                scenario_id=scenario_id,
                input={"text": fixture["text"]},
                expected_behavior=f"Detect language for: {fixture['text'][:30]}",
                expected_result={
                    "language": fixture["expected_language"],
                    "label": str(fixture["expected_label"].value),
                },
            )
        )
    return cases


def build_routing_cases(scenario_id: uuid.UUID) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for i, fixture in enumerate(ROUTING_FIXTURES):
        cases.append(
            EvaluationCase(
                case_id=uuid.uuid5(scenario_id, f"route_{i}"),
                scenario_id=scenario_id,
                input={"task_description": fixture["task_description"]},
                expected_behavior=f"Route to correct agent/tool for: {fixture['task_description'][:40]}",
                expected_result={
                    "agent": fixture["expected_agent"],
                    "tool": fixture["expected_tool"],
                },
                expected_routing=RoutingMetadata(
                    expected_agent=str(fixture["expected_agent"]),
                    expected_tool=fixture["expected_tool"] if isinstance(fixture["expected_tool"], str) else None,
                    decision=RoutingDecision.CORRECT,
                ),
            )
        )
    return cases


def build_planning_cases(scenario_id: uuid.UUID) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for i, fixture in enumerate(PLANNING_FIXTURES):
        cases.append(
            EvaluationCase(
                case_id=uuid.uuid5(scenario_id, f"plan_{i}"),
                scenario_id=scenario_id,
                input={"task_description": fixture["task_description"]},
                expected_behavior=f"Generate valid plan for: {fixture['task_description'][:40]}",
                expected_result={
                    "min_steps": fixture["expected_min_steps"],
                    "step_keywords": fixture["expected_step_descriptions_contain"],
                },
            )
        )
    return cases


def build_research_cases(scenario_id: uuid.UUID) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for query, sources in RESEARCH_FIXTURES.items():
        cases.append(
            EvaluationCase(
                case_id=uuid.uuid5(scenario_id, f"research_{query[:10]}"),
                scenario_id=scenario_id,
                input={"query": query},
                expected_behavior=f"Retrieve sources for: {query}",
                expected_result={
                    "expected_source_count": len(sources),
                    "sources": sources,
                },
            )
        )
    return cases


def build_security_cases(scenario_id: uuid.UUID) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for i, fixture in enumerate(SECURITY_FIXTURES):
        cases.append(
            EvaluationCase(
                case_id=uuid.uuid5(scenario_id, f"sec_{i}"),
                scenario_id=scenario_id,
                input={"action": fixture["action"]},
                expected_behavior=fixture["description"],
                expected_result={"decision": fixture["expected_decision"]},
            )
        )
    return cases


def build_vision_cases(scenario_id: uuid.UUID) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for key, fixture in VISION_FIXTURES.items():
        cases.append(
            EvaluationCase(
                case_id=uuid.uuid5(scenario_id, key),
                scenario_id=scenario_id,
                input={"image_ref": fixture["image_ref"]},
                expected_behavior=f"Produce structured observation for {key}",
                expected_result={
                    "text": fixture["expected_text"],
                    "elements": fixture["expected_elements"],
                    "ocr_text": fixture["ocr_text"],
                },
            )
        )
    return cases


def build_distributed_cases(scenario_id: uuid.UUID) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for i, fixture in enumerate(DISTRIBUTED_FIXTURES):
        cases.append(
            EvaluationCase(
                case_id=uuid.uuid5(scenario_id, f"dist_{i}"),
                scenario_id=scenario_id,
                input=fixture,
                expected_behavior=f"Distributed scenario: {fixture['scenario']}",
                expected_result=fixture,
            )
        )
    return cases


def build_memory_cases(scenario_id: uuid.UUID) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for i, fixture in enumerate(MEMORY_FIXTURES):
        cases.append(
            EvaluationCase(
                case_id=uuid.uuid5(scenario_id, f"mem_{i}"),
                scenario_id=scenario_id,
                input={"query": fixture["query"], "records": fixture["records"]},
                expected_behavior=f"Memory retrieval for: {fixture['query']}",
                expected_result={
                    "min_results": fixture["expected_min_results"],
                    "relevant": fixture["expected_relevant"],
                },
            )
        )
    return cases


def build_avatar_cases(scenario_id: uuid.UUID) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for i, fixture in enumerate(AVATAR_EVENT_FIXTURES):
        cases.append(
            EvaluationCase(
                case_id=uuid.uuid5(scenario_id, f"avatar_{i}"),
                scenario_id=scenario_id,
                input={"event": fixture["input_event"]},
                expected_behavior=fixture["description"],
                expected_result={"state": fixture["expected_state"]},
            )
        )
    return cases


def build_voice_cases(scenario_id: uuid.UUID) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for stage, timing_ms in VOICE_TIMING_FIXTURES.items():
        cases.append(
            EvaluationCase(
                case_id=uuid.uuid5(scenario_id, stage),
                scenario_id=scenario_id,
                input={"stage": stage},
                expected_behavior=f"Fixture timing measurement for {stage}",
                expected_result={"timing_ms": timing_ms},
            )
        )
    return cases


def build_bounded_loop_cases(scenario_id: uuid.UUID) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for i, fixture in enumerate(BOUNDED_LOOP_FIXTURES):
        cases.append(
            EvaluationCase(
                case_id=uuid.uuid5(scenario_id, f"loop_{i}"),
                scenario_id=scenario_id,
                input=fixture,
                expected_behavior=f"Bounded loop: {fixture['scenario']}",
                expected_result=fixture,
            )
        )
    return cases


def build_all_cases() -> list[EvaluationCase]:
    all_cases: list[EvaluationCase] = []
    builder_map = {
        build_stt_scenario: build_stt_cases,
        build_language_detection_scenario: build_language_cases,
        build_routing_scenario: build_routing_cases,
        build_planning_scenario: build_planning_cases,
        build_problem_solving_scenario: build_bounded_loop_cases,
        build_research_scenario: build_research_cases,
        build_computer_scenario: build_security_cases,
        build_browser_scenario: build_security_cases,
        build_vision_scenario: build_vision_cases,
        build_distributed_scenario: build_distributed_cases,
        build_security_scenario: build_security_cases,
        build_voice_scenario: build_voice_cases,
        build_avatar_scenario: build_avatar_cases,
        build_memory_scenario: build_memory_cases,
        build_e2e_scenario: build_routing_cases,
        build_reliability_scenario_group: build_bounded_loop_cases,
    }
    for scenario_builder, case_builder in builder_map.items():
        scenario = scenario_builder()
        all_cases.extend(case_builder(scenario.scenario_id))
    return all_cases


def build_all_scenarios() -> list[EvaluationScenario]:
    return list(ALL_SCENARIOS)


def build_reliability_scenarios() -> list[ReliabilityScenario]:
    return list(RELIABILITY_SCENARIOS)
