"""Single entry point for permission checks, confirmation and audit.

:class:`SecurityManager` composes a policy, a risk assessor, a confirmation
manager and an audit logger behind one small API that every integration point
(Orchestrator, problem-solving loop, distributed coordinator/service) can use.
It never executes operations itself — the existing Tool/ActionExecutor/Worker
boundaries do the actual work after a check passes.
"""

from app.core.permissions import ToolPermission
from app.security.audit import AuditLogger, AuditStore, InMemoryAuditStore
from app.security.confirmation import ConfirmationManager
from app.security.exceptions import (
    ConfirmationRequired,
    PermissionDenied,
)
from app.security.models import (
    AuditEvent,
    Permission,
    PermissionCategory,
    PermissionDecision,
    PermissionRequest,
    RiskLevel,
    SecurityContext,
    SecurityDecision,
)
from app.security.policy import DenyAllPolicy, SecurityPolicy
from app.security.risk import RiskAssessor


def as_security_manager(
    security: "SecurityManager | SecurityPolicy | None",
) -> "SecurityManager | None":
    """Normalize an injected security object to a :class:`SecurityManager`.

    Accepts ``None`` (no enforcement), a bare :class:`SecurityPolicy`, or an
    already-composed :class:`SecurityManager`.  A bare policy gets a manager
    with an in-memory audit store and a confirmation manager so checks remain
    observable.
    """
    if security is None:
        return None
    if isinstance(security, SecurityManager):
        return security
    if isinstance(security, SecurityPolicy):
        return SecurityManager(policy=security)
    raise TypeError(
        f"security must be a SecurityManager or SecurityPolicy, got {type(security).__name__}"
    )


