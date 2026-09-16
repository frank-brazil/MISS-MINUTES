"""Typed data models for the security and permissions system.

These models describe the *what* of a permission check — the category a
request belongs to, its risk class, the actor/context requesting it, and the
decision a policy produces — plus the audit trail that records it.  They
follow the project conventions: Pydantic models with
``validate_assignment=True``, ``StrEnum`` members, and ``_utc_now``
timestamps.

The models deliberately hold **no secrets**: actors are identifiers, actions
are descriptions, and concrete credential values are never modelled.  Audit
events store redacted metadata only (see ``app.security.redaction``).
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PermissionCategory(StrEnum):
    """Category of operation a permission request describes.

    Categories keep decisions coarse and deterministic.  Tools map their
    existing ``ToolPermission`` (read/write/system) onto
    ``READ``/``WRITE``/``SYSTEM``; higher-level paths (browser, network,
    distributed, actions) use the dedicated categories.
    """

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    BROWSER = "browser"
    NETWORK = "network"
    SYSTEM = "system"
    SENSITIVE = "sensitive"
    DISTRIBUTED = "distributed"


class RiskLevel(StrEnum):
    """Assessed risk class of an operation before policy evaluation."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class PermissionDecision(StrEnum):
    """Outcome a policy can produce for a permission request."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_CONFIRMATION = "require_confirmation"


class Permission(BaseModel):
    """A concrete capability a request asks to exercise.

    ``category`` is the coarse class; ``resource`` optionally narrows the
    subject (a file path, a URL host, a distributed ``task_type``).  A
    resource of ``None`` matches any subject.
    """

    model_config = ConfigDict(validate_assignment=True)

    category: PermissionCategory
    resource: str | None = None

    @field_validator("resource")
    @classmethod
    def _optional_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("resource must not be blank")
        return value


class PermissionRequest(BaseModel):
    """An attempt to perform an operation that requires a permission.

    Created by callers before the operation happens, evaluated against a
    policy, and recorded in the audit trail.  ``action`` is a short,
    human-readable description of the operation (never raw arguments).
    """

    model_config = ConfigDict(validate_assignment=True)

    request_id: UUID = Field(default_factory=uuid4)
    permission: Permission
    action: str
    risk_level: RiskLevel
    session_id: UUID | None = None
    task_id: UUID | None = None
    actor: str | None = None
    origin: str | None = None

    @field_validator("action")
    @classmethod
    def _action_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("action must not be blank")
        return value


class SecurityContext(BaseModel):
    """Who/what is asking and under what binding.

    An optional context attached to a check so a policy can make origin-aware
    decisions (for example, refuse ``DISTRIBUTED`` requests that carry no
    authenticated worker id).  It carries identifiers only, never secrets.
    """

    model_config = ConfigDict(validate_assignment=True)

    actor_id: str | None = None
    session_id: UUID | None = None
    task_id: UUID | None = None
    worker_id: UUID | None = None
    origin: str | None = None
    capabilities: frozenset[str] = Field(default_factory=frozenset)


class SecurityDecision(BaseModel):
    """Outcome of evaluating a permission request."""

    model_config = ConfigDict(validate_assignment=True)

    decision: PermissionDecision
    reason_code: str | None = None
    reason: str | None = None
    request_id: UUID | None = None
    confirmation_id: UUID | None = None

    @property
    def allowed(self) -> bool:
        return self.decision is PermissionDecision.ALLOW

    @property
    def denied(self) -> bool:
        return self.decision is PermissionDecision.DENY

    @property
    def requires_confirmation(self) -> bool:
        return self.decision is PermissionDecision.REQUIRE_CONFIRMATION

    @classmethod
    def allow(
        cls,
        *,
        reason_code: str | None = None,
        reason: str | None = None,
        request_id: UUID | None = None,
        confirmation_id: UUID | None = None,
    ) -> "SecurityDecision":
        return cls(
            decision=PermissionDecision.ALLOW,
            reason_code=reason_code,
            reason=reason,
            request_id=request_id,
            confirmation_id=confirmation_id,
        )

    @classmethod
    def deny(
        cls,
        *,
        reason_code: str | None = None,
        reason: str | None = None,
        request_id: UUID | None = None,
    ) -> "SecurityDecision":
        return cls(
            decision=PermissionDecision.DENY,
            reason_code=reason_code,
            reason=reason,
            request_id=request_id,
        )

    @classmethod
    def require_confirmation(
        cls,
        *,
        reason_code: str | None = None,
        reason: str | None = None,
        request_id: UUID | None = None,
        confirmation_id: UUID | None = None,
    ) -> "SecurityDecision":
        return cls(
            decision=PermissionDecision.REQUIRE_CONFIRMATION,
            reason_code=reason_code,
            reason=reason,
            request_id=request_id,
            confirmation_id=confirmation_id,
        )


class PermissionRule(BaseModel):
    """A declarative allow/deny rule for a permission.

    ``permission.resource``, when set, is matched with a trailing ``*``
    wildcard (``*.txt`` matches ``notes.txt``).  Explicit deny rules always
    win over allow rules.
    """

    model_config = ConfigDict(validate_assignment=True)

    permission: Permission
    effect: Literal["allow", "deny"]

    def matches(self, other: Permission) -> bool:
        if self.permission.category is not other.category:
            return False
        pattern = self.permission.resource
        if pattern is None:
            return True
        value = other.resource or ""
        if pattern.endswith("*") and pattern.startswith("*"):
            return pattern[1:-1] in value
        if pattern.endswith("*"):
            return value.startswith(pattern[:-1])
        if pattern.startswith("*"):
            return value.endswith(pattern[1:])
        return pattern == value


class ConfirmationStatus(StrEnum):
    """Lifecycle of an approval-flow confirmation."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


class Confirmation(BaseModel):
    """A human-in-the-loop gate for a riskier permission request.

    Creating a confirmation is **not** an approval: the operation must not be
    performed while the confirmation is ``PENDING``.  Approvals expire so a
    stale approval cannot enable a later request.
    """

    model_config = ConfigDict(validate_assignment=True)

    confirmation_id: UUID = Field(default_factory=uuid4)
    request_id: UUID
    permission: Permission
    action: str
    risk_level: RiskLevel
    session_id: UUID | None = None
    task_id: UUID | None = None
    actor: str | None = None
    status: ConfirmationStatus = ConfirmationStatus.PENDING
    created_at: datetime = Field(default_factory=_utc_now)
    expires_at: datetime
    approved_by: str | None = None
    denied_by: str | None = None
    resolved_at: datetime | None = None

    @property
    def is_pending(self) -> bool:
        return self.status is ConfirmationStatus.PENDING

    @property
    def is_approved(self) -> bool:
        return self.status is ConfirmationStatus.APPROVED


class AuditEvent(BaseModel):
    """A single immutable audit record for one permission decision.

    Stores structured, redacted metadata only: never passwords, tokens,
    cookies, raw tool arguments, or sensitive file contents.
    """

    model_config = ConfigDict(validate_assignment=True)

    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=_utc_now)
    request_id: UUID | None = None
    session_id: UUID | None = None
    task_id: UUID | None = None
    actor: str | None = None
    origin: str | None = None
    action: str
    permission: str | None = None
    resource: str | None = None
    risk: str | None = None
    decision: str
    reason_code: str | None = None
    success: bool | None = None

    @field_validator("action")
    @classmethod
    def _action_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("action must not be blank")
        return value