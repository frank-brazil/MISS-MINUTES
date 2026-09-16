"""Confirmation (approval-flow) management.

A confirmation gates an otherwise-allowed, higher-risk operation behind an
explicit human approval:

- creating a confirmation is **never** an approval;
- approving must be an explicit, separate caller action;
- confirmations expire, so a stale approval cannot enable a later request;
- every approval/denial is recorded with an approver identifier and when it
  happened.

The manager is injectable and deterministic: tests may supply ``now_fn`` and
``id_gen`` instead of a wall clock.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.security.exceptions import (
    ConfirmationRequired,
    PermissionDenied,
    SecurityError,
)
from app.security.models import (
    Confirmation,
    ConfirmationStatus,
    PermissionRequest,
)
from app.security.redaction import redact_string

DEFAULT_CONFIRMATION_TTL_SECONDS = 60.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ConfirmationManager:
    """Tracks pending and resolved confirmations for permission requests."""

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_CONFIRMATION_TTL_SECONDS,
        now_fn: Callable[[], datetime] | None = None,
        id_gen: Callable[[], UUID] | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl_seconds = ttl_seconds
        self._now_fn = now_fn or _utc_now
        self._id_gen = id_gen or uuid4
        self._confirmations: dict[UUID, Confirmation] = {}

    @property
    def ttl_seconds(self) -> float:
        return self._ttl_seconds

    def create(self, request: PermissionRequest) -> Confirmation:
        """Open a new pending confirmation for ``request``.

        Never auto-approves.  The caller must call :meth:`approve` before the
        protected operation may run, and must re-check the decision after
        approval.
        """
        now = self._now_fn()
        confirmation = Confirmation(
            confirmation_id=self._id_gen(),
            request_id=request.request_id,
            permission=request.permission,
            action=redact_string(request.action),
            risk_level=request.risk_level,
            session_id=request.session_id,
            task_id=request.task_id,
            actor=request.actor,
            status=ConfirmationStatus.PENDING,
            created_at=now,
            expires_at=now + timedelta(seconds=self._ttl_seconds),
        )
        self._confirmations[confirmation.confirmation_id] = confirmation
        return confirmation

    def get(self, confirmation_id: UUID) -> Confirmation | None:
        """Return a confirmation by id, or ``None`` when unknown."""
        return self._confirmations.get(confirmation_id)

    def pending(self) -> tuple[Confirmation, ...]:
        """Return all currently pending (unexpired) confirmations."""
        self.expire()
        return tuple(
            confirmation
            for confirmation in self._confirmations.values()
            if confirmation.status is ConfirmationStatus.PENDING
        )

    def resolved(self) -> tuple[Confirmation, ...]:
        """Return every confirmed/denied/expired confirmation."""
        return tuple(
            confirmation
            for confirmation in self._confirmations.values()
            if confirmation.status is not ConfirmationStatus.PENDING
        )

    def approve(
        self,
        confirmation_id: UUID,
        *,
        approved_by: str | None = None,
    ) -> Confirmation:
        """Approve a pending confirmation.

        Raises
        ------
        SecurityError
            When the confirmation is unknown or has already been resolved.
        ConfirmationRequired
            When the confirmation has expired before approval.
        """
        confirmation = self._get_resolvable(confirmation_id)
        confirmation.status = ConfirmationStatus.APPROVED
        confirmation.approved_by = approved_by
        confirmation.resolved_at = self._now_fn()
        return confirmation

    def deny(
        self,
        confirmation_id: UUID,
        *,
        denied_by: str | None = None,
    ) -> Confirmation:
        """Deny a pending confirmation."""
        confirmation = self._get_resolvable(confirmation_id)
        confirmation.status = ConfirmationStatus.DENIED
        confirmation.denied_by = denied_by
        confirmation.resolved_at = self._now_fn()
        return confirmation

    def expire(self) -> int:
        """Mark pending confirmations past their expiry as ``EXPIRED``.

        Returns the number of confirmations expired by this call.
        """
        now = self._now_fn()
        expired = 0
        for confirmation in self._confirmations.values():
            if (
                confirmation.status is ConfirmationStatus.PENDING
                and confirmation.expires_at <= now
            ):
                confirmation.status = ConfirmationStatus.EXPIRED
                confirmation.resolved_at = now
                expired += 1
        return expired

    def is_active_approval_for(
        self,
        confirmation_id: UUID,
        request: PermissionRequest,
    ) -> bool:
        """Return True when ``confirmation_id`` is an active approval for
        exactly this request.

        The confirmation must be APPROVED, not expired, and must reference the
        same request.  This is how a caller proves an explicit human approval
        before re-checking a request.
        """
        confirmation = self._confirmations.get(confirmation_id)
        if confirmation is None:
            return False
        if confirmation.request_id != request.request_id:
            return False
        if confirmation.status is ConfirmationStatus.PENDING:
            return False
        if (
            confirmation.status is ConfirmationStatus.EXPIRED
            or confirmation.expires_at <= self._now_fn()
        ):
            return False
        return confirmation.status is ConfirmationStatus.APPROVED

    def _get_resolvable(self, confirmation_id: UUID) -> Confirmation:
        confirmation = self._confirmations.get(confirmation_id)
        if confirmation is None:
            raise PermissionDenied(
                f"confirmation {confirmation_id} does not exist"
            )
        if confirmation.status is ConfirmationStatus.PENDING and (
            confirmation.expires_at <= self._now_fn()
        ):
            confirmation.status = ConfirmationStatus.EXPIRED
            confirmation.resolved_at = self._now_fn()
        if confirmation.status is ConfirmationStatus.EXPIRED:
            raise ConfirmationRequired(
                f"confirmation {confirmation_id} has expired"
            )
        if confirmation.status is not ConfirmationStatus.PENDING:
            raise SecurityError(
                f"confirmation {confirmation_id} is already resolved"
            )
        return confirmation
