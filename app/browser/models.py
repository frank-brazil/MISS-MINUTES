"""Typed models shared by every browser provider and tool.

These models deliberately contain *safe metadata only*.  They never carry
credentials, cookies, authorization headers or raw secrets.  They are used
as the contract between the provider abstraction and the tool layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BrowserSessionStatus(StrEnum):
    """Lifecycle state of a browser session."""

    ACTIVE = "active"
    CLOSED = "closed"


class TextEntryAction(StrEnum):
    """Explicit, structured text-entry action for typing into fields."""

    TYPE = "type"
    REPLACE = "replace"
    CLEAR = "clear"


class BrowserSession(BaseModel):
    """Tracks one browser session's safe, non-sensitive metadata."""

    session_id: str
    status: BrowserSessionStatus = BrowserSessionStatus.ACTIVE
    current_url: str | None = None
    title: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @classmethod
    def create(cls, session_id: str) -> "BrowserSession":
        now = _utcnow()
        return cls(
            session_id=session_id,
            created_at=now,
            updated_at=now,
        )


class BrowserPageContent(BaseModel):
    """Page content returned to the tool layer as untrusted text."""

    session_id: str
    content: str
    truncated: bool = False
    mode: str = "text"


class BrowserNavigation(BaseModel):
    """Result of a page navigation."""

    session_id: str
    url: str
    status: int | None = None


class BrowserActionResult(BaseModel):
    """Result of an in-page action such as a click."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    ok: bool = True


class BrowserClickResult(BrowserActionResult):
    selector: str


class BrowserTypeResult(BrowserActionResult):
    selector: str
    chars_typed: int


class BrowserScreenshot(BaseModel):
    """Reference to a captured screenshot.  Never carries pixel data."""

    session_id: str
    path: Path
    format: str = "png"
    size_bytes: int | None = None


class BrowserDownload(BaseModel):
    """Safe metadata describing a completed download."""

    session_id: str
    url: str
    saved_to: Path
    size_bytes: int | None = None