"""Centralized error types for the MISSMINUTES integration layer.

All errors carry safe, user-friendly messages. Stack traces and internal
details are never exposed through these types.
"""

from __future__ import annotations


class RuntimeBaseError(Exception):
    """Base class for all MISSMINUTES runtime errors."""


class StartupError(RuntimeBaseError):
    """Raised when the runtime fails to start."""


class ShutdownError(RuntimeBaseError):
    """Raised when the runtime fails to shut down cleanly."""


class ProviderUnavailableError(RuntimeBaseError):
    """Raised when an external provider (AI, STT, TTS, etc.) is unavailable."""


class VoiceServiceError(RuntimeBaseError):
    """Raised when the voice pipeline encounters an error."""


class PlannerError(RuntimeBaseError):
    """Raised when the planner fails to produce a plan."""


class AgentError(RuntimeBaseError):
    """Raised when an agent execution fails."""


class ToolDeniedError(RuntimeBaseError):
    """Raised when a tool call is denied by the security policy."""


class BrowserServiceError(RuntimeBaseError):
    """Raised when a browser operation fails."""


class DistributedWorkerError(RuntimeBaseError):
    """Raised when a distributed worker operation fails."""


class VerificationError(RuntimeBaseError):
    """Raised when result verification fails."""


class RequestTimeoutError(RuntimeBaseError):
    """Raised when a request exceeds its time budget."""


class RequestCancelledError(RuntimeBaseError):
    """Raised when a request is cancelled by the caller."""
