"""Tests for evaluation scenario dataset building."""

from app.evaluation.models import EvaluationCategory
from app.evaluation.scenarios import (
    ALL_SCENARIOS,
    build_all_cases,
    build_all_scenarios,
    build_avatar_cases,
    build_avatar_scenario,
    build_bounded_loop_cases,
    build_browser_scenario,
    build_computer_scenario,
    build_distributed_cases,
    build_distributed_scenario,
    build_e2e_scenario,
    build_language_cases,
    build_language_detection_scenario,
    build_memory_cases,
    build_memory_scenario,
    build_planning_cases,
    build_planning_scenario,
    build_problem_solving_scenario,
    build_reliability_scenario_group,
    build_reliability_scenarios,
    build_research_cases,
    build_research_scenario,
    build_routing_cases,
    build_routing_scenario,
    build_security_cases,
    build_security_scenario,
    build_stt_cases,
    build_stt_scenario,
    build_vision_cases,
    build_vision_scenario,
    build_voice_cases,
    build_voice_scenario,
)


class TestAllScenarios:
    def test_count(self):
        assert len(ALL_SCENARIOS) == 16

    def test_unique_ids(self):
        ids = [s.scenario_id for s in ALL_SCENARIOS]
        assert len(ids) == len(set(ids))

    def test_unique_names(self):
        names = [s.name for s in ALL_SCENARIOS]
        assert len(names) == len(set(names))

    def test_all_have_categories(self):
        for scenario in ALL_SCENARIOS:
            assert isinstance(scenario.category, EvaluationCategory)

    def test_build_all_returns_same(self):
        scenarios = build_all_scenarios()
        assert len(scenarios) == len(ALL_SCENARIOS)


class TestScenarioBuilders:
    def test_stt_scenario(self):
        s = build_stt_scenario()
        assert s.category == EvaluationCategory.STT
        assert "STT" in s.name

    def test_language_scenario(self):
        s = build_language_detection_scenario()
        assert s.category == EvaluationCategory.LANGUAGE_DETECTION

    def test_routing_scenario(self):
        s = build_routing_scenario()
        assert s.category == EvaluationCategory.TOOL_AGENT_ROUTING

    def test_planning_scenario(self):
        s = build_planning_scenario()
        assert s.category == EvaluationCategory.PLANNING

    def test_problem_solving_scenario(self):
        s = build_problem_solving_scenario()
        assert s.category == EvaluationCategory.PROBLEM_SOLVING

    def test_research_scenario(self):
        s = build_research_scenario()
        assert s.category == EvaluationCategory.RESEARCH

    def test_computer_scenario(self):
        s = build_computer_scenario()
        assert s.category == EvaluationCategory.COMPUTER

    def test_browser_scenario(self):
        s = build_browser_scenario()
        assert s.category == EvaluationCategory.BROWSER

    def test_vision_scenario(self):
        s = build_vision_scenario()
        assert s.category == EvaluationCategory.VISION

    def test_distributed_scenario(self):
        s = build_distributed_scenario()
        assert s.category == EvaluationCategory.DISTRIBUTED

    def test_security_scenario(self):
        s = build_security_scenario()
        assert s.category == EvaluationCategory.SECURITY

    def test_voice_scenario(self):
        s = build_voice_scenario()
        assert s.category == EvaluationCategory.VOICE

    def test_avatar_scenario(self):
        s = build_avatar_scenario()
        assert s.category == EvaluationCategory.AVATAR

    def test_memory_scenario(self):
        s = build_memory_scenario()
        assert s.category == EvaluationCategory.MEMORY

    def test_e2e_scenario(self):
        s = build_e2e_scenario()
        assert s.category == EvaluationCategory.END_TO_END

    def test_reliability_scenario_group(self):
        s = build_reliability_scenario_group()
        assert s.category == EvaluationCategory.RELIABILITY


class TestCaseBuilders:
    def test_stt_cases(self):
        s = build_stt_scenario()
        cases = build_stt_cases(s.scenario_id)
        assert len(cases) >= 5
        for c in cases:
            assert c.scenario_id == s.scenario_id

    def test_language_cases(self):
        s = build_language_detection_scenario()
        cases = build_language_cases(s.scenario_id)
        assert len(cases) >= 7

    def test_routing_cases(self):
        s = build_routing_scenario()
        cases = build_routing_cases(s.scenario_id)
        assert len(cases) >= 7

    def test_planning_cases(self):
        s = build_planning_scenario()
        cases = build_planning_cases(s.scenario_id)
        assert len(cases) >= 3

    def test_research_cases(self):
        s = build_research_scenario()
        cases = build_research_cases(s.scenario_id)
        assert len(cases) >= 2

    def test_security_cases(self):
        s = build_security_scenario()
        cases = build_security_cases(s.scenario_id)
        assert len(cases) >= 5

    def test_vision_cases(self):
        s = build_vision_scenario()
        cases = build_vision_cases(s.scenario_id)
        assert len(cases) >= 2

    def test_distributed_cases(self):
        s = build_distributed_scenario()
        cases = build_distributed_cases(s.scenario_id)
        assert len(cases) >= 4

    def test_memory_cases(self):
        s = build_memory_scenario()
        cases = build_memory_cases(s.scenario_id)
        assert len(cases) >= 3

    def test_avatar_cases(self):
        s = build_avatar_scenario()
        cases = build_avatar_cases(s.scenario_id)
        assert len(cases) >= 4

    def test_voice_cases(self):
        s = build_voice_scenario()
        cases = build_voice_cases(s.scenario_id)
        assert len(cases) >= 5

    def test_bounded_loop_cases(self):
        s = build_problem_solving_scenario()
        cases = build_bounded_loop_cases(s.scenario_id)
        assert len(cases) >= 4

    def test_all_cases(self):
        all_cases = build_all_cases()
        assert len(all_cases) > 50


class TestReliabilityScenarios:
    def test_count(self):
        scenarios = build_reliability_scenarios()
        assert len(scenarios) == 15

    def test_all_have_failure_types(self):
        from app.evaluation.models import FailureCategory
        for s in build_reliability_scenarios():
            assert isinstance(s.failure_type, FailureCategory)
