"""Security and permissions system for MISSMINUTES.

The package provides a centralized, fail-closed permission layer over the
existing Agent/Tool/ActionExecutor/Worker boundaries:

- ``models`` — typed models for permissions, requests, decisions, contexts,
  confirmations and audit events;
- ``exceptions`` — typed security exceptions;
- ``risk`` — deterministic risk assessment for requests;
- ``policy`` — injectable, fail-closed policies (rule-based, conservative,
  default, deny-all);
- ``confirmation`` — human-in-the-loop approval workflow with expiry;
- ``audit`` — structured, redacted audit storage with retention;
- ``redaction`` — heuristic secret-value scrubbing helpers;
- ``manager`` — :class:`SecurityManager`, the single composable entry point.
"""

from app.security.audit import AuditLogger, AuditStore, InMemoryAuditStore
from app.security.confirmation import ConfirmationManager
from app.security.exceptions import (
    AuthenticationFailed,
    ConfirmationRequired,
    InvalidSecurityContext,
    PermissionDenied,
    PolicyViolation,
    SecurityError,
    WorkerNotAuthorized,
)
from app.security.manager import SecurityManager, as_security_manager
from app.security.models import (
    AuditEvent,
    Confirmation,
    ConfirmationStatus,
    Permission,
    PermissionCategory,
    PermissionDecision,
    PermissionRequest,
    PermissionRule,
    RiskLevel,
    SecurityContext,
    SecurityDecision,
)
from app.security.policy import (
    AllowDenyPolicy,
    ConservativePolicy,
    DefaultPolicy,
    DenyAllPolicy,
    SecurityPolicy,
)
from app.security.redaction import (
    REDACTED,
    is_redacted,
    redact,
    redact_mapping,
    redact_string,
    redact_value,
)
from app.security.risk import RiskAssessor, risk_rank

__all__ = [
    "AllowDenyPolicy",
    "AuditEvent",
    "AuditLogger",
    "AuditStore",
    "AuthenticationFailed",
    "Confirmation",
    "ConfirmationManager",
    "ConfirmationRequired",
    "ConfirmationStatus",
    "ConservativePolicy",
    "DefaultPolicy",
    "DenyAllPolicy",
    "InMemoryAuditStore",
    "InvalidSecurityContext",
    "Permission",
    "PermissionCategory",
    "PermissionDecision",
    "PermissionDenied",
    "PermissionRequest",
    "PermissionRule",
    "PolicyViolation",
    "REDACTED",
    "RiskAssessor",
    "RiskLevel",
    "SecurityContext",
    "SecurityDecision",
    "SecurityError",
    "SecurityManager",
    "SecurityPolicy",
    "WorkerNotAuthorized",
    "as_security_manager",
    "is_redacted",
    "redact",
    "redact_mapping",
    "redact_string",
    "redact_value",
    "risk_rank",
]
