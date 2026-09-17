"""Deterministic, fail-closed permission policies.

Policies decide *whether* an operation may proceed.  They never execute the
operation themselves; execution belongs to the existing Tool/Agent/Executor
boundaries.  A policy takes a :class:`PermissionRequest` (and an optional
:class:`SecurityContext`) and returns a :class:`SecurityDecision`.

Evaluation precedence (highest first):

1. an explicit deny rule matches  -> ``DENY``
2. risk is unknown                -> ``DENY`` (fail closed)
3. risk is critical               -> ``DENY`` (critical actions are never
   auto-approved)
4. no allow rule matches          -> ``DENY`` (missing permission)
5. risk requires confirmation     -> ``REQUIRE_CONFIRMATION`` (an approval
   gate, never an auto-approval)
6. otherwise                      -> ``ALLOW``

Policies are pure and injectable: a policy must not read global mutable state
or contact any external service.
"""

from abc import ABC, abstractmethod
from typing import Iterable

from app.security.models import (
    PermissionCategory,
    PermissionRequest,
    PermissionRule,
    RiskLevel,
    SecurityContext,
    SecurityDecision,
)


class SecurityPolicy(ABC):
    """Interface every permission policy implements."""

    @abstractmethod
    def evaluate(
        self,
        request: PermissionRequest,
        context: SecurityContext | None = None,
    ) -> SecurityDecision:
        """Return the decision for ``request`` under this policy.

        Must be deterministic for identical inputs and free of side effects.
        """
        raise NotImplementedError


class AllowDenyPolicy(SecurityPolicy):
    """Rule-based policy implementing the documented evaluation precedence.

    Parameters
    ----------
    rules
        Declarative allow/deny rules.  Deny always wins over allow.
    require_confirmation
        Risk classes that, when otherwise allowed, still require an explicit
        human confirmation before the operation runs.
    allow_default
        When True, a request with no matching allow rule may be allowed if its
        risk is at or below ``risk_floor`` and not in
        ``require_confirmation``.  Off by default so the policy fails closed.
    risk_floor
        Highest risk class an un-ruled request may reach with
        ``allow_default=True``.  ``HIGH``/``CRITICAL``/``UNKNOWN`` risks are
        never auto-allowed.
    """

    def __init__(
        self,
        *,
        rules: Iterable[PermissionRule] = (),
        require_confirmation: Iterable[RiskLevel] = (RiskLevel.HIGH,),
        allow_default: bool = False,
        risk_floor: RiskLevel = RiskLevel.LOW,
    ) -> None:
        self._rules = tuple(rules)
        self._require_confirmation = frozenset(require_confirmation)
        self._allow_default = allow_default
        self._risk_floor = risk_floor

    @property
    def rules(self) -> tuple[PermissionRule, ...]:
        return self._rules

    @property
    def require_confirmation(self) -> frozenset[RiskLevel]:
        return self._require_confirmation

    @property
    def allow_default(self) -> bool:
        return self._allow_default

    @property
    def risk_floor(self) -> RiskLevel:
        return self._risk_floor

    def evaluate(
        self,
        request: PermissionRequest,
        context: SecurityContext | None = None,
    ) -> SecurityDecision:
        request_id = request.request_id

        deny = [
            rule
            for rule in self._rules
            if rule.effect == "deny" and rule.matches(request.permission)
        ]
        if deny:
            return SecurityDecision.deny(
                reason_code="deny_rule",
                reason="explicit deny rule matches this permission",
                request_id=request_id,
            )

        risk = request.risk_level
        if risk is RiskLevel.UNKNOWN:
            return SecurityDecision.deny(
                reason_code="unknown_risk",
                reason="risk could not be assessed; failing closed",
                request_id=request_id,
            )
        if risk is RiskLevel.CRITICAL:
            return SecurityDecision.deny(
                reason_code="critical_risk",
                reason="critical risk is not auto-approved",
                request_id=request_id,
            )

        allow = [
            rule
            for rule in self._rules
            if rule.effect == "allow" and rule.matches(request.permission)
        ]
        if not allow:
            if self._allow_default:
                from app.security.risk import risk_rank

                if risk_rank(risk) <= risk_rank(self._risk_floor):
                    if risk in self._require_confirmation:
                        return SecurityDecision.require_confirmation(
                            reason_code="confirmation_required",
                            reason=(f"risk '{risk.value}' requires confirmation before approval"),
                            request_id=request_id,
                        )
                    return SecurityDecision.allow(
                        reason_code="allow_default",
                        reason="risk is at or below the default floor",
                        request_id=request_id,
                    )
            return SecurityDecision.deny(
                reason_code="missing_permission",
                reason="no allow rule covers this permission",
                request_id=request_id,
            )

        if risk in self._require_confirmation:
            return SecurityDecision.require_confirmation(
                reason_code="confirmation_required",
                reason=(f"risk '{risk.value}' requires confirmation before approval"),
                request_id=request_id,
            )
        return SecurityDecision.allow(
            reason_code="allow_rule",
            reason="explicit allow rule matches this permission",
            request_id=request_id,
        )


class ConservativePolicy(AllowDenyPolicy):
    """Fail-closed policy: only explicitly allowed permissions run.

    No default allowances, no implicit trust.  Any permission without a
    matching allow rule is denied; unknown and critical risks are denied even
    when a rule matches; high-risk permissions require a confirmation.
    """

    def __init__(
        self,
        *,
        rules: Iterable[PermissionRule] = (),
        require_confirmation: Iterable[RiskLevel] = (RiskLevel.HIGH,),
    ) -> None:
        super().__init__(
            rules=rules,
            require_confirmation=require_confirmation,
            allow_default=False,
            risk_floor=RiskLevel.LOW,
        )


class DefaultPolicy(AllowDenyPolicy):
    """Convenience default policy for explicit, low-risk opt-in.

    Low- and medium-risk requests without a rule are auto-allowed; unknown and
    critical risks are always denied, and high-risk requests without a matching
    allow rule are denied too.  Explicit allow rules are evaluated under the
    standard precedence, so a high-risk permission with an allow rule still
    requires a human confirmation.  This is only suitable for local,
    single-actor tooling.
    """

    def __init__(
        self,
        *,
        require_confirmation: Iterable[RiskLevel] = (RiskLevel.HIGH,),
        risk_floor: RiskLevel = RiskLevel.MEDIUM,
    ) -> None:
        super().__init__(
            rules=(),
            require_confirmation=require_confirmation,
            allow_default=True,
            risk_floor=risk_floor,
        )


class DenyAllPolicy(SecurityPolicy):
    """Deny every request.  Used as the conservative default whenever a
    security boundary is enabled but no real policy has been configured.
    """

    def evaluate(
        self,
        request: PermissionRequest,
        context: SecurityContext | None = None,
    ) -> SecurityDecision:
        return SecurityDecision.deny(
            reason_code="deny_all",
            reason="all operations are denied by policy",
            request_id=request.request_id,
        )


def is_denied_by_default(category: PermissionCategory) -> bool:
    """Return True for categories this system never auto-approves.

    ``SENSITIVE`` and ``DISTRIBUTED`` are treated as opt-in categories: a
    caller must provide an explicit allow rule for them.
    """
    return category in (
        PermissionCategory.SENSITIVE,
        PermissionCategory.DISTRIBUTED,
    )
