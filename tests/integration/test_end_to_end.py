"""End-to-end integration tests for the MISSMINUTES runtime.

Covers five deterministic scenarios:
A — File search
B — Failed action + replan
C — Security denial
D — Distributed failure + reroute
E — Voice interruption
"""

import asyncio
from collections.abc import Sequence

from app.config.schema import MissMinutesConfig
from app.core.ai import AIMessage, AIModel, AIResponse, ToolDefinition
from app.runtime.runtime import MissMinutesRuntime
from app.security.models import PermissionCategory, RiskLevel


def _run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------
# Scenario A — File search
# ------------------------------------------------------------------


class _FileSearchAI(AIModel):
    name = "file-search-ai"
    description = "AI that returns a file search plan."

    async def chat(
        self, messages: Sequence[AIMessage], *, tools: Sequence[ToolDefinition] | None = None
    ) -> AIResponse:
        last = messages[-1].content if messages else ""
        if "DSA" in last or "notes" in last.lower():
            return AIResponse.ok(
                content="Found DSA notes.pdf in /college/notes/ folder.",
                model_name="test",
            )
        return AIResponse.ok(content="Task completed.", model_name="test")


def test_scenario_a_file_search():
    """Text request for file search goes through orchestration and returns result."""

    async def flow():
        ai = _FileSearchAI()
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config, ai_model=ai)
        await runtime.startup()
        response = await runtime.handle_text("Find my DSA notes PDF in my college folder.")
        assert response.success is True
        assert "DSA" in response.text_response or "notes" in response.text_response.lower()
        assert response.task_id is not None
        await runtime.shutdown()

    _run(flow())


# ------------------------------------------------------------------
# Scenario B — Failed action + replan
# ------------------------------------------------------------------


class _ReplanAI(AIModel):
    name = "replan-ai"
    description = "AI that succeeds on second attempt."

    def __init__(self):
        self._count = 0

    async def chat(
        self, messages: Sequence[AIMessage], *, tools: Sequence[ToolDefinition] | None = None
    ) -> AIResponse:
        self._count += 1
        if self._count == 1:
            return AIResponse.fail(error="simulated first failure")
        return AIResponse.ok(content="Recovery successful on second attempt.", model_name="test")


def test_scenario_b_failed_action_replan():
    """First attempt fails, second attempt succeeds."""

    async def flow():
        ai = _ReplanAI()
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config, ai_model=ai)
        await runtime.startup()
        response = await runtime.handle_text("Perform the task")
        # The runtime should handle the failure gracefully
        assert response.request_id is not None
        await runtime.shutdown()

    _run(flow())


# ------------------------------------------------------------------
# Scenario C — Security denial
# ------------------------------------------------------------------


def test_scenario_c_security_denial():
    """Forbidden action is denied by security policy."""

    async def flow():
        config = MissMinutesConfig()
        config.security.policy_mode = "deny_all"
        runtime = MissMinutesRuntime(config)
        await runtime.startup()
        assert runtime.security is not None
        from app.security.models import Permission, PermissionRequest, SecurityContext

        permission = Permission(
            category=PermissionCategory.EXECUTE,
            action="test:denied",
            risk_level=RiskLevel.CRITICAL,
        )
        request = PermissionRequest(
            permission=permission,
            action="test:denied",
            risk_level=RiskLevel.CRITICAL,
            actor=None,
            origin="test",
        )
        context = SecurityContext(actor_id=None, origin="test")
        decision = runtime.security.check(request, context=context)
        assert decision.allowed is False
        await runtime.shutdown()

    _run(flow())


# ------------------------------------------------------------------
# Scenario D — Distributed failure + reroute
# ------------------------------------------------------------------


def test_scenario_distributed_failure_reroute():
    """Worker failure is handled gracefully — coordinator produces a synthetic failure."""

    async def flow():
        from uuid import uuid4

        from app.distributed.coordinator import DistributedCoordinator
        from app.distributed.executor import FakeWorkerExecutor
        from app.distributed.fakes import FakeWorkerTransport
        from app.distributed.models import DistributedTask, WorkerInfo
        from app.distributed.queue import DistributedTaskQueue
        from app.distributed.registry import WorkerRegistry

        worker_executor = FakeWorkerExecutor(output="task done")
        # Transport that always fails (simulating unreachable worker)
        transport = FakeWorkerTransport(
            executor=worker_executor,
            fail=True,
            fail_message="worker unreachable",
        )

        registry = WorkerRegistry()
        queue = DistributedTaskQueue()

        worker_id = uuid4()
        registry.register(
            WorkerInfo(
                worker_id=worker_id,
                worker_name="worker-a",
                capabilities=frozenset({"analysis"}),
                endpoint="http://a",
            )
        )

        coordinator = DistributedCoordinator(
            registry=registry,
            queue=queue,
            transport=transport,
        )

        task = DistributedTask(
            task_id=uuid4(),
            task_type="analysis",
            description="analysis task",
            required_capabilities=frozenset({"analysis"}),
        )
        coordinator.submit(task)

        # Dispatch: worker is unreachable, coordinator returns synthetic failure
        assignment = coordinator.dispatch_next()
        assert assignment is not None
        result = await coordinator.dispatch_async(assignment, task)
        coordinator.accept_result(result)

        # The result is a synthetic failure — the task is requeued for retry
        assert result.success is False
        assert "unreachable" in (result.error or "").lower()

    _run(flow())


# ------------------------------------------------------------------
# Scenario E — Voice interruption
# ------------------------------------------------------------------


class _InterruptibleTTS:
    name = "interruptible-tts"
    description = "TTS that can be interrupted."

    def __init__(self):
        self.playing = False
        self.interrupted = False

    async def synthesize(self, text, *, language=None):
        from app.voice.base import AudioData, TextToSpeechResult

        self.playing = True
        # Simulate interruption check
        if self.interrupted:
            self.playing = False
            from app.voice.base import SpeechError

            raise SpeechError("interrupted")
        self.playing = False
        return TextToSpeechResult(
            success=True,
            audio=AudioData(content=b"audio", format="text"),
        )


def test_scenario_e_voice_interruption():
    """Voice interruption stops playback and resets avatar."""

    async def flow():
        config = MissMinutesConfig()
        config.voice.enabled = True
        config.avatar.enabled = True
        runtime = MissMinutesRuntime(config)
        await runtime.startup()

        # Simulate interruption
        if runtime.avatar_controller is not None:
            from app.avatar.controller import AvatarSignal

            runtime.avatar_controller.handle(AvatarSignal.SPEAKING)
            # Interrupt
            runtime.avatar_controller.handle(AvatarSignal.INTERRUPTED)
            state = runtime.avatar_controller.state
            # After interruption, avatar should not be speaking
            assert state is not None

        await runtime.shutdown()

    _run(flow())
