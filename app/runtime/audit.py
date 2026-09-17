"""Safe end-to-end audit trail for the MISSMINUTES runtime.

Tracks metadata about each request through its lifecycle. Never logs
secrets, API keys, passwords, raw audio, raw screenshots, or hidden
chain-of-thought.
"""

from __future__ import annotations

import time
from collections import deque

from pydantic import BaseModel


class AuditEntry(BaseModel):
    """One audit event in the request lifecycle."""

    request_id: str
    stage: str
    timestamp: float
    detail: str | None = None
    success: bool | None = None


class RequestAuditTrail:
    """Bounded, append-only audit log for request lifecycle events."""

    def __init__(self, max_entries: int = 1000) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._entries: deque[AuditEntry] = deque(maxlen=max_entries)

    def record(
        self,
        request_id: str,
        stage: str,
        *,
        detail: str | None = None,
        success: bool | None = None,
        now: float | None = None,
    ) -> AuditEntry:
        """Record an audit event for a request stage."""
        entry = AuditEntry(
            request_id=request_id,
            stage=stage,
            timestamp=now if now is not None else time.time(),
            detail=detail,
            success=success,
        )
        self._entries.append(entry)
        return entry

    def entries_for(self, request_id: str) -> list[AuditEntry]:
        """Return all audit entries for a given request (in order)."""
        return [e for e in self._entries if e.request_id == request_id]

    def all_entries(self) -> tuple[AuditEntry, ...]:
        """Return all audit entries in order."""
        return tuple(self._entries)

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
