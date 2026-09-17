from datetime import UTC, datetime, timedelta

from app.security.audit import AuditLogger, InMemoryAuditStore
from app.security.models import (
    AuditEvent,
    Permission,
    PermissionCategory,
    PermissionRequest,
    RiskLevel,
    SecurityDecision,
)
from app.security.redaction import REDACTED


def _request(action: str = "tool:file_read") -> PermissionRequest:
    return PermissionRequest(
        permission=Permission(category=PermissionCategory.READ),
        action=action,
        risk_level=RiskLevel.LOW,
        actor="alice",
        origin="orchestrator",
    )


def test_record_and_snapshot() -> None:
    store = InMemoryAuditStore()
    logger = AuditLogger(store)
    event = logger.log(
        request=_request(),
        decision=SecurityDecision.allow(reason_code="allow_rule"),
    )
    assert store.count() == 1
    snapshot = store.snapshot()
    assert snapshot[0].event_id == event.event_id
    assert snapshot[0].decision == "allow"


def test_decision_populates_success() -> None:
    logger = AuditLogger()
    allowed = logger.log(
        request=_request(),
        decision=SecurityDecision.allow(reason_code="x"),
    )
    denied = logger.log(
        request=_request(action="tool:terminal"),
        decision=SecurityDecision.deny(reason_code="y"),
    )
    confirm = logger.log(
        request=_request(),
        decision=SecurityDecision.require_confirmation(),
    )
    assert allowed.success is True
    assert denied.success is False
    assert confirm.success is None


def test_metadata_is_redacted_before_storage() -> None:
    logger = AuditLogger()
    event = logger.log(
        request=_request(action="delete with password=hunter2 and api_key: sk-abc"),
    )
    stored = logger.store.snapshot()[-1]
    assert "hunter2" not in stored.action
    assert REDACTED in stored.action
    assert event.action == stored.action


def test_resource_redacted() -> None:
    request = PermissionRequest(
        permission=Permission(
            category=PermissionCategory.READ,
            resource="token=abcd1234efgh5678secret",
        ),
        action="tool:file_read",
        risk_level=RiskLevel.LOW,
    )
    logger = AuditLogger()
    logger.log(request=request, decision=SecurityDecision.allow())
    stored = logger.store.snapshot()[-1]
    assert "abcd1234" not in (stored.resource or "")
    assert stored.resource is not None


def test_max_events_retention() -> None:
    store = InMemoryAuditStore(max_events=5)
    logger = AuditLogger(store)
    for _ in range(10):
        logger.log(request=_request(), decision=SecurityDecision.allow())
    assert store.count() == 5
    assert store.cleanup() == 0


def test_age_based_cleanup() -> None:
    base = datetime.now(UTC)
    store = InMemoryAuditStore(max_age_seconds=100)

    old = AuditEvent(
        timestamp=base - timedelta(seconds=500),
        action="old operation",
        decision="allow",
    )
    new = AuditEvent(timestamp=base, action="new operation", decision="allow")
    store.record(old)
    store.record(new)
    store.cleanup()
    actions = [event.action for event in store.snapshot()]
    assert "new operation" in actions
    assert "old operation" not in actions


def test_cleanup_enforces_max_events_eagerly() -> None:
    store = InMemoryAuditStore(max_events=3)
    for i in range(5):
        store.record(AuditEvent(action=f"op-{i}", decision="allow"))
    assert store.count() == 3
    assert store.cleanup() == 0
    actions = [event.action for event in store.snapshot()]
    assert "op-4" in actions  # newest kept
    assert "op-0" not in actions  # oldest dropped


def test_never_store_secret_files() -> None:
    logger = AuditLogger()
    request = _request(action="file_read: /private/ssh/id_rsa with password=topsecret")
    logger.log(request=request, decision=SecurityDecision.allow())
    events_text = " ".join(event.action for event in logger.store.snapshot())
    assert "/private/ssh/id_rsa" in events_text  # path itself is fine
    assert "topsecret" not in events_text  # credential-like value is not


def test_audit_event_defaults_request_fields() -> None:
    request = PermissionRequest(
        permission=Permission(category=PermissionCategory.WRITE),
        action="tool:file_create",
        risk_level=RiskLevel.MEDIUM,
        actor="bob",
        origin="solver",
    )
    logger = AuditLogger()
    event = logger.log(request=request, decision=SecurityDecision.allow())
    assert event.actor == "bob"
    assert event.origin == "solver"
    assert event.permission == "write"
    assert event.risk == "medium"


def test_explicit_overrides() -> None:
    logger = AuditLogger()
    event = logger.log(
        request=_request(),
        decision=SecurityDecision.allow(),
        action="override",
        success=False,
    )
    assert event.action == "override"
    assert event.success is False


def test_in_memory_store_validates_max_events() -> None:
    import pytest

    with pytest.raises(ValueError):
        InMemoryAuditStore(max_events=0)
