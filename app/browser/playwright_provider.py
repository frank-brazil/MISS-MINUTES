"""Playwright-backed browser provider.

Playwright is an optional dependency and is only ever imported inside this
module's methods, so importing this module never requires Playwright to be
installed.  Calling ``start()`` without Playwright (or without a downloaded
browser) raises :class:`BrowserStartupError` with installation guidance.

Installation requirement (documented, not performed by this code):

.. code-block:: bash

    pip install playwright
    playwright install chromium

Tests never exercise this provider: they use :class:`FakeBrowserProvider`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from app.browser.errors import BrowserStartupError, BrowserUnsupportedError
from app.browser.models import (
    BrowserClickResult,
    BrowserDownload,
    BrowserNavigation,
    BrowserPageContent,
    BrowserScreenshot,
    BrowserSession,
    BrowserTypeResult,
    TextEntryAction,
)
from app.browser.provider import BrowserProvider


class PlaywrightBrowserProvider(BrowserProvider):
    """Implements :class:`BrowserProvider` with the Playwright async API.

    One page maps to one browser session.  Cookies are never persisted to
    disk and credentials are never stored or logged.
    """

    name: ClassVar[str] = "playwright"

    _INSTALL_HINT = (
        "Playwright is not installed.  Install it with "
        "'pip install playwright' and run 'playwright install chromium'."
    )

    def __init__(
        self,
        *,
        headless: bool = True,
        browser_type: str = "chromium",
    ) -> None:
        self._headless = headless
        self._browser_type = browser_type
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._pages: dict[str, Any] = {}
        self._sessions: dict[str, BrowserSession] = {}

    # ---------------------------------------------------------- lifecycle

    async def start(self) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise BrowserStartupError(self._INSTALL_HINT) from exc

        self._playwright = await async_playwright().start()
        launcher = getattr(self._playwright, self._browser_type, None)
        if launcher is None:
            raise BrowserUnsupportedError(
                f"Unsupported browser type: {self._browser_type}"
            )
        try:
            self._browser = await launcher.launch(headless=self._headless)
        except Exception as exc:
            raise BrowserStartupError(
                "Failed to launch browser; ensure 'playwright install "
                f"{self._browser_type}' has been run.  ({type(exc).__name__})"
            ) from exc
        self._context = await self._browser.new_context()

    async def stop(self) -> None:
        for session_id in list(self._pages):
            await self.close_session(session_id)
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._context = None
        self._browser = None
        self._playwright = None
        self._pages.clear()
        self._sessions.clear()

    # ------------------------------------------------------------ sessions

    async def create_session(
        self, *, session_id: str | None = None
    ) -> BrowserSession:
        if self._context is None:
            raise BrowserStartupError("browser is not started")
        sid = session_id or f"session-{len(self._sessions) + 1}"
        if sid in self._sessions:
            raise BrowserUnsupportedError(f"session '{sid}' already exists")
        page = await self._context.new_page()
        self._pages[sid] = page
        session = BrowserSession.create(sid)
        self._sessions[sid] = session
        return session

    async def close_session(self, session_id: str) -> None:
        page = self._pages.pop(session_id, None)
        self._sessions.pop(session_id, None)
        if page is not None:
            await page.close()

    def has_session(self, session_id: str) -> bool:
        return session_id in self._pages

    def sessions(self) -> tuple[BrowserSession, ...]:
        return tuple(self._sessions.values())

    # ------------------------------------------------------ page operations

    def _page(self, session_id: str) -> Any:
        page = self._pages.get(session_id)
        if page is None:
            from app.browser.errors import BrowserSessionError

            raise BrowserSessionError(f"unknown session: {session_id}")
        return page

    async def open_url(self, session_id: str, url: str) -> BrowserNavigation:
        from app.browser.errors import BrowserNavigationError

        page = self._page(session_id)
        try:
            response = await page.goto(url)
        except Exception as exc:
            raise BrowserNavigationError(
                f"navigation failed: {type(exc).__name__}"
            ) from exc
        status = response.status if response is not None else None
        current = page.url
        session = self._sessions.get(session_id)
        if session is not None:
            session.current_url = current
        return BrowserNavigation(
            session_id=session_id, url=current, status=status
        )

    async def get_current_url(self, session_id: str) -> str:
        return self._page(session_id).url or ""

    async def get_title(self, session_id: str) -> str | None:
        from app.browser.errors import BrowserContentError

        page = self._page(session_id)
        try:
            title = await page.title()
        except Exception as exc:
            raise BrowserContentError(
                f"failed to read title: {type(exc).__name__}"
            ) from exc
        return title

    async def read_content(
        self,
        session_id: str,
        *,
        mode: str = "text",
        selector: str | None = None,
        max_chars: int = 8000,
    ) -> BrowserPageContent:
        from app.browser.errors import BrowserContentError

        page = self._page(session_id)
        try:
            if mode == "html":
                text = await page.content()
            elif selector is not None:
                text = await page.inner_text(selector)
            else:
                text = await page.inner_text("body")
        except Exception as exc:
            raise BrowserContentError(
                f"failed to read content: {type(exc).__name__}"
            ) from exc

        truncated = False
        if len(text) > max_chars:
            text = text[:max_chars]
            truncated = True

        return BrowserPageContent(
            session_id=session_id,
            content=text,
            truncated=truncated,
            mode=mode,
        )

    async def click(self, session_id: str, selector: str) -> BrowserClickResult:
        from app.browser.errors import BrowserActionError

        page = self._page(session_id)
        try:
            await page.click(selector)
        except Exception as exc:
            raise BrowserActionError(
                f"click failed on '{selector}': {type(exc).__name__}"
            ) from exc
        return BrowserClickResult(session_id=session_id, selector=selector)

    async def type_text(
        self,
        session_id: str,
        selector: str,
        text: str,
        *,
        action: TextEntryAction = TextEntryAction.TYPE,
    ) -> BrowserTypeResult:
        from app.browser.errors import BrowserActionError

        page = self._page(session_id)
        try:
            if action == TextEntryAction.CLEAR:
                await page.fill(selector, "")
                chars_typed = 0
            elif action == TextEntryAction.REPLACE:
                await page.fill(selector, text)
                chars_typed = len(text)
            else:
                await page.fill(selector, text)
                chars_typed = len(text)
        except Exception as exc:
            raise BrowserActionError(
                f"type failed on '{selector}': {type(exc).__name__}"
            ) from exc
        return BrowserTypeResult(
            session_id=session_id,
            selector=selector,
            chars_typed=chars_typed,
        )

    # ---------------------------------------------------------- media/files

    async def screenshot(
        self, session_id: str, *, path: str | Path
    ) -> BrowserScreenshot:
        from app.browser.errors import BrowserContentError

        page = self._page(session_id)
        destination = Path(path)
        try:
            await page.screenshot(path=str(destination))
        except Exception as exc:
            raise BrowserContentError(
                f"screenshot failed: {type(exc).__name__}"
            ) from exc
        size = destination.stat().st_size if destination.exists() else None
        return BrowserScreenshot(
            session_id=session_id,
            path=destination,
            format=destination.suffix.lstrip(".") or "png",
            size_bytes=size,
        )

    async def download(
        self,
        session_id: str,
        url: str,
        *,
        destination: str | Path,
    ) -> BrowserDownload:
        import asyncio
        import os

        from app.browser.errors import BrowserDownloadError

        page = self._page(session_id)
        destination_path = Path(destination)
        try:
            async with page.expect_download() as download_info:
                await page.goto(url)
            download = await download_info.value
            await download.save_as(str(destination_path))
        except Exception as exc:
            raise BrowserDownloadError(
                f"download failed: {type(exc).__name__}"
            ) from exc
        size = await asyncio.to_thread(os.path.getsize, destination_path)
        return BrowserDownload(
            session_id=session_id,
            url=url,
            saved_to=destination_path,
            size_bytes=size,
        )
