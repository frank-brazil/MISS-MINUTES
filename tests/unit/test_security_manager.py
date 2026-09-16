import asyncio

import pytest

from app.core.permissions import ToolPermission
from app.security.exceptions import ConfirmationRequired, PermissionDenied
from app.security.manager import SecurityManager, as_security_manager
from app.security.models import (
    ConfirmationStatus,
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


def _manager(
    *,
    allow: tuple[PermissionCategory, ...] = (),
    allow_default: bool = False,
) -> SecurityManager:
    rules = [
        PermissionRule(
            permission=Permission(category=category), effect="allow"
        )
        for category in allow
    ]
    return SecurityManager(
        policy=AllowDenyPolicy(
            rules=rules,
            allow_default=allow_default,
            risk_floor=RiskLevel.MEDIUM,
        )
    )


def test_create_request_computes_risk() -> None:
    manager = _manager()
    request = manager.create_request(
        permission=PermissionCategory.READ, action="tool:file_read"
    )
    assert request.risk_level is RiskLevel.LOW


def test_create_request_explicit_risk_wins() -> None:
    manager = _manager()
    request = manager.create_request(
        permission=PermissionCategory.READ,
        action="tool:file_read",
        risk_level=RiskLevel.HIGH,
    )
    assert request.risk_level is RiskLevel.HIGH


def test_create_request_maps_category_to_permission() -> None:
    manager = _manager()
    request = manager.create_request(
        permission=PermissionCategory.WRITE,
        action="tool:file_create",
        resource="notes.txt",
    )
    assert request.permission.category is PermissionCategory.WRITE
    assert request.permission.resource == "notes.txt"


def test_check_allow_and_audits() -> None:
    manager = _manager(allow=(PermissionCategory.READ,))
    request = manager.create_request(
        permission=PermissionCategory.READ, action="tool:file_read"
    )
    decision = manager.check(request)
    assert decision.allowed
    assert manager.audit_store.count() == 1


def test_check_deny_and_audits() -> None:
    manager = _manager()
    request = manager.create_request(
        permission=PermissionCategory.READ, action="tool:file_read"
    )
    decision = manager.check(request)
    assert decision.denied
    assert decision.reason_code == "missing_permission"
    assert manager.audit_store.count() == 1


def test_check_requires_confirmation_creates_pending() -> None:
    manager = SecurityManager(
        policy=AllowDenyPolicy(
            rules=[
                PermissionRule(
                    permission=Permission(
                        category=PermissionCategory.SYSTEM
                    ),
                    effect="allow",
                )
            ]
        )
    )
    request = manager.create_request(
        permission=PermissionCategory.SYSTEM, action="tool:approved_terminal"
    )
    assert request.risk_level is RiskLevel.HIGH
    decision = manager.check(request)
    assert decision.requires_confirmation
    assert decision.confirmation_id is not None
    stored = manager.confirmation.get(decision.confirmation_id)
    assert stored is not None
    assert stored.status is ConfirmationStatus.PENDING


def test_confirmation_approval_enables_recheck() -> None:
    manager = SecurityManager(
        policy=AllowDenyPolicy(
            rules=[
                PermissionRule(
                    permission=Permission(
                        category=PermissionCategory.SYSTEM
                    ),
                    effect="allow",
                )
            ]
        )
    )
    request = manager.create_request(
        permission=PermissionCategory.SYSTEM, action="tool:approved_terminal"
    )
    first = manager.check(request)
    assert first.requires_confirmation
    manager.confirmation.approve(first.confirmation_id, approved_by="human")
    second = manager.check(request, approved_confirmation_id=first.confirmation_id)
    assert second.allowed
    assert second.reason_code == "approved_confirmation"


def test_require_allowed_raises_on_deny() -> None:
    manager = _manager()
    request = manager.create_request(
        permission=PermissionCategory.READ, action="tool:file_read"
    )
    with pytest.raises(PermissionDenied):
        manager.require_allowed(request)


def test_require_allowed_raises_on_confirmation() -> None:
    manager = SecurityManager(
        policy=AllowDenyPolicy(
            rules=[
                PermissionRule(
                    permission=Permission(
                        category=PermissionCategory.SYSTEM
                    ),
                    effect="allow",
                )
            ]
        )
    )
    request = manager.create_request(
        permission=PermissionCategory.SYSTEM, action="tool:system"
    )
    with pytest.raises(ConfirmationRequired):
        manager.require_allowed(request)


def test_tool_permission_mapping() -> None:
    class FakeReadTool:
        permission = ToolPermission.READ

    class FakeWriteTool:
        permission = ToolPermission.WRITE

    class FakeSystemTool:
        permission = ToolPermission.SYSTEM

    class FakeUndeclaredTool:
        pass

    manager = _manager()
    assert (
        manager.tool_permission(FakeReadTool()).category
        is PermissionCategory.READ
    )
    assert (
        manager.tool_permission(FakeWriteTool()).category
        is PermissionCategory.WRITE
    )
    assert (
        manager.tool_permission(FakeSystemTool()).category
        is PermissionCategory.SYSTEM
    )
    assert manager.tool_permission(FakeUndeclaredTool()) is None


def test_tool_risk_unknown_for_undeclared() -> None:
    class FakeUndeclaredTool:
        pass

    manager = _manager()
    assert manager.tool_risk(FakeUndeclaredTool()) is RiskLevel.UNKNOWN


def test_tool_risk_read_is_low() -> None:
    class FakeReadTool:
        permission = ToolPermission.READ

    manager = _manager()
    assert manager.tool_risk(FakeReadTool()) is RiskLevel.LOW


def test_as_security_manager_normalizes() -> None:
    assert as_security_manager(None) is None
    manager = _manager()
    assert as_security_manager(manager) is manager
    policy = ConservativePolicy()
    wrapped = as_security_manager(policy)
    assert isinstance(wrapped, SecurityManager)
    assert wrapped.policy is policy
    with pytest.raises(TypeError):
        as_security_manager("not a security object")  # type: ignore[arg-type]


def test_audit_event_with_secret_is_redacted() -> None:
    manager = _manager()
    manager.audit_event(
        action="upload with password=hunter2",
        decision_value="deny",
        success=False,
    )
    events = manager.audit_store.snapshot()
    assert "hunter2" not in events[-1].action


def test_evaluate_is_pure() -> None:
    manager = _manager(allow=(PermissionCategory.READ,))
    request = manager.create_request(
        permission=PermissionCategory.READ, action="tool:file_read"
    )
    before = manager.evaluate(request)
    assert manager.audit_store.count() == 0
    assert before.allowed


def test_default_policy_manager_allows_low_risk() -> None:
    manager = SecurityManager(policy=DefaultPolicy())
    request = manager.create_request(
        permission=PermissionCategory.READ, action="tool:file_read"
    )
    assert manager.check(request).allowed


def test_deny_all_manager_blocks_everything() -> None:
    manager = SecurityManager(policy=DenyAllPolicy())
    request = manager.create_request(
        permission=PermissionCategory.READ, action="tool:file_read"
    )
    assert manager.check(request).denied


def test_manager_properties_exposed() -> None:
    manager = _manager(allow=(PermissionCategory.READ,))
    assert isinstance(manager.policy, SecurityPolicy)
    assert manager.confirmation is not None
    assert manager.audit_logger is not None