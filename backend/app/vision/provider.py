"""Provider-independent vision abstraction.

Real vision backends (e.g. a hosted multimodal model) are implemented behind
this boundary.  Nothing in the rest of the system ever hard-codes a provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from app.vision.models import VisionRequest, VisionResult


class VisionError(Exception):
    """Raised by a vision provider on unrecoverable failures."""


class VisionProvider(ABC):
    """Analyzes images and produces structured visual understanding.

    Implementations may raise :class:`VisionError` or any exception; callers
    (e.g. :class:`ScreenUnderstandingService`) turn those into controlled
    ``VisionResult.fail`` results.
    """

    name: ClassVar[str] = "vision"
    description: ClassVar[str] = "Analyses images and produces structured visual understanding."

    # ADD API HERE: REAL VISION PROVIDER / MODEL CREDENTIAL (implement this ABC)
    @abstractmethod
    async def analyze(self, request: VisionRequest) -> VisionResult:
        raise NotImplementedError
