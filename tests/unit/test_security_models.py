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


def test_permission_categories() -> None:
    assert PermissionCategory.READ == "read"
    assert PermissionCategory.WRITE == "write"
    assert PermissionCategory.EXECUTE == "execute"
    assert PermissionCategory.BROWSER == "browser"
    assert PermissionCategory.NETWORK == "network"
    assert PermissionCategory.SYSTEM == "system"
    assert PermissionCategory.SENSITIVE == "sensitive"
    assert PermissionCategory.DISTRIBUTED == "distributed"


def test_risk_levels() -> None:
    assert RiskLevel.LOW == "low"
    assert RiskLevel.MEDIUM == "medium"
    assert RiskLevel.HIGH == "high"
    assert RiskLevel.CRITICAL == "critical"
    assert RiskLevel.UNKNOWN == "unknown"


def test_decision_enum() -> None:
    assert set(PermissionDecision) == {
        PermissionDecision.ALLOW,
        PermissionDecision.DENY,
        PermissionDecision.REQUIRE_CONFIRMATION,
    }


def test_permission_resource_must_not_be_blank() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Permission(category=PermissionCategory.READ, resource="  ")


def test_permission_request_action_must_not_be_blank() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PermissionRequest(
            permission=Permission(category=PermissionCategory.READ),
            action=" ",
            risk_level=RiskLevel.LOW,
        )


def test_permission_rule_resource_wildcard_matching() -> None:
    rule = PermissionRule(
        permission=Permission(category=PermissionCategory.READ, resource="*.txt"),
        effect="allow",
    )
    assert rule.matches(
        Permission(category=PermissionCategory.READ, resource="notes.txt")
    )
    assert not rule.matches(
        Permission(category=PermissionCategory.READ, resource="notes.md")
    )
    assert not rule.matches(
        Permission(category=PermissionCategory.WRITE, resource="notes.txt")
    )


def test_permission_rule_null_resource_matches_any() -> None:
    rule = PermissionRule(
        permission=Permission(category=PermissionCategory.READ),
        effect="deny",
    )
    assert rule.matches(
        Permission(category=PermissionCategory.READ, resource="anything")
    )
    assert rule.matches(Permission(category=PermissionCategory.READ))


def test_security_decision_flags() -> None:
    allow = SecurityDecision.allow(reason_code="x")
    deny = SecurityDecision.deny(reason_code="y")
    confirm = SecurityDecision.require_confirmation()
    assert allow.allowed and not allow.denied and not allow.requires_confirmation
    assert deny.denied and not deny.allowed
    assert confirm.requires_confirmation and not confirm.allowed


def test_security_context_carries_identifiers_only() -> None:
    context = SecurityContext(
        actor_id="worker-1",
        worker_id=None,
        origin="distributed-worker",
        capabilities=frozenset({"analysis"}),
    )
    assert context.actor_id == "worker-1"
    assert context.capabilities == frozenset({"analysis"})


def test_features_exist() -> None:
    # The full typed exception + model vocabulary CHUNK 30 requires exists
    # and is importable from the package.
    from app.security import (
        AuthenticationFailed,
        ConfirmationRequired,
        InvalidSecurityContext,
        PermissionDenied,
        PolicyViolation,
        SecurityError,
        WorkerNotAuthorized,
    )

    for exc in (
        AuthenticationFailed,
        ConfirmationRequired,
        InvalidSecurityContext,
        PermissionDenied,
        PolicyViolation,
        WorkerNotAuthorized,
    ):
        assert issubclass(exc, SecurityError)

    assert ConfirmationStatus.PENDING.value == "pending"
    assert AuditEvent is not None
    assert Confirmation is not None