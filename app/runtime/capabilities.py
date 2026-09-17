"""Capability registry and health reporting for the MISSMINUTES runtime.

Provides a central view of which subsystems are available and a unified
health/readiness summary. Does not duplicate any existing capability system.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, Field


class CapabilityStatus(BaseModel):
    """Status of one subsystem capability."""

    name: str
    available: bool
    detail: str | None = None


class HealthReport(BaseModel):
    """Unified health/readiness report for the runtime."""

    ready: bool
    capabilities: list[CapabilityStatus] = Field(default_factory=list)
    uptime_seconds: float = 0.0
    request_count: int = 0


class CapabilityRegistry:
    """Tracks which subsystems are available and produces health reports."""

    def __init__(self) -> None:
        self._capabilities: dict[str, CapabilityStatus] = {}
        self._start_time: float = time.time()

    def register(self, name: str, available: bool, detail: str | None = None) -> None:
        """Register or update a capability status."""
        self._capabilities[name] = CapabilityStatus(name=name, available=available, detail=detail)

    def is_available(self, name: str) -> bool:
        """Check if a named capability is available."""
        cap = self._capabilities.get(name)
        return cap.available if cap is not None else False

    @property
    def start_time(self) -> float:
        return self._start_time

    def health_report(self, ready: bool, request_count: int = 0) -> HealthReport:
        """Build a snapshot health report."""
        return HealthReport(
            ready=ready,
            capabilities=list(self._capabilities.values()),
            uptime_seconds=time.time() - self._start_time,
            request_count=request_count,
        )

    def all_capabilities(self) -> dict[str, bool]:
        """Return a flat name → available mapping."""
        return {name: cap.available for name, cap in self._capabilities.items()}
