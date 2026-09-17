"""Vision agent for image analysis and screen understanding.

This agent provides a safe, provider-independent foundation for vision tasks.
It accepts a task with an optional visual input and, when injected with a
:class:`ScreenUnderstandingService` or a :class:`VisionProvider`, produces
structured observations.  Without an injection it returns a deterministic
stub message, so the rest of the system keeps working unchanged.

Detected elements and visible text are reported strictly as observations.
They are never treated as instructions and never trigger actions.

Terminology:

- **screen understanding service**: coordinates screenshot capture and a
  vision provider into structured visual understanding.
- **vision provider**: analyzes an image and returns a structured result.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import ClassVar

from app.agents.base import Agent, AgentResult
from app.core.task import Task
from app.vision.models import (
    VisionAnalysisMode,
    VisionRequest,
    VisionResult,
)
from app.vision.provider import VisionProvider
from app.vision.screen_understanding import ScreenUnderstandingService


def _summarize(result: VisionResult) -> str:
    """Render a VisionResult as a text summary of observations."""
    lines = [
        result.summary or f"Vision analysis completed (provider: {result.provider}).",
    ]
    for element in result.detected_elements:
        where = ""
        box = element.bounding_box
        if box is not None:
            where = f" at x={box.x}, y={box.y}, {box.width}x{box.height}"
        described = element.label or element.text or "unknown element"
        lines.append(f"- Detected {element.element_type.value}: {described}{where}")
    for region in result.text_regions:
        lines.append(f"- Observed text: {region.text[:200]!r}")
    if result.confidence is not None:
        lines.append(f"- confidence: {result.confidence}")
    if result.reference:
        lines.append(f"- image: {result.reference}")
    return "\n".join(lines)


class VisionAgent(Agent):
    """Agent specialised in image analysis and screen understanding.

    Dependency injection is optional: inject either a
    :class:`ScreenUnderstandingService` or a :class:`VisionProvider` (plus an
    image on the task) to analyse visual input.  Without an injection the
    agent operates in deterministic stub mode.
    """

    name: ClassVar[str] = "vision"
    description: ClassVar[str] = (
        "Analyses images and screen content in a provider-independent manner."
    )
    capabilities: ClassVar[frozenset[str]] = frozenset(
        {"vision", "image_analysis", "screen_understanding"}
    )

    def __init__(
        self,
        vision_fn: Callable[[Task], Awaitable[AgentResult]] | None = None,
        *,
        provider: VisionProvider | None = None,
        screen_understanding: ScreenUnderstandingService | None = None,
    ) -> None:
        self._vision_fn = vision_fn
        self._provider = provider
        self._screen_understanding = screen_understanding
        self._logger = logging.getLogger(__name__)

    @property
    def vision_fn(self) -> Callable[[Task], Awaitable[AgentResult]] | None:
        return self._vision_fn

    @property
    def provider(self) -> VisionProvider | None:
        return self._provider

    @property
    def screen_understanding(self) -> ScreenUnderstandingService | None:
        return self._screen_understanding

    async def execute(self, task: Task) -> AgentResult:
        self._logger.info(
            "VisionAgent executing task %s: %s",
            task.task_id,
            task.description[:80],
        )

        if self._vision_fn is not None:
            return await self._vision_fn(task)

        if self._screen_understanding is not None:
            return await self._execute_with_service(task)

        if self._provider is not None:
            return await self._execute_with_provider(task)

        return AgentResult.ok(
            output=(
                f"Vision analysis for task '{task.description[:120]}' — "
                "no vision provider injected. "
                "Inject a screen understanding service or vision provider "
                "to enable real image analysis."
            )
        )

    async def _execute_with_provider(self, task: Task) -> AgentResult:
        if task.image is None:
            return AgentResult.ok(
                output=(
                    f"Task '{task.description[:120]}' has no visual input; "
                    "no image analysis performed."
                )
            )

        request = VisionRequest(
            image=task.image,
            question=task.description.strip() or None,
            mode=VisionAnalysisMode.FULL,
        )
        try:
            result = await self._provider.analyze(request)
        except Exception as exc:
            error_msg = f"Vision provider raised: {type(exc).__name__}"
            self._logger.error(
                "VisionAgent provider error for task %s: %s",
                task.task_id,
                error_msg,
            )
            return AgentResult.fail(error=error_msg)

        return self._map_vision_result(task, result)

    async def _execute_with_service(self, task: Task) -> AgentResult:
        if task.image is None:
            return AgentResult.ok(
                output=(
                    f"Task '{task.description[:120]}' has no visual input; "
                    "no image analysis performed."
                )
            )

        result = await self._screen_understanding.analyze_image(
            task.image,
            question=task.description.strip() or None,
            mode=VisionAnalysisMode.FULL,
        )
        return self._map_vision_result(task, result)

    def _map_vision_result(self, task: Task, result: VisionResult) -> AgentResult:
        if not result.success:
            error_msg = result.error or "Vision analysis failed"
            self._logger.info("VisionAgent task %s failed: %s", task.task_id, error_msg)
            return AgentResult.fail(error=error_msg)

        return AgentResult.ok(output=_summarize(result))
