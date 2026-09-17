from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.security.confirmation import ConfirmationManager
from app.security.exceptions import (
    ConfirmationRequired,
    PermissionDenied,
    SecurityError,
)
from app.security.models import (
    ConfirmationStatus,
    Permission,
    PermissionCategory,
    PermissionRequest,
    RiskLevel,
)


def _request(
    category: PermissionCategory = PermissionCategory.SYSTEM,
    risk: RiskLevel = RiskLevel.HIGH,
    actor: str | None = "approver",
) -> PermissionRequest:
    return PermissionRequest(
        permission=Permission(category=category),
        action=f"operation:{category.value}",
        risk_level=risk,
        actor=actor,
    )


def test_create_is_never_an_approval() -> None:
    manager = ConfirmationManager()
    confirmation = manager.create(_request())
    assert confirmation.status is ConfirmationStatus.PENDING
    assert not confirmation.is_approved


def test_approve_requires_explicit_call() -> None:
    manager = ConfirmationManager()
    confirmation = manager.create(_request())
    updated = manager.approve(confirmation.confirmation_id, approved_by="human")
    assert updated.status is ConfirmationStatus.APPROVED
    assert updated.approved_by == "human"
    assert updated.resolved_at is not None


def test_deny_records_denier() -> None:
    manager = ConfirmationManager()
    confirmation = manager.create(_request())
    updated = manager.deny(confirmation.confirmation_id, denied_by="human")
    assert updated.status is ConfirmationStatus.DENIED
    assert updated.denied_by == "human"


def test_unknown_confirmation_raises() -> None:
    manager = ConfirmationManager()
    with pytest.raises(PermissionDenied):
        manager.approve(uuid4())
    with pytest.raises(PermissionDenied):
        manager.deny(uuid4())


def test_approving_twice_raises() -> None:
    manager = ConfirmationManager()
    confirmation = manager.create(_request())
    manager.approve(confirmation.confirmation_id, approved_by="human")
    with pytest.raises(SecurityError):
        manager.approve(confirmation.confirmation_id, approved_by="human")


def test_expiry_blocks_late_approval() -> None:
    now = datetime.now(UTC)
    manager = ConfirmationManager(ttl_seconds=5.0, now_fn=lambda: now)
    confirmation = manager.create(_request())
    later = now + timedelta(seconds=6)
    manager._now_fn = lambda: later  # simulate clock moving forward

    assert manager.expire() == 1
    assert manager.get(confirmation.confirmation_id).status is ConfirmationStatus.EXPIRED
    with pytest.raises(ConfirmationRequired):
        manager.approve(confirmation.confirmation_id, approved_by="late")


def test_pending_lists_only_active() -> None:
    manager = ConfirmationManager()
    first = manager.create(_request())
    manager.create(_request())
    manager.deny(first.confirmation_id, denied_by="human")
    pending = manager.pending()
    assert len(pending) == 1
    assert pending[0].confirmation_id != first.confirmation_id


def test_is_active_approval_for_requires_exact_request() -> None:
    manager = ConfirmationManager()
    request = _request()
    confirmation = manager.create(request)
    assert not manager.is_active_approval_for(confirmation.confirmation_id, request)
    manager.approve(confirmation.confirmation_id, approved_by="human")
    assert manager.is_active_approval_for(confirmation.confirmation_id, request)
    other = _request(category=PermissionCategory.READ, risk=RiskLevel.LOW)
    assert not manager.is_active_approval_for(confirmation.confirmation_id, other)


def test_expired_confirmation_is_not_an_active_approval() -> None:
    now = datetime.now(UTC)
    manager = ConfirmationManager(ttl_seconds=5.0, now_fn=lambda: now)
    request = _request()
    confirmation = manager.create(request)
    manager.approve(confirmation.confirmation_id, approved_by="human")
    later = now + timedelta(seconds=10)
    manager._now_fn = lambda: later
    assert not manager.is_active_approval_for(confirmation.confirmation_id, request)


def test_ttl_seconds_validation() -> None:
    with pytest.raises(ValueError):
        ConfirmationManager(ttl_seconds=0)


def test_deterministic_id_generation() -> None:
    fixed = uuid4()
    manager = ConfirmationManager(id_gen=lambda: fixed)
    confirmation = manager.create(_request())
    assert confirmation.confirmation_id == fixed


def test_resolved_confirmation_keeps_history() -> None:
    manager = ConfirmationManager()
    first = manager.create(_request())
    manager.create(_request())
    manager.deny(first.confirmation_id, denied_by="human")
    resolved = manager.resolved()
    assert any(c.confirmation_id == first.confirmation_id for c in resolved)
