"""Browser error hierarchy.

All browser failures ultimately surface as controlled ``ToolResult`` failures.
Tooling catches the subclasses below and converts them to safe messages.
"""


class BrowserError(Exception):
    """Base class for all browser-layer failures."""


class BrowserStartupError(BrowserError):
    """Raised when the browser provider cannot start."""


class BrowserUnsupportedError(BrowserError):
    """Raised when an environment cannot support the requested operation."""


class BrowserSessionError(BrowserError):
    """Raised for unknown, closed or improperly used sessions."""


class BrowserNavigationError(BrowserError):
    """Raised when navigation or page access fails."""


class BrowserContentError(BrowserError):
    """Raised when page content cannot be read or extracted."""


class BrowserActionError(BrowserError):
    """Raised when an in-page action (click/type) fails."""


class BrowserDownloadError(BrowserError):
    """Raised when a download fails or is unsafe."""