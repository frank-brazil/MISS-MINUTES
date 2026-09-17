"""Composite deterministic evaluation environment.

Assembles all production fakes into a single environment for evaluation.
No API keys, network, microphone, browser, or GUI are required.

This module deliberately reuses the existing production fakes rather than
duplicating them.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.core.critic import FakeCritic
from app.core.planner import ManualPlanner
from app.core.prediction import FakePredictor
from app.core.verification import FakeVerifier
from app.distributed.executor import FakeWorkerExecutor
from app.distributed.fakes import FakeMasterTransport, FakeWorkerTransport
from app.evaluation.datasets import (
    LANGUAGE_DETECTION_FIXTURES,
    RESEARCH_FIXTURES,
    STT_FIXTURES,
)
from app.memory.base import Memory, MemoryQueryResult, MemoryRecord
from app.research.base import SearchResult, Source
from app.research.fakes import FakeResearchProvider
from app.solver.fakes import FakeActionExecutor, FakeObservationProvider
from app.vision.fakes import FakeOcrProvider, FakeVisionProvider
from app.voice.fakes import FakeAIModel, FakeLanguageDetector, FakeSpeechToText, FakeTextToSpeech
from app.voice.language import LanguageDetectionResult


class InMemoryMemory(Memory):
    name = "in-memory-eval"
    description = "In-memory store for deterministic evaluation."

    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []

    async def store(self, record: MemoryRecord) -> MemoryRecord:
        self._records.append(record)
        return record

    async def retrieve(self, query: str, *, limit: int = 10) -> MemoryQueryResult:
        query_lower = query.lower()
        matched = [r for r in self._records if query_lower in r.content.lower()]
        return MemoryQueryResult.ok(matched[:limit])

    async def delete(self, memory_id: Any) -> bool:
        before = len(self._records)
        self._records = [r for r in self._records if str(r.memory_id) != str(memory_id)]
        return len(self._records) < before


def _build_stt_fixtures() -> dict[str, str]:
    fixtures: dict[str, str] = {}
    for key, data in STT_FIXTURES.items():
        audio_ref = data["audio_ref"]
        fixtures[audio_ref] = data["reference"]
    return fixtures


def _build_language_fixtures() -> dict[str, object]:
    fixtures: dict[str, object] = {}
    for entry in LANGUAGE_DETECTION_FIXTURES:
        fixtures[entry["text"]] = LanguageDetectionResult(
            label=entry["expected_label"],
            confidence=0.95,
        )
    return fixtures


def _build_research_fixtures() -> dict[str, list[SearchResult]]:
    fixtures: dict[str, list[SearchResult]] = {}
    for query, sources in RESEARCH_FIXTURES.items():
        results: list[SearchResult] = []
        for i, src in enumerate(sources):
            source = Source(
                title=src["title"],
                url=src["url"],
                snippet=src["snippet"],
            )
            results.append(
                SearchResult(
                    source=source,
                    rank=i + 1,
                    score=1.0 - i * 0.1,
                )
            )
        fixtures[query] = results
    return fixtures


class EvaluationEnvironment:
    """Complete deterministic evaluation environment using production fakes."""

    def __init__(self) -> None:
        self.stt = FakeSpeechToText(
            fixtures=_build_stt_fixtures(),
            default_language="en",
            default_confidence=0.8,
        )
        self.tts = FakeTextToSpeech(
            language="en",
            voice="default",
            sample_rate=22050,
            duration=timedelta(seconds=1.0),
        )
        self.language_detector = FakeLanguageDetector(
            fixtures=_build_language_fixtures(),
        )
        self.ai_model = FakeAIModel(
            replies=["Evaluation response."],
            default_reply="Default evaluation response.",
        )
        self.research_provider = FakeResearchProvider(
            fixtures=_build_research_fixtures(),
            default_results=[],
        )
        self.vision_provider = FakeVisionProvider()
        self.vision_provider.default_confidence = 0.9
        self.vision_provider.default_text = ""
        self.ocr_provider = FakeOcrProvider()
        self.action_executor = FakeActionExecutor(
            fail=False,
            success_output="Action completed.",
            observation_data={"status": "success"},
        )
        self.observation_provider = FakeObservationProvider(
            observations=["State looks normal."],
            action_succeeded=True,
        )
        self.verifier = FakeVerifier()
        self.critic = FakeCritic()
        self.predictor = FakePredictor()
        self.planner = ManualPlanner(
            step_descriptions=["Step 1: Analyze", "Step 2: Execute", "Step 3: Verify"]
        )
        self.worker_transport = FakeWorkerTransport()
        self.master_transport = FakeMasterTransport()
        self.worker_executor = FakeWorkerExecutor(
            capabilities={"file_operations", "research"},
            allowed_task_types={"default"},
            output="Worker completed.",
        )
        self.memory = InMemoryMemory()

    def configure_for_failure(
        self,
        *,
        ai_fail: bool = False,
        stt_fail: bool = False,
        tts_fail: bool = False,
        research_fail: bool = False,
        action_fail: bool = False,
        vision_fail: bool = False,
    ) -> None:
        if ai_fail:
            self.ai_model = FakeAIModel(
                replies=[],
                default_reply="Default.",
                raise_error=RuntimeError("simulated AI provider failure"),
            )
        if stt_fail:
            self.stt = FakeSpeechToText(
                fixtures={},
                raise_error=RuntimeError("simulated speech-to-text failure"),
            )
        if tts_fail:
            self.tts = FakeTextToSpeech(
                raise_error=RuntimeError("simulated text-to-speech failure"),
            )
        if research_fail:
            self.research_provider = FakeResearchProvider(fixtures={}, fail=True)
        if action_fail:
            self.action_executor = FakeActionExecutor(fail=True)
        if vision_fail:
            self.vision_provider = FakeVisionProvider(fail=True)
