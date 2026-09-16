import pytest

from app.security.models import (
    Permission,
    PermissionCategory,
    PermissionDecision,
    PermissionRequest,
    PermissionRule,
    RiskLevel,
    SecurityContext,
)
from app.security.policy import (
    AllowDenyPolicy,
    ConservativePolicy,
    DefaultPolicy,
    DenyAllPolicy,
    SecurityPolicy,
)


def _request(
    category: PermissionCategory,
    risk: RiskLevel,
    resource: str | None = None,
) -> PermissionRequest:
    return PermissionRequest(
        permission=Permission(category=category, resource=resource),
        action=f"request:{category.value}",
        risk_level=risk,
    )


def test_precedence_explicit_deny_beats_everything() -> None:
    policy = AllowDenyPolicy(
        rules=[
            PermissionRule(
                permission=Permission(category=PermissionCategory.WRITE),
                effect="allow",
            ),
            PermissionRule(
                permission=Permission(category=PermissionCategory.WRITE),
                effect="deny",
            ),
        ]
    )
    decision = policy.evaluate(
        _request(PermissionCategory.WRITE, RiskLevel.LOW)
    )
    assert decision.decision is PermissionDecision.DENY
    assert decision.reason_code == "deny_rule"


def test_unknown_risk_fails_closed() -> None:
    policy = ConservativePolicy(
        rules=[
            PermissionRule(
                permission=Permission(
                    category=PermissionCategory.READ
                ),
                effect="allow",
            )
        ]
    )
    decision = policy.evaluate(
        _request(PermissionCategory.READ, RiskLevel.UNKNOWN)
    )
    assert decision.decision is PermissionDecision.DENY
    assert decision.reason_code == "unknown_risk"


def test_critical_risk_never_auto_approved() -> None:
    policy = AllowDenyPolicy(
        rules=[
            PermissionRule(
                permission=Permission(
                    category=PermissionCategory.SENSITIVE
                ),
                effect="allow",
            )
        ],
        allow_default=True,
    )
    decision = policy.evaluate(
        _request(PermissionCategory.SENSITIVE, RiskLevel.CRITICAL)
    )
    assert decision.decision is PermissionDecision.DENY
    assert decision.reason_code == "critical_risk"


def test_missing_permission_denied() -> None:
    policy = ConservativePolicy()
    decision = policy.evaluate(
        _request(PermissionCategory.READ, RiskLevel.LOW)
    )
    assert decision.decision is PermissionDecision.DENY
    assert decision.reason_code == "missing_permission"


def test_allow_via_rule() -> None:
    policy = AllowDenyPolicy(
        rules=[
            PermissionRule(
                permission=Permission(
                    category=PermissionCategory.READ
                ),
                effect="allow",
            )
        ]
    )
    decision = policy.evaluate(
        _request(PermissionCategory.READ, RiskLevel.LOW)
    )
    assert decision.decision is PermissionDecision.ALLOW
    assert decision.reason_code == "allow_rule"


def test_high_risk_requires_confirmation_even_when_allowed() -> None:
    policy = AllowDenyPolicy(
        rules=[
            PermissionRule(
                permission=Permission(
                    category=PermissionCategory.SYSTEM
                ),
                effect="allow",
            )
        ]
    )
    decision = policy.evaluate(
        _request(PermissionCategory.SYSTEM, RiskLevel.HIGH)
    )
    assert (
        decision.decision
        is PermissionDecision.REQUIRE_CONFIRMATION
    )
    assert decision.reason_code == "confirmation_required"


def test_medium_risk_rule_allowed_without_confirmation() -> None:
    policy = AllowDenyPolicy(
        rules=[
            PermissionRule(
                permission=Permission(
                    category=PermissionCategory.WRITE
                ),
                effect="allow",
            )
        ]
    )
    decision = policy.evaluate(
        _request(PermissionCategory.WRITE, RiskLevel.MEDIUM)
    )
    assert decision.decision is PermissionDecision.ALLOW


def test_default_policy_auto_allows_low_medium() -> None:
    policy = DefaultPolicy()
    assert (
        policy.evaluate(
            _request(PermissionCategory.READ, RiskLevel.LOW)
        ).decision
        is PermissionDecision.ALLOW
    )
    assert (
        policy.evaluate(
            _request(PermissionCategory.WRITE, RiskLevel.MEDIUM)
        ).decision
        is PermissionDecision.ALLOW
    )


