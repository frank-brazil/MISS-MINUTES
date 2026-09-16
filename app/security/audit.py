"""Audit log storage, retention and recording.

The audit trail is an append-only, structured list of :class:`AuditEvent`
records.  It deliberately stores **metadata only**: actions and resources are
redacted before they are written (see ``app.security.redaction``), and
credentials are never accepted as fields.

Retention is enforced by the in-memory store: a maximum event count plus an
optional maximum age.  A cleanup pass trims beyond both whenever a record is
added or :meth:`InMemoryAuditStore.cleanup` is called.  The store interface
keeps the door open for a durable backend later.
"""

from abc import ABC, abstractmethod
from typing import Callable
from uuid import UUID

from app.security.models import (
    AuditEvent,
    PermissionRequest,
    SecurityDecision,
)
from app.security.redaction import redact_string


class AuditStore(ABC):
    """Interface every audit backend implements."""

    @abstractmethod
    def record(self, event: AuditEvent) -> None:
        """Persist one audit event."""
        raise NotImplementedError

    @abstractmethod
    def snapshot(self) -> tuple[AuditEvent, ...]:
        """Return every retained event, oldest first."""
        raise NotImplementedError

    @abstractmethod
    def count(self) -> int:
        """Number of retained events."""
        raise NotImplementedError

    @abstractmethod
    def cleanup(self) -> int:
        """Apply retention and return the number of events removed."""
        raise NotImplementedError


class InMemoryAuditStore(AuditStore):
    """Deterministic in-memory audit store with configurable retention."""

    def __init__(
        self,
        *,
        max_events: int = 1000,
        max_age_seconds: float | None = None,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        if max_events < 1:
            raise ValueError("max_events must be at least 1")
        if max_age_seconds is not None and max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be positive when provided")
        import time as _time

        self._max_events = max_events
        self._max_age_seconds = max_age_seconds
        self._now_fn = now_fn or _time.time
        self._events: list[AuditEvent] = []

    @property
    def max_events(self) -> int:
        return self._max_events

    @property
    def max_age_seconds(self) -> float | None:
        return self._max_age_seconds

    def record(self, event: AuditEvent) -> None:
        self._events.append(event)
        self.cleanup()

    def snapshot(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def count(self) -> int:
        return len(self._events)

    def cleanup(self) -> int:
        """Apply retention: drop age-expired events, then the oldest events
        while the count exceeds ``max_events``.  Returns events removed.
        """
        removed = 0
        if self._max_age_seconds is not None:
            now_epoch = self._now_fn()
            kept: list[AuditEvent] = []
            for event in self._events:
                age = now_epoch - event.timestamp.timestamp()
                if age > self._max_age_seconds:
                    removed += 1
                else:
                    kept.append(event)
            self._events = kept

        overflow = len(self._events) - self._max_events
        if overflow > 0:
            del self._events[:overflow]
            removed += overflow
        return removed


class AuditLogger:
    """Builds and persists audit events with redaction applied."""

    def __init__(self, store: AuditStore | None = None) -> None:
        self._store = store or InMemoryAuditStore()

    @property
    def store(self) -> AuditStore:
        return self._store

    def log(
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
        session_id: UUID | None = None,
        task_id: UUID | None = None,
        actor: str | None = None,
        origin: str | None = None,
    ) -> AuditEvent:
        """Record one audit event and return it.

        ``request``/``decision`` pull most fields when provided; any explicit
        keyword overrides them.  Free-text fields (action, resource) are
        redacted before storage.
        """
        event = AuditEvent(
            request_id=request.request_id if request is not None else None,
            session_id=(
                session_id
                if session_id is not None
                else (request.session_id if request is not None else None)
            ),
            task_id=(
                task_id
                if task_id is not None
                else (request.task_id if request is not None else None)
            ),
            actor=(
                actor
                if actor is not None
                else (
                    request.actor
                    if request is not None
                    else (None if decision is None else None)
                )
            ),
            origin=(
                origin
                if origin is not None
                else (request.origin if request is not None else None)
            ),
            action=redact_string(
                action
                if action is not None
                else (request.action if request is not None else "operation")
            ),
            permission=(
                permission
                if permission is not None
                else (
                    request.permission.category.value
                    if request is not None
                    else None
                )
            ),
            resource=redact_string(
                resource
                if resource is not None
                else (
                    request.permission.resource
                    if request is not None
                    else None
                )
            ),
            risk=(
                risk
                if risk is not None
                else (request.risk_level.value if request is not None else None)
            ),
            decision=(
                decision_value
                if decision_value is not None
                else (
                    decision.decision.value
                    if decision is not None
                    else "unknown"
                )
            ),
            reason_code=(
                reason_code
                if reason_code is not None
                else (decision.reason_code if decision is not None else None)
            ),
            success=success,
        )
        if success is None and decision is not None:
            if decision.allowed:
                event.success = True
            elif decision.requires_confirmation:
                event.success = None
            else:
                event.success = False
        self._store.record(event)
        return event
