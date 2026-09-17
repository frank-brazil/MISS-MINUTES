import asyncio
from pathlib import Path

from app.agents.base import AgentResult
from app.agents.vision import VisionAgent
from app.core.task import Task
from app.tools.screenshot import ScreenshotProvider, ScreenshotResult
from app.vision.fakes import FailingVisionProvider, FakeVisionProvider
from app.vision.models import (
    BoundingBox,
    DetectedElement,
    DetectedElementType,
    ImageInput,
)
from app.vision.screen_understanding import ScreenUnderstandingService


def _run(coro):
    return asyncio.run(coro)


class StaticScreenshotProvider(ScreenshotProvider):
    def __init__(self, filename: str, *, content: bytes = b"fake") -> None:
        self.filename = filename
        self.content = content

    async def capture(self, output_path: Path) -> ScreenshotResult:
        output_path.write_bytes(self.content)
        return ScreenshotResult(path=output_path, width=10, height=10, format="png")


def _task_with_image(description: str = "describe screenshot") -> Task:
    return Task(
        description=description,
        image=ImageInput(data=b"\x89PNG-fake", mime_type="image/png"),
    )


def test_vision_agent_without_injection_uses_stub() -> None:
    result = _run(VisionAgent().execute(Task(description="describe screen")))
    assert result.success is True
    assert "no vision provider" in (result.output or "").lower()


def test_vision_agent_injected_service_success(tmp_path: Path) -> None:
    vision = FakeVisionProvider()
    vision.default_text = "Login form"
    image = ImageInput(data=b"\x89PNG-fake", mime_type="image/png")
    from app.vision.models import image_reference

    vision.register_detected_elements(
        image_reference(image),
        [
            DetectedElement(
                element_type=DetectedElementType.BUTTON,
                label="Sign in",
                bounding_box=BoundingBox(x=1, y=2, width=3, height=4),
            )
        ],
    )
    service = ScreenUnderstandingService(
        StaticScreenshotProvider("s.png"), vision, workspace=tmp_path
    )
    agent = VisionAgent(screen_understanding=service)

    result = _run(agent.execute(_task_with_image()))

    assert result.success is True
    assert "Detected button: Sign in" in (result.output or "")
    assert "Observed text: 'Login form'" in (result.output or "")


def test_vision_agent_service_failure_propagates(tmp_path: Path) -> None:
    service = ScreenUnderstandingService(
        StaticScreenshotProvider("s.png"),
        FailingVisionProvider(),
        workspace=tmp_path,
    )
    agent = VisionAgent(screen_understanding=service)

    result = _run(agent.execute(_task_with_image()))

    assert result.success is False
    assert "Vision analysis failed" in (result.error or "")


def test_vision_agent_service_without_image_returns_deterministic() -> None:
    service = ScreenUnderstandingService(
        StaticScreenshotProvider("s.png"), FakeVisionProvider(), workspace=None
    )
    agent = VisionAgent(screen_understanding=service)

    result = _run(agent.execute(Task(description="describe screen")))

    assert result.success is True
    assert "no visual input" in (result.output or "")


def test_vision_agent_injected_provider_success() -> None:
    vision = FakeVisionProvider()
    vision.default_text = "Some text on screen"
    agent = VisionAgent(provider=vision)

    result = _run(agent.execute(_task_with_image("what text is shown?")))

    assert result.success is True
    assert "Some text on screen" in (result.output or "")
    assert len(vision.calls) == 1
    assert vision.calls[0].question == "what text is shown?"


def test_vision_agent_provider_without_image_returns_deterministic() -> None:
    agent = VisionAgent(provider=FakeVisionProvider())
    result = _run(agent.execute(Task(description="no image here")))
    assert result.success is True
    assert "no visual input" in (result.output or "")


def test_vision_agent_provider_exception_is_controlled() -> None:
    vision = FakeVisionProvider()
    vision.raise_error = RuntimeError("vision crashed")
    agent = VisionAgent(provider=vision)

    result = _run(agent.execute(_task_with_image()))

    assert result.success is False
    assert "Vision provider raised: RuntimeError" in (result.error or "")


def test_vision_agent_preserves_legacy_vision_fn() -> None:
    async def fake_vision(task: Task) -> AgentResult:
        return AgentResult.ok(output=f"legacy vision for '{task.description}'")

    agent = VisionAgent(vision_fn=fake_vision)
    assert agent.vision_fn is fake_vision
    result = _run(agent.execute(_task_with_image()))
    assert result.output == "legacy vision for 'describe screenshot'"


def test_vision_agent_exposes_injected_dependencies() -> None:
    vision = FakeVisionProvider()
    service = ScreenUnderstandingService(StaticScreenshotProvider("s.png"), vision, workspace=None)
    agent = VisionAgent(provider=vision, screen_understanding=service)
    assert agent.provider is vision
    assert agent.screen_understanding is service
