"""Typed exceptions for the security and permissions system.

All security failures are subclasses of :class:`SecurityError` so callers can
catch the family, or the specific typed subclass, without leaking stack
traces to end users.
"""


class SecurityError(Exception):
    """Base exception for the security and permissions system."""


class PermissionDeniedError(SecurityError):
    """An operation was explicitly refused by a policy decision."""


class ConfirmationRequiredError(SecurityError):
    """An operation needs an explicit human approval before it may run."""


class AuthenticationFailedError(SecurityError):
    """A caller could not be authenticated for a protected operation."""


class InvalidSecurityContextError(SecurityError):
    """A request referenced a security context that was missing or invalid."""


class PolicyViolationError(SecurityError):
    """A policy was malformed, contradictory, or violated its own rules."""


class WorkerNotAuthorizedError(SecurityError):
    """A distributed worker is not authorized for the requested operation."""
