"""Tests for evaluation fixture datasets."""

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


class TestSttFixtures:
    def test_count(self):
        assert len(STT_FIXTURES) >= 5

    def test_all_have_required_keys(self):
        for key, fixture in STT_FIXTURES.items():
            assert "audio_ref" in fixture
            assert "reference" in fixture
            assert "hypothesis" in fixture

    def test_reference_not_empty(self):
        for key, fixture in STT_FIXTURES.items():
            if key != "empty_audio":
                assert len(fixture["reference"]) > 0


class TestLanguageDetectionFixtures:
    def test_count(self):
        assert len(LANGUAGE_DETECTION_FIXTURES) >= 7

    def test_all_have_required_keys(self):
        for fixture in LANGUAGE_DETECTION_FIXTURES:
            assert "text" in fixture
            assert "expected_language" in fixture
            assert "expected_label" in fixture

    def test_languages(self):
        languages = {f["expected_language"] for f in LANGUAGE_DETECTION_FIXTURES}
        assert "english" in languages
        assert "hindi" in languages


class TestRoutingFixtures:
    def test_count(self):
        assert len(ROUTING_FIXTURES) >= 7

    def test_all_have_required_keys(self):
        for fixture in ROUTING_FIXTURES:
            assert "task_description" in fixture
            assert "expected_agent" in fixture


class TestPlanningFixtures:
    def test_count(self):
        assert len(PLANNING_FIXTURES) >= 3

    def test_all_have_required_keys(self):
        for fixture in PLANNING_FIXTURES:
            assert "task_description" in fixture
            assert "expected_min_steps" in fixture


class TestResearchFixtures:
    def test_count(self):
        assert len(RESEARCH_FIXTURES) >= 2

    def test_all_have_sources(self):
        for query, sources in RESEARCH_FIXTURES.items():
            assert isinstance(sources, list)
            for src in sources:
                assert "title" in src
                assert "url" in src
                assert "snippet" in src


class TestSecurityFixtures:
    def test_count(self):
        assert len(SECURITY_FIXTURES) >= 5

    def test_all_have_required_keys(self):
        for fixture in SECURITY_FIXTURES:
            assert "action" in fixture
            assert "expected_decision" in fixture

    def test_decisions(self):
        decisions = {f["expected_decision"] for f in SECURITY_FIXTURES}
        assert "allow" in decisions
        assert "deny" in decisions
        assert "confirm" in decisions


class TestVisionFixtures:
    def test_count(self):
        assert len(VISION_FIXTURES) >= 2

    def test_all_have_required_keys(self):
        for key, fixture in VISION_FIXTURES.items():
            assert "image_ref" in fixture
            assert "expected_text" in fixture
            assert "ocr_text" in fixture


class TestMemoryFixtures:
    def test_count(self):
        assert len(MEMORY_FIXTURES) >= 3

    def test_all_have_required_keys(self):
        for fixture in MEMORY_FIXTURES:
            assert "records" in fixture
            assert "query" in fixture
            assert "expected_min_results" in fixture


class TestVoiceTimingFixtures:
    def test_count(self):
        assert len(VOICE_TIMING_FIXTURES) >= 4

    def test_all_positive(self):
        for stage, timing in VOICE_TIMING_FIXTURES.items():
            assert timing > 0, f"{stage} timing must be positive"


class TestAvatarEventFixtures:
    def test_count(self):
        assert len(AVATAR_EVENT_FIXTURES) >= 4

    def test_all_have_required_keys(self):
        for fixture in AVATAR_EVENT_FIXTURES:
            assert "input_event" in fixture
            assert "expected_state" in fixture


class TestDistributedFixtures:
    def test_count(self):
        assert len(DISTRIBUTED_FIXTURES) >= 4

    def test_all_have_required_keys(self):
        for fixture in DISTRIBUTED_FIXTURES:
            assert "scenario" in fixture


class TestBoundedLoopFixtures:
    def test_count(self):
        assert len(BOUNDED_LOOP_FIXTURES) >= 4

    def test_all_have_required_keys(self):
        for fixture in BOUNDED_LOOP_FIXTURES:
            assert "scenario" in fixture
            assert "max_iterations" in fixture


class TestReliabilityScenariosData:
    def test_count(self):
        assert len(RELIABILITY_SCENARIOS) == 15

    def test_all_have_names(self):
        for s in RELIABILITY_SCENARIOS:
            assert s.name
            assert s.name.strip()

    def test_unique_names(self):
        names = [s.name for s in RELIABILITY_SCENARIOS]
        assert len(names) == len(set(names))