class SecurityManager:
    """Facade over policy evaluation, confirmation and audit."""

    def __init__(
        self,
        *,
        policy: SecurityPolicy | None = None,
        confirmation: ConfirmationManager | None = None,
        audit: AuditStore | None = None,
        risk_assessor: RiskAssessor | None = None,
    ) -> None:
        self._policy = policy if policy is not None else DenyAllPolicy()
        self._confirmation = confirmation or ConfirmationManager()
        self._audit_logger = AuditLogger(audit or InMemoryAuditStore())
        self._risk = risk_assessor or RiskAssessor()

    @property
    def policy(self) -> SecurityPolicy:
        return self._policy

    @property
    def confirmation(self) -> ConfirmationManager:
        return self._confirmation

    @property
    def audit_logger(self) -> AuditLogger:
        return self._audit_logger

    @property
    def audit_store(self) -> AuditStore:
        return self._audit_logger.store

    @property
    def risk_assessor(self) -> RiskAssessor:
        return self._risk

    # ------------------------------------------------------------------
    # Request construction
    # ------------------------------------------------------------------

    def assess(
        self,
        *,
        category: PermissionCategory,
        action: str | None = None,
        resource: str | None = None,
    ) -> RiskLevel:
        return self._risk.assess(category=category, action=action, resource=resource)

    def create_request(
        self,
        *,
        permission: Permission | PermissionCategory,
        action: str,
        risk_level: RiskLevel | None = None,
        session_id=None,
        task_id=None,
        actor: str | None = None,
        origin: str | None = None,
        resource: str | None = None,
    ) -> PermissionRequest:
        """Build a permission request, computing risk when not supplied."""
        if isinstance(permission, PermissionCategory):
            permission = Permission(category=permission)
        if resource is not None:
            permission = Permission(category=permission.category, resource=resource)
        effective_risk = risk_level or self._risk.assess(
            category=permission.category,
            action=action,
            resource=permission.resource,
        )
        return PermissionRequest(
            permission=permission,
            action=action,
            risk_level=effective_risk,
            session_id=session_id,
            task_id=task_id,
            actor=actor,
            origin=origin,
        )

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        request: PermissionRequest,
        *,
        context: SecurityContext | None = None,
    ) -> SecurityDecision:
        """Pure policy evaluation without audit or confirmation side effects."""
        return self._policy.evaluate(request, context=context)

    def check(
        self,
        request: PermissionRequest,
        *,
        context: SecurityContext | None = None,
        approved_confirmation_id=None,
    ) -> SecurityDecision:
        """Evaluate ``request``, handle confirmation, and record an audit
        event.  Returns the decision; the caller must not proceed unless it is
        an allow.
        """
        decision = self._policy.evaluate(request, context=context)

        if decision.requires_confirmation:
            if approved_confirmation_id is not None and (
                self._confirmation.is_active_approval_for(approved_confirmation_id, request)
            ):
                decision = SecurityDecision.allow(
                    reason_code="approved_confirmation",
                    reason="explicit human confirmation approved this request",
                    request_id=request.request_id,
                    confirmation_id=approved_confirmation_id,
                )
            else:
                confirmation = self._confirmation.create(request)
                decision = SecurityDecision.require_confirmation(
                    reason_code="confirmation_required",
                    reason=(f"pending confirmation {confirmation.confirmation_id}"),
                    request_id=request.request_id,
                    confirmation_id=confirmation.confirmation_id,
                )

        self._audit_logger.log(
            request=request,
            decision=decision,
            actor=context.actor_id if context is not None else None,
            origin=context.origin if context is not None else None,
        )
        return decision

    def require_allowed(
        self,
        request: PermissionRequest,
        *,
        context: SecurityContext | None = None,
    ) -> SecurityDecision:
        """Check ``request`` and raise on non-allow outcomes.

        Raises
        ------
        PermissionDenied
            When the policy denies the request.
        ConfirmationRequired
            When the request needs an explicit human confirmation.
        """
        decision = self.check(request, context=context)
        if decision.allowed:
            return decision
        if decision.requires_confirmation:
            raise ConfirmationRequired(decision.reason or "confirmation is required")
        raise PermissionDenied(decision.reason or "permission denied")

    # ------------------------------------------------------------------
    # Tool metadata mapping
    # ------------------------------------------------------------------

    def tool_permission(self, tool) -> Permission | None:
        """Map a Tool's declared ``ToolPermission`` to a security Permission.

        Returns None when the tool does not declare a permission, so callers
        fail closed instead of guessing.
        """
        declared = getattr(tool, "permission", None)
        if declared is ToolPermission.READ:
            return Permission(category=PermissionCategory.READ)
        if declared is ToolPermission.WRITE:
            return Permission(category=PermissionCategory.WRITE)
        if declared is ToolPermission.SYSTEM:
            return Permission(category=PermissionCategory.SYSTEM)
        return None

    def tool_risk(self, tool, action: str | None = None) -> RiskLevel:
        """Assess the risk of a tool call from its declared permission."""
        permission = self.tool_permission(tool)
        if permission is None:
            return RiskLevel.UNKNOWN
        return self._risk.assess(category=permission.category, action=action)

    def audit_event(
        self,
        *,
        request: PermissionRequest | None = None,
        decision: SecurityDecision | None = None,
        action: str | None = None,
        permission: str | None = None,
        resource: str | None = None,
        risk: str | None = None,
        decision_value: str | None = None,
        reason_code: str | None = None,
        success: bool | None = None,
        session_id=None,
        task_id=None,
        actor: str | None = None,
        origin: str | None = None,
    ) -> AuditEvent:
        """Record a free-form audit event (redacted) and return it."""
        return self._audit_logger.log(
            request=request,
            decision=decision,
            action=action,
            permission=permission,
            resource=resource,
            risk=risk,
            decision_value=decision_value,
            reason_code=reason_code,
            success=success,
            session_id=session_id,
            task_id=task_id,
            actor=actor,
            origin=origin,
        )

    def decision_value(self, decision: PermissionDecision) -> str:
        return decision.value
