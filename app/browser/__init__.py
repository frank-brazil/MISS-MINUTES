"""Safe browser automation foundation for MISSMINUTES.

Browser operations are exposed through the existing ``Tool`` abstraction and
are backed by an injectable :class:`BrowserProvider`.  Page content is always
treated as untrusted data and never auto-executed.
"""

from app.browser.errors import (
    BrowserContentError,
    BrowserDownloadError,
    BrowserError,
    BrowserNavigationError,
    BrowserSessionError,
    BrowserStartupError,
    BrowserUnsupportedError,
)
from app.browser.fakes import FakeBrowserProvider
from app.browser.models import (
    BrowserActionResult,
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
from app.browser.playwright_provider import PlaywrightBrowserProvider
from app.browser.policy import UrlPolicy, UrlValidationError
from app.browser.provider import BrowserProvider
from app.browser.tools import (
    BrowserClickArguments,
    BrowserClickTool,
    BrowserDownloadArguments,
    BrowserDownloadTool,
    BrowserOpenArguments,
    BrowserOpenTool,
    BrowserReadArguments,
    BrowserReadTool,
    BrowserToolBundle,
    BrowserToolContext,
    BrowserTypeArguments,
    BrowserTypeTool,
    ReadMode,
)

__all__ = [
    "BrowserActionResult",
    "BrowserClickArguments",
    "BrowserClickResult",
    "BrowserClickTool",
    "BrowserContentError",
    "BrowserDownload",
    "BrowserDownloadArguments",
    "BrowserDownloadError",
    "BrowserDownloadTool",
    "BrowserError",
    "BrowserNavigation",
    "BrowserNavigationError",
    "BrowserOpenArguments",
    "BrowserOpenTool",
    "BrowserPageContent",
    "BrowserProvider",
    "BrowserReadArguments",
    "BrowserReadTool",
    "BrowserSession",
    "BrowserSessionError",
    "BrowserSessionStatus",
    "BrowserScreenshot",
    "BrowserStartupError",
    "BrowserToolBundle",
    "BrowserToolContext",
    "BrowserTypeArguments",
    "BrowserTypeResult",
    "BrowserTypeTool",
    "BrowserUnsupportedError",
    "FakeBrowserProvider",
    "PlaywrightBrowserProvider",
    "ReadMode",
    "TextEntryAction",
    "UrlPolicy",
    "UrlValidationError",
]
