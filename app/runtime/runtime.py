"""Central application runtime for MISSMINUTES.

``MissMinutesRuntime`` owns the major application services, coordinates
lifecycle, and provides unified request entry points. It supports optional
capabilities cleanly — every subsystem can be absent without breaking the core.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from app.agents.coding import CodingAgent
from app.agents.critic import CriticAgent
from app.agents.prediction import PredictionAgent
from app.agents.research import ResearchAgent
from app.agents.system import SystemAgent
from app.agents.verification import VerificationAgent
from app.agents.vision import VisionAgent
from app.avatar.controller import AvatarController
from app.avatar.voice_adapter import VoiceAvatarAdapter
from app.config.schema import MissMinutesConfig
from app.core.ai import AIModel
from app.core.critic import FakeCritic
from app.core.orchestrator import Orchestrator
from app.core.planner import Planner
from app.core.prediction import FakePredictor
from app.core.routing import AgentRouter
from app.core.verification import FakeVerifier
from app.memory.base import Memory
from app.research.base import ResearchProvider
from app.runtime.audit import RequestAuditTrail
from app.runtime.capabilities import CapabilityRegistry
from app.runtime.errors import (
    StartupError,
)
from app.runtime.request import UnifiedRequest, UnifiedResponse
from app.security.confirmation import ConfirmationManager
from app.security.manager import SecurityManager
from app.security.policy import (
    ConservativePolicy,
    DefaultPolicy,
    DenyAllPolicy,
    SecurityPolicy,
)
from app.solver.actions import ActionExecutor
from app.solver.observation import ObservationProvider
from app.tools.calculator import CalculatorTool
from app.tools.file_config import FileToolConfig
from app.tools.file_create import FileCreateTool
from app.tools.file_edit import FileEditTool
from app.tools.file_read import FileReadTool
from app.tools.file_search import FileSearchTool
from app.tools.system_info import SystemInfoTool
from app.tools.terminal import ApprovedTerminalTool
from app.voice.base import SpeechToText, TextToSpeech
from app.voice.fakes import FakeSpeechToText, FakeTextToSpeech
from app.voice.language import LanguageDetector
from app.voice.service import (
    VoiceConversationRequest,
    VoiceConversationService,
)

logger = logging.getLogger(__name__)

# Allowed file system roots for the default tool configuration
_DEFAULT_ALLOWED_ROOTS: tuple[Path, ...] = (
    Path.home(),
)


def _build_security_policy(config: MissMinutesConfig) -> SecurityPolicy:
    """Build a SecurityPolicy from configuration."""
    mode = config.security.policy_mode.lower()
    if mode == "conservative":
        return ConservativePolicy()
    if mode == "deny_all":
        return DenyAllPolicy()
    return DefaultPolicy()


class MissMinutesRuntime:
    """Central application runtime owning all major subsystems.

    Usage::

        config = load_config()
        runtime = MissMinutesRuntime(config)
        await runtime.startup()
        try:
            response = await runtime.handle_text("Find my DSA notes.")
        finally:
            await runtime.shutdown()
    """

    def __init__(
        self,
        config: MissMinutesConfig,
        *,
        ai_model: AIModel | None = None,
        research_provider: ResearchProvider | None = None,
        stt: SpeechToText | None = None,
        tts: TextToSpeech | None = None,
        language_detector: LanguageDetector | None = None,
        action_executor: ActionExecutor | None = None,
        observation_provider: ObservationProvider | None = None,
    ) -> None:
        self._config = config
        self._ai_model = ai_model
        self._research_provider = research_provider
        self._stt_override = stt
        self._tts_override = tts
        self._language_detector_override = language_detector
        self._action_executor_override = action_executor
        self._observation_provider_override = observation_provider

        # Core services — populated during startup
        self._security: SecurityManager | None = None
        self._memory: Memory | None = None
        self._orchestrator: Orchestrator | None = None
        self._planner: Planner | None = None
        self._voice_service: VoiceConversationService | None = None
        self._avatar_controller: AvatarController | None = None
        self._voice_avatar_adapter: VoiceAvatarAdapter | None = None

        # Subsystem references for lifecycle management
        self._browser_tools: Any = None  # BrowserToolBundle if created
        self._distributed_coordinator: Any = None

        self._capabilities = CapabilityRegistry()
        self._audit = RequestAuditTrail(
            max_entries=config.security.audit_max_events
        )
        self._ready = False
        self._request_count = 0
        self._shutdown_called = False
        self._logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Read-only accessors
    # ------------------------------------------------------------------

    @property
    def config(self) -> MissMinutesConfig:
        return self._config

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def orchestrator(self) -> Orchestrator | None:
        return self._orchestrator

    @property
    def security(self) -> SecurityManager | None:
        return self._security

    @property
    def voice_service(self) -> VoiceConversationService | None:
        return self._voice_service

    @property
    def avatar_controller(self) -> AvatarController | None:
        return self._avatar_controller

    @property
    def memory(self) -> Memory | None:
        return self._memory

    @property
    def capabilities(self) -> CapabilityRegistry:
        return self._capabilities

    @property
    def audit(self) -> RequestAuditTrail:
        return self._audit

    @property
    def request_count(self) -> int:
        return self._request_count

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Initialize all subsystems. Idempotent — repeated calls are no-ops."""
        if self._ready:
            self._logger.info("Runtime already ready, skipping startup")
            return

        self._logger.info("MISSMINUTES runtime starting up")
        try:
            await self._initialize_security()
            await self._initialize_memory()
            await self._initialize_orchestrator()
            await self._initialize_agents()
            await self._initialize_tools()
            await self._initialize_voice()
            await self._initialize_avatar()
            await self._initialize_capabilities()
            self._ready = True
            self._logger.info("MISSMINUTES runtime ready")
        except Exception as exc:
            self._logger.error("Startup failed: %s", exc)
            await self._cleanup_on_failure()
            raise StartupError(f"Failed to start runtime: {exc}") from exc

    async def shutdown(self) -> None:
        """Clean up all subsystems. Idempotent."""
        if self._shutdown_called:
            return
        self._shutdown_called = True
        self._logger.info("MISSMINUTES runtime shutting down")

        try:
            await self._stop_voice()
            await self._stop_avatar()
            await self._stop_browser()
            await self._stop_distributed()
            await self._flush_memory()
        except Exception as exc:
            self._logger.warning("Error during shutdown: %s", exc)
        finally:
            self._ready = False
            self._logger.info("MISSMINUTES runtime shut down")

    # ------------------------------------------------------------------
    # Unified request handlers
    # ------------------------------------------------------------------

    async def handle_text(
        self, text: str, *, timeout_seconds: float | None = None
    ) -> UnifiedResponse:
        """Process a text request through the full pipeline."""
        if not text or not text.strip():
            request = UnifiedRequest(source="text", text="empty")
            return UnifiedResponse.fail(
                request.request_id, source="text", error="text must not be blank"
            )
        request = UnifiedRequest(source="text", text=text)
        return await self._handle_unified(request, timeout_seconds=timeout_seconds)

    async def handle_voice(
        self, audio: bytes, *, timeout_seconds: float | None = None
    ) -> UnifiedResponse:
        """Process a voice request through STT → brain → TTS."""
        request = UnifiedRequest(source="voice", audio=audio)
        return await self._handle_unified(request, timeout_seconds=timeout_seconds)

    async def handle_task(
        self, task: Any, *, timeout_seconds: float | None = None
    ) -> UnifiedResponse:
        """Process a pre-built Task through orchestration."""

        request_id = str(id(task)) if not hasattr(task, "task_id") else str(task.task_id)
        self._audit.record(request_id, "accepted", detail="pre-built task")
        self._request_count += 1

        orchestrator = self._orchestrator
        if orchestrator is None:
            return UnifiedResponse.fail(request_id, error="Orchestrator not available")

        try:
            result = await asyncio.wait_for(
                orchestrator.execute(task),
                timeout=timeout_seconds or self._config.ai.timeout_seconds,
            )
            self._audit.record(
                request_id, "response_generated",
                detail=f"success={result.success}", success=result.success,
            )
            return UnifiedResponse.ok(
                request_id,
                text_response=result.output,
                task_id=result.task_id,
            )
        except asyncio.TimeoutError:
            self._audit.record(request_id, "timeout", success=False)
            return UnifiedResponse.fail(request_id, error="Request timed out")
        except Exception as exc:
            self._audit.record(
                request_id, "error", detail=str(exc)[:200], success=False,
            )
            return UnifiedResponse.fail(request_id, error=str(exc)[:500])

    # ------------------------------------------------------------------
    # Internal initialization
    # ------------------------------------------------------------------

    async def _initialize_security(self) -> None:
        policy = _build_security_policy(self._config)
        self._security = SecurityManager(
            policy=policy,
            confirmation=ConfirmationManager() if self._config.security.confirmation_required else None,
        )
        self._capabilities.register("security", True, self._config.security.policy_mode)

    async def _initialize_memory(self) -> None:
        try:
            from app.memory.sqlite_memory import SQLiteMemory

            self._memory = SQLiteMemory.from_env()
            self._capabilities.register("memory", True, "sqlite")
        except Exception:
            self._logger.warning("Memory initialization failed, continuing without memory")
            self._memory = None
            self._capabilities.register("memory", False)

    async def _initialize_orchestrator(self) -> None:
        # ManualPlanner requires step descriptions and is task-specific.
        # The runtime does not set a planner by default — the orchestrator
        # will use the AI tool-calling path when an AI model is provided,
        # or the placeholder path otherwise. The ProblemSolvingEngine
        # supplies its own internal planner when configured.
        router = AgentRouter()
        self._orchestrator = Orchestrator(
            ai_model=self._ai_model,
            memory=self._memory,
            planner=None,
            agent_router=router,
            security=self._security,
        )
        self._capabilities.register("text", True)
        self._capabilities.register("planning", True)

    async def _initialize_agents(self) -> None:
        """Register agents based on available subsystems."""

        # Always register these agents
        self._orchestrator.register_agent(SystemAgent())
        self._orchestrator.register_agent(CodingAgent())
        self._orchestrator.register_agent(
            PredictionAgent(FakePredictor())
        )
        self._orchestrator.register_agent(CriticAgent(FakeCritic()))
        self._orchestrator.register_agent(VerificationAgent(FakeVerifier()))

        # Conditional agents
        self._orchestrator.register_agent(
            ResearchAgent(self._research_provider)
        )
        if self._config.vision.enabled:
            self._orchestrator.register_agent(VisionAgent())
            self._capabilities.register("vision", True, self._config.vision.provider)
        else:
            self._capabilities.register("vision", False)

        self._capabilities.register("research", self._research_provider is not None)
        self._capabilities.register("prediction", True)
        self._capabilities.register("critique", True)
        self._capabilities.register("verification", True)
        self._capabilities.register("agents", True)

    async def _initialize_tools(self) -> None:
        """Register tools with their CHUNK 30 security metadata preserved."""
        o = self._orchestrator
        o.register_tool(CalculatorTool())
        o.register_tool(SystemInfoTool())
        o.register_tool(ApprovedTerminalTool())

        # Filesystem tools with allowed roots from config
        allowed = [Path(p) for p in self._config.filesystem.allowed_roots]
        if not allowed:
            allowed = list(_DEFAULT_ALLOWED_ROOTS)
        file_config = FileToolConfig(allowed_roots=tuple(allowed))
        o.register_tool(FileReadTool(config=file_config))
        o.register_tool(FileCreateTool(config=file_config))
        o.register_tool(FileEditTool(config=file_config))
        o.register_tool(FileSearchTool(config=file_config))

        self._capabilities.register("filesystem", True)
        self._capabilities.register("terminal", True)

        # Browser tools
        if self._config.browser.enabled:
            try:
                from app.browser.playwright_provider import PlaywrightBrowserProvider
                from app.browser.tools import BrowserToolBundle

                provider = PlaywrightBrowserProvider()
                bundle = BrowserToolBundle(provider=provider)
                await bundle.start()
                self._browser_tools = bundle
                for tool in bundle.tools():
                    o.register_tool(tool)
                self._capabilities.register("browser", True)
            except Exception:
                self._logger.warning("Browser initialization failed")
                self._capabilities.register("browser", False)
        else:
            self._capabilities.register("browser", False)

    async def _initialize_voice(self) -> None:
        if not self._config.voice.enabled:
            self._capabilities.register("voice", False)
            return

        stt = self._stt_override or FakeSpeechToText()
        tts = self._tts_override or FakeTextToSpeech()
        detector = self._language_detector_override
        if detector is None:
            try:
                from app.voice.local_detector import LocalLanguageDetector
                detector = LocalLanguageDetector()
            except Exception:
                from app.voice.fakes import FakeLanguageDetector
                detector = FakeLanguageDetector()

        self._voice_service = VoiceConversationService(
            stt=stt,
            tts=tts,
            detector=detector,
            ai_model=self._ai_model,
        )
        self._capabilities.register("voice", True)

    async def _initialize_avatar(self) -> None:
        if not self._config.avatar.enabled:
            self._capabilities.register("avatar", False)
            return

        try:
            from app.avatar.config import AvatarConfig as AvatarCfg

            avatar_cfg = AvatarCfg()
            self._avatar_controller = AvatarController(config=avatar_cfg)

            if self._voice_service is not None:
                self._voice_avatar_adapter = VoiceAvatarAdapter(
                    controller=self._avatar_controller
                )
            self._capabilities.register("avatar", True, self._config.avatar.theme)
        except Exception:
            self._logger.warning("Avatar initialization failed")
            self._capabilities.register("avatar", False)

    async def _initialize_capabilities(self) -> None:
        """Register remaining capability statuses."""
        self._capabilities.register(
            "distributed", self._config.distributed.enabled
        )
        # ProblemSolvingEngine is available as an opt-in execution mode.
        # By default the runtime uses the AI tool-calling path via the
        # orchestrator. The engine is NOT wired to the orchestrator unless
        # explicitly requested — it requires its own planner and is only
        # useful for bounded autonomous loops.

    # ------------------------------------------------------------------
    # Unified request handler
    # ------------------------------------------------------------------

    async def _handle_unified(
        self,
        request: UnifiedRequest,
        *,
        timeout_seconds: float | None = None,
    ) -> UnifiedResponse:
        self._request_count += 1
        self._audit.record(request.request_id, "accepted", detail=f"source={request.source}")

        if not self._ready:
            self._audit.record(request.request_id, "not_ready", success=False)
            return UnifiedResponse.fail(
                request.request_id,
                source=request.source,
                error="Runtime is not ready",
            )

        timeout = timeout_seconds or self._config.ai.timeout_seconds

        try:
            if request.source == "voice" and request.audio is not None:
                if self._voice_service is None:
                    self._audit.record(
                        request.request_id, "voice_disabled", success=False,
                    )
                    return UnifiedResponse.fail(
                        request.request_id,
                        source="voice",
                        error="Voice service is not enabled or available",
                    )
                return await self._handle_voice_request(request, timeout)
            elif request.source == "text" and request.text is not None:
                return await self._handle_text_request(request, timeout)
            else:
                return UnifiedResponse.fail(
                    request.request_id,
                    source=request.source,
                    error="Invalid request: missing text or audio",
                )
        except asyncio.TimeoutError:
            self._audit.record(
                request.request_id, "timeout", success=False,
            )
            return UnifiedResponse.fail(
                request.request_id,
                source=request.source,
                error="Request timed out",
            )
        except Exception as exc:
            self._audit.record(
                request.request_id, "error",
                detail=str(exc)[:200], success=False,
            )
            return UnifiedResponse.fail(
                request.request_id,
                source=request.source,
                error=str(exc)[:500],
            )

    async def _handle_text_request(
        self, request: UnifiedRequest, timeout: float,
    ) -> UnifiedResponse:
        assert request.text is not None
        self._audit.record(
            request.request_id, "planning_started",
            detail=f"text_len={len(request.text)}",
        )

        from app.core.task import Task

        task = Task(description=request.text)
        self._audit.record(
            request.request_id, "task_created",
            detail=f"task_id={task.task_id}",
        )

        result = await asyncio.wait_for(
            self._orchestrator.execute(task),
            timeout=timeout,
        )

        self._audit.record(
            request.request_id, "verification_completed",
            detail=f"success={result.success}", success=result.success,
        )
        self._audit.record(
            request.request_id, "response_generated",
            success=result.success,
        )

        if result.success:
            return UnifiedResponse.ok(
                request.request_id,
                source="text",
                text_response=result.output,
                task_id=result.task_id,
            )
        else:
            return UnifiedResponse.fail(
                request.request_id,
                source="text",
                error=result.error or "Task failed",
            )

    async def _handle_voice_request(
        self, request: UnifiedRequest, timeout: float,
    ) -> UnifiedResponse:
        assert request.audio is not None
        assert self._voice_service is not None

        self._audit.record(
            request.request_id, "voice_received",
            detail=f"audio_len={len(request.audio)}",
        )

        voice_request = VoiceConversationRequest(audio=request.audio)
        voice_result = await asyncio.wait_for(
            self._voice_service.handle(voice_request),
            timeout=timeout,
        )

        # Emit voice events to avatar if adapter is present
        if self._voice_avatar_adapter is not None:
            # Map voice result to avatar signal
            from app.avatar.controller import AvatarSignal

            if voice_result.success:
                self._voice_avatar_adapter.controller.handle(AvatarSignal.SUCCESS)
            else:
                self._voice_avatar_adapter.controller.handle(AvatarSignal.ERROR)

        self._audit.record(
            request.request_id, "voice_completed",
            detail=f"success={voice_result.success}",
            success=voice_result.success,
        )

        if voice_result.success:
            audio_bytes = voice_result.audio.content if voice_result.audio else None
            return UnifiedResponse.ok(
                request.request_id,
                source="voice",
                text_response=voice_result.ai_response,
                audio_response=audio_bytes,
            )
        else:
            return UnifiedResponse.fail(
                request.request_id,
                source="voice",
                error=voice_result.error or "Voice processing failed",
            )

    # ------------------------------------------------------------------
    # Cleanup helpers
    # ------------------------------------------------------------------

    async def _stop_voice(self) -> None:
        self._logger.debug("Stopping voice services")

    async def _stop_avatar(self) -> None:
        if self._avatar_controller is not None:
            try:
                self._avatar_controller.stop()
            except Exception:
                pass

    async def _stop_browser(self) -> None:
        if self._browser_tools is not None:
            try:
                await self._browser_tools.stop()
            except Exception:
                pass

    async def _stop_distributed(self) -> None:
        self._logger.debug("Stopping distributed services")

    async def _flush_memory(self) -> None:
        self._logger.debug("Flushing memory")

    async def _cleanup_on_failure(self) -> None:
        """Best-effort cleanup when startup fails partway."""
        await self._stop_voice()
        await self._stop_avatar()
        await self._stop_browser()
        await self._stop_distributed()

    # ------------------------------------------------------------------
    # Class helpers
    # ------------------------------------------------------------------

    @classmethod
    def create_headless(cls, config: MissMinutesConfig | None = None) -> MissMinutesRuntime:
        """Create a runtime suitable for CI/tests with all fakes.

        No hardware, no network, no external dependencies required.
        """
        from app.research.fakes import FakeResearchProvider
        from app.voice.fakes import FakeLanguageDetector

        cfg = config or MissMinutesConfig()

        class _FakeAI(AIModel):
            name = "fake-ai-runtime"
            description = "Fake AI model for headless runtime."

            async def chat(self, messages, *, tools=None):
                from app.core.ai import AIResponse
                return AIResponse.ok(content="Headless response.", model_name="fake")

        return cls(
            config=cfg,
            ai_model=_FakeAI(),
            research_provider=FakeResearchProvider(),
            stt=FakeSpeechToText(),
            tts=FakeTextToSpeech(),
            language_detector=FakeLanguageDetector(),
        )
