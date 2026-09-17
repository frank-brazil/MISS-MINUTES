"""Tests for evaluation composite fakes."""

import asyncio

from app.evaluation.fakes import EvaluationEnvironment, InMemoryMemory
from app.memory.base import MemoryRecord


def _run(coro):
    return asyncio.run(coro)


class TestInMemoryMemory:
    def test_store_and_retrieve(self):
        memory = InMemoryMemory()
        record = MemoryRecord(content="Test record")
        _run(memory.store(record))
        result = _run(memory.retrieve("Test"))
        assert result.count == 1
        assert result.success

    def test_retrieve_no_match(self):
        memory = InMemoryMemory()
        record = MemoryRecord(content="Test record")
        _run(memory.store(record))
        result = _run(memory.retrieve("nonexistent"))
        assert result.count == 0

    def test_delete(self):
        memory = InMemoryMemory()
        record = MemoryRecord(content="To delete")
        _run(memory.store(record))
        deleted = _run(memory.delete(record.memory_id))
        assert deleted
        result = _run(memory.retrieve("delete"))
        assert result.count == 0

    def test_limit(self):
        memory = InMemoryMemory()
        for i in range(5):
            _run(memory.store(MemoryRecord(content=f"Record {i}")))
        result = _run(memory.retrieve("Record", limit=2))
        assert result.count == 2


class TestEvaluationEnvironment:
    def test_create(self):
        env = EvaluationEnvironment()
        assert env.stt is not None
        assert env.tts is not None
        assert env.language_detector is not None
        assert env.ai_model is not None
        assert env.research_provider is not None
        assert env.vision_provider is not None
        assert env.ocr_provider is not None
        assert env.action_executor is not None
        assert env.observation_provider is not None
        assert env.verifier is not None
        assert env.critic is not None
        assert env.predictor is not None
        assert env.planner is not None
        assert env.worker_transport is not None
        assert env.master_transport is not None
        assert env.worker_executor is not None
        assert env.memory is not None

    def test_stt_deterministic(self):
        env = EvaluationEnvironment()
        from app.voice.base import SpeechInput

        request = SpeechInput(audio=b"audio_clear_en_001", sample_rate=16000)
        result = _run(env.stt.transcribe(request))
        assert result.text
        assert result.language == "en"

    def test_tts_deterministic(self):
        env = EvaluationEnvironment()
        from app.voice.base import TextToSpeechRequest

        request = TextToSpeechRequest(text="Hello", language="en")
        result = _run(env.tts.synthesize(request))
        assert result.audio is not None
        assert result.audio.content is not None

    def test_language_detector_deterministic(self):
        env = EvaluationEnvironment()
        result = _run(env.language_detector.detect("Find my project files"))
        assert result is not None
        assert result.label.value == "english"

    def test_research_deterministic(self):
        env = EvaluationEnvironment()
        import asyncio

        from app.research.base import SearchRequest

        request = SearchRequest(query="quantum computing", max_results=5)
        response = asyncio.run(env.research_provider.research(request))
        assert len(response.results) >= 1
        assert response.results[0].source.title

    def test_action_executor_deterministic(self):
        env = EvaluationEnvironment()
        from app.solver.actions import ActionRequest

        request = ActionRequest(description="Test action")
        result = _run(env.action_executor.execute(request))
        assert result.success

    def test_verifier_deterministic(self):
        env = EvaluationEnvironment()
        from app.core.verification import ObservedResult, VerificationExpectation

        expectation = VerificationExpectation(description="Test", conditions=["file exists"])
        observation = ObservedResult(
            description="Found",
            observations=["file exists"],
            evidence=[],
            action_succeeded=True,
        )
        result = _run(env.verifier.verify(expectation, observation))
        assert result.status.value in ("verified", "failed", "inconclusive")

    def test_configure_for_failure_ai(self):
        env = EvaluationEnvironment()
        env.configure_for_failure(ai_fail=True)
        from app.voice.base import SpeechInput

        request = SpeechInput(audio=b"test", sample_rate=16000)
        result = _run(env.stt.transcribe(request))
        assert result is not None

    def test_configure_for_failure_action(self):
        env = EvaluationEnvironment()
        env.configure_for_failure(action_fail=True)
        from app.solver.actions import ActionRequest

        request = ActionRequest(description="Fail test")
        result = _run(env.action_executor.execute(request))
        assert not result.success

    def test_memory_in_environment(self):
        env = EvaluationEnvironment()
        record = MemoryRecord(content="Environment memory test")
        _run(env.memory.store(record))
        result = _run(env.memory.retrieve("Environment"))
        assert result.count == 1