def test_default_policy_high_without_rule_is_denied() -> None:
    policy = DefaultPolicy()
    high = policy.evaluate(
        _request(PermissionCategory.SYSTEM, RiskLevel.HIGH)
    )
    assert high.decision is PermissionDecision.DENY
    assert high.reason_code == "missing_permission"


def test_default_policy_high_with_allow_rule_requires_confirmation() -> None:
    request = _request(PermissionCategory.SYSTEM, RiskLevel.HIGH)
    rule = PermissionRule(
        permission=Permission(category=PermissionCategory.SYSTEM),
        effect="allow",
    )
    explicit = AllowDenyPolicy(
        rules=[rule], allow_default=True, risk_floor=RiskLevel.MEDIUM
    ).evaluate(request)
    assert explicit.decision is PermissionDecision.REQUIRE_CONFIRMATION
    assert explicit.reason_code == "confirmation_required"


def test_default_policy_critical_is_denied_even_with_rule() -> None:
    policy = AllowDenyPolicy(
        rules=[
            PermissionRule(
                permission=Permission(category=PermissionCategory.SYSTEM),
                effect="allow",
            )
        ],
        allow_default=True,
        risk_floor=RiskLevel.MEDIUM,
    )
    critical = policy.evaluate(
        _request(PermissionCategory.SENSITIVE, RiskLevel.CRITICAL)
    )
    assert critical.decision is PermissionDecision.DENY
    assert critical.reason_code == "critical_risk"


def test_conservative_policy_denies_without_rules() -> None:
    policy = ConservativePolicy()
    assert (
        policy.evaluate(
            _request(PermissionCategory.READ, RiskLevel.LOW)
        ).decision
        is PermissionDecision.DENY
    )


def test_deny_all_policy() -> None:
    policy = DenyAllPolicy()
    decision = policy.evaluate(
        _request(PermissionCategory.READ, RiskLevel.LOW)
    )
    assert decision.decision is PermissionDecision.DENY
    assert decision.reason_code == "deny_all"


def test_resource_specific_allow_rule() -> None:
    policy = AllowDenyPolicy(
        rules=[
            PermissionRule(
                permission=Permission(
                    category=PermissionCategory.DISTRIBUTED,
                    resource="analysis",
                ),
                effect="allow",
            )
        ]
    )
    allowed = policy.evaluate(
        _request(
            PermissionCategory.DISTRIBUTED,
            RiskLevel.MEDIUM,
            resource="analysis",
        )
    )
    denied = policy.evaluate(
        _request(
            PermissionCategory.DISTRIBUTED,
            RiskLevel.MEDIUM,
            resource="coding",
        )
    )
    assert allowed.decision is PermissionDecision.ALLOW
    assert denied.decision is PermissionDecision.DENY


def test_policy_is_deterministic() -> None:
    policy = AllowDenyPolicy(
        rules=[
            PermissionRule(
                permission=Permission(
                    category=PermissionCategory.READ
                ),
                effect="allow",
            )
        ]
    )
    request = _request(PermissionCategory.READ, RiskLevel.LOW)
    first = policy.evaluate(request)
    second = policy.evaluate(request)
    assert first.decision is second.decision
    assert first.reason_code == second.reason_code


def test_policy_accepts_context_without_state_change() -> None:
    policy = ConservativePolicy()
    context = SecurityContext(actor_id="someone", origin="test")
    before = policy.evaluate(
        _request(PermissionCategory.READ, RiskLevel.LOW),
        context=context,
    )
    after = policy.evaluate(
        _request(PermissionCategory.READ, RiskLevel.LOW),
        context=context,
    )
    assert before.decision is after.decision


def test_evaluate_is_pure_no_side_effects() -> None:
    policy = DenyAllPolicy()
    request = _request(PermissionCategory.READ, RiskLevel.LOW)
    decision_1 = policy.evaluate(request)
    decision_2 = policy.evaluate(request)
    assert decision_1.request_id == request.request_id
    assert decision_2.decision is decision_1.decision


def test_security_policy_is_abstract() -> None:
    with pytest.raises(TypeError):
        SecurityPolicy()  # type: ignore[abstract]