"""Browser provider abstraction.

Real browser engines (Playwright, etc.) are implemented behind this
interface.  Tools depend only on this ABC plus the typed models, so a fake
in-memory provider can be injected into tests with zero browser installed.

The abstraction deliberately exposes a small, safe surface:

- lifecycle (``start`` / ``stop``)
- sessions (create / close / query)
- page operations (open URL, read content, click, type)
- media/file operations (screenshot reference, explicit download)

No raw browser internals, no arbitrary JavaScript execution, and no
credential/cookie management are exposed to callers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

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


class BrowserProvider(ABC):
    """Interface implemented by fake and real browser back-ends."""

    name: ClassVar[str] = "browser"

    # --- Lifecycle -----------------------------------------------------

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    # --- Sessions ------------------------------------------------------

    @abstractmethod
    async def create_session(
        self, *, session_id: str | None = None
    ) -> BrowserSession:
        raise NotImplementedError

    @abstractmethod
    async def close_session(self, session_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def has_session(self, session_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def sessions(self) -> Sequence[BrowserSession]:
        raise NotImplementedError

    # --- Page operations -----------------------------------------------

    @abstractmethod
    async def open_url(self, session_id: str, url: str) -> BrowserNavigation:
        raise NotImplementedError

    @abstractmethod
    async def get_current_url(self, session_id: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def get_title(self, session_id: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    async def read_content(
        self,
        session_id: str,
        *,
        mode: str = "text",
        selector: str | None = None,
        max_chars: int = 8000,
    ) -> BrowserPageContent:
        raise NotImplementedError

    @abstractmethod
    async def click(self, session_id: str, selector: str) -> BrowserClickResult:
        raise NotImplementedError

    @abstractmethod
    async def type_text(
        self,
        session_id: str,
        selector: str,
        text: str,
        *,
        action: TextEntryAction = TextEntryAction.TYPE,
    ) -> BrowserTypeResult:
        raise NotImplementedError

    # --- Media / files -------------------------------------------------

    @abstractmethod
    async def screenshot(
        self, session_id: str, *, path: str | Path
    ) -> BrowserScreenshot:
        raise NotImplementedError

    @abstractmethod
    async def download(
        self,
        session_id: str,
        url: str,
        *,
        destination: str | Path,
    ) -> BrowserDownload:
        raise NotImplementedError
