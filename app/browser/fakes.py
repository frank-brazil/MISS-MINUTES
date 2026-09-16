"""Deterministic in-memory fake browser provider.

Used by the test-suite and by local development to exercise the browser
tool layer without a real browser or any network traffic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from app.browser.errors import (
    BrowserActionError,
    BrowserContentError,
    BrowserDownloadError,
    BrowserNavigationError,
    BrowserSessionError,
    BrowserStartupError,
)
from app.browser.models import (
    BrowserClickResult,
    BrowserDownload,
    BrowserNavigation,
    BrowserPageContent,
    BrowserScreenshot,
    BrowserSession,
    BrowserSessionStatus,
    BrowserTypeResult,
    TextEntryAction,
)
from app.browser.provider import BrowserProvider


@dataclass
class _FakePage:
    url: str | None = None
    title: str | None = None
    content: str = ""
    html: str = ""
    elements: dict[str, str] = field(default_factory=dict)
    clicks: list[str] = field(default_factory=list)
    typing: list[dict[str, object]] = field(default_factory=list)


class FakeBrowserProvider(BrowserProvider):
    """An in-memory ``BrowserProvider`` that never touches the network.

    Behaviour is deterministic and fully controlled through the ``seed_page``
    and ``register_download`` helpers and the ``fail_click_on`` set.
    """

    name: ClassVar[str] = "fake-browser"

    def __init__(self, *, fail_start: bool = False) -> None:
        self._fail_start = fail_start
        self._started = False
        self._sessions: dict[str, BrowserSession] = {}
        self._pages: dict[str, _FakePage] = {}
        self._download_registry: dict[str, tuple[bytes, str]] = {}
        self.fail_click_on: set[str] = set()
        self.events: list[str] = []
        self.start_count = 0
        self.stop_count = 0

    # ---------------------------------------------------------- lifecycle

    async def start(self) -> None:
        if self._fail_start:
            raise BrowserStartupError("fake browser failed to start")
        self._started = True
        self.start_count += 1
        self.events.append("start")

    async def stop(self) -> None:
        self._started = False
        self._sessions.clear()
        self._pages.clear()
        self.stop_count += 1
        self.events.append("stop")

    @property
    def started(self) -> bool:
        return self._started

    # ------------------------------------------------------------ sessions

    async def create_session(
        self, *, session_id: str | None = None
    ) -> BrowserSession:
        if not self._started:
            raise BrowserSessionError("browser is not started")
        sid = session_id or f"session-{len(self._sessions) + 1}"
        if sid in self._sessions:
            raise BrowserSessionError(f"session '{sid}' already exists")
        session = BrowserSession.create(sid)
        self._sessions[sid] = session
        self._pages[sid] = _FakePage()
        self.events.append(f"create:{sid}")
        return session

    async def close_session(self, session_id: str) -> None:
        self._require_active(session_id)
        session = self._sessions[session_id]
        session.status = BrowserSessionStatus.CLOSED
        session.updated_at = datetime.now(timezone.utc)
        self._pages.pop(session_id, None)
        self.events.append(f"close:{session_id}")

    def has_session(self, session_id: str) -> bool:
        return session_id in self._sessions

    def sessions(self) -> tuple[BrowserSession, ...]:
        return tuple(
            self._sessions[key]
            for key in sorted(self._sessions)
        )

    # --------------------------------------------------------------- setup

    async def seed_page(
        self,
        *,
        session_id: str = "default",
        url: str = "http://localhost/",
        title: str = "Seeded page",
        content: str = "",
        elements: dict[str, str] | None = None,
    ) -> BrowserSession:
        """Preset a page's observable state (test helper, no network)."""
        if session_id not in self._sessions:
            await self.create_session(session_id=session_id)
        page = self._pages[session_id]
        page.url = url
        page.title = title
        page.content = content
        page.html = content
        if elements:
            page.elements.update(elements)
        session = self._sessions[session_id]
        session.current_url = url
        session.title = title
        session.updated_at = datetime.now(timezone.utc)
        return session

    def register_download(
        self, url: str, data: bytes, filename: str = "download.bin"
    ) -> None:
        """Register fake downloadable content for ``url``."""
        self._download_registry[url] = (data, filename)

    def register_element(self, session_id: str, selector: str, text: str) -> None:
        """Attach a selectable element to a page (test helper)."""
        self._require_active(session_id)
        self._pages[session_id].elements[selector] = text

    # ------------------------------------------------------------- guards

    def _require_active(self, session_id: str) -> BrowserSession:
        if not self._started:
            raise BrowserSessionError("browser is not started")
        session = self._sessions.get(session_id)
        if session is None:
            raise BrowserSessionError(f"unknown session: {session_id}")
        if session.status == BrowserSessionStatus.CLOSED:
            raise BrowserSessionError(f"session '{session_id}' is closed")
        return session

    def _require_page(self, session_id: str) -> _FakePage:
        self._require_active(session_id)
        page = self._pages.get(session_id)
        if page is None:
            raise BrowserSessionError(f"session '{session_id}' has no page")
        return page

    # ------------------------------------------------------ page operations

    async def open_url(self, session_id: str, url: str) -> BrowserNavigation:
        page = self._require_page(session_id)
        session = self._sessions[session_id]
        page.url = url
        page.title = f"Mock title for {url}"
        page.content = f"Mock content for {url}"
        page.html = f"<html><body>Mock content for {url}</body></html>"
        session.current_url = url
        session.title = page.title
        session.updated_at = datetime.now(timezone.utc)
        self.events.append(f"open:{session_id}")
        return BrowserNavigation(session_id=session_id, url=url, status=200)

    async def get_current_url(self, session_id: str) -> str:
        page = self._require_page(session_id)
        if page.url is None:
            raise BrowserNavigationError("no page has been loaded")
        return page.url

    async def get_title(self, session_id: str) -> str | None:
        page = self._require_page(session_id)
        if page.url is None:
            raise BrowserNavigationError("no page has been loaded")
        return page.title

    async def read_content(
        self,
        session_id: str,
        *,
        mode: str = "text",
        selector: str | None = None,
        max_chars: int = 8000,
    ) -> BrowserPageContent:
        page = self._require_page(session_id)
        if page.url is None:
            raise BrowserContentError("no page has been loaded")

        if selector is not None:
            text = page.elements.get(selector)
            if text is None:
                raise BrowserContentError(f"element not found: {selector}")
        elif mode == "html":
            text = page.html or page.content
        elif mode == "text":
            text = page.content
        else:
            raise BrowserContentError(f"unsupported mode: {mode}")

        truncated = False
        if len(text) > max_chars:
            text = text[:max_chars]
            truncated = True

        session = self._sessions[session_id]
        session.updated_at = datetime.now(timezone.utc)
        self.events.append(f"read:{session_id}")
        return BrowserPageContent(
            session_id=session_id,
            content=text,
            truncated=truncated,
            mode=mode,
        )

    async def click(self, session_id: str, selector: str) -> BrowserClickResult:
        page = self._require_page(session_id)
        if selector in self.fail_click_on:
            raise BrowserActionError(f"element not found: {selector}")
        page.clicks.append(selector)
        self._sessions[session_id].updated_at = datetime.now(timezone.utc)
        self.events.append(f"click:{session_id}")
        return BrowserClickResult(session_id=session_id, selector=selector)

    async def type_text(
        self,
        session_id: str,
        selector: str,
        text: str,
        *,
        action: TextEntryAction = TextEntryAction.TYPE,
    ) -> BrowserTypeResult:
        page = self._require_page(session_id)
        page.typing.append(
            {
                "selector": selector,
                "action": action.value,
                "text": text,
                "length": len(text),
            }
        )
        self._sessions[session_id].updated_at = datetime.now(timezone.utc)
        self.events.append(f"type:{session_id}")
        return BrowserTypeResult(
            session_id=session_id,
            selector=selector,
            chars_typed=len(text),
        )

    # ---------------------------------------------------------- media/files

    async def screenshot(
        self, session_id: str, *, path: str | Path
    ) -> BrowserScreenshot:
        self._require_page(session_id)
        destination = Path(path)
        destination.write_bytes(b"fake-png-bytes")
        self.events.append(f"screenshot:{session_id}")
        return BrowserScreenshot(
            session_id=session_id,
            path=destination,
            format="png",
            size_bytes=len(b"fake-png-bytes"),
        )

    async def download(
        self,
        session_id: str,
        url: str,
        *,
        destination: str | Path,
    ) -> BrowserDownload:
        self._require_page(session_id)
        if url not in self._download_registry:
            raise BrowserDownloadError(f"no download available for {url}")
        data, _filename = self._download_registry[url]
        destination_path = Path(destination)
        destination_path.write_bytes(data)
        self._sessions[session_id].updated_at = datetime.now(timezone.utc)
        self.events.append(f"download:{session_id}")
        return BrowserDownload(
            session_id=session_id,
            url=url,
            saved_to=destination_path,
            size_bytes=len(data),
        )
