"""Secret-value redaction helpers for audit and confirmation records.

These helpers are **heuristic**, not a formal guarantee: they scrub values
that look like API keys, bearer tokens, passwords and generic secrets so that
metadata never carries obvious credential material.  They are intentionally
conservative and never claim to catch every possible secret format.
"""

import re
from typing import Any

_REDACTED = "[REDACTED]"

_SECRET_KEY_WORDS = (
    "api[_-]?key",
    "authorization",
    "apikey",
    "access[_-]?token",
    "refresh[_-]?token",
    "auth[_-]?token",
    "token",
    "password",
    "passwd",
    "secret",
    "client[_-]?secret",
    "credential",
    "jwt",
    "cookie",
    "session[_-]?token",
    "private[_-]?key",
)

_SECRET_KEY_RE = re.compile(
    r"^[A-Za-z0-9._-]*(?:" + "|".join(_SECRET_KEY_WORDS) + r")[A-Za-z0-9._-]*$",
    flags=re.IGNORECASE,
)

_AUTH_VALUE_RE = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/= -]{8,}\b")

_KEY_VALUE_RE = re.compile(r"(?i)\b(" + "|".join(_SECRET_KEY_WORDS) + r")\s*([=:])\s*\S+")


def _redact_auth(match: re.Match[str]) -> str:
    return f"{match.group(1)} {_REDACTED}"


def _redact_kv(match: re.Match[str]) -> str:
    return f"{match.group(1)}{match.group(2)}{_REDACTED}"


def redact_string(value: str) -> str:
    """Return ``value`` with credential-looking fragments replaced.

    ``"Bearer abc123"`` becomes ``"Bearer [REDACTED]"`` and
    ``"password=hunter2"`` becomes ``"password=[REDACTED]"``.  Plain text is
    returned unchanged.
    """
    if not value:
        return value
    redacted = _AUTH_VALUE_RE.sub(_redact_auth, value)
    return _KEY_VALUE_RE.sub(_redact_kv, redacted)


def _is_secret_key(key: str) -> bool:
    return _SECRET_KEY_RE.match(key) is not None


def redact_mapping(value: dict[Any, Any]) -> dict[Any, Any]:
    """Return a deep copy of ``value`` with secret-looking values scrubbed."""
    result: dict[Any, Any] = {}
    for key, item in value.items():
        if isinstance(key, str) and _is_secret_key(key):
            result[key] = _REDACTED
            continue
        result[key] = redact_value(item)
    return result


def redact_value(value: Any) -> Any:
    """Recursively redact secret-looking content within ``value``."""
    if isinstance(value, dict):
        return redact_mapping(value)
    if isinstance(value, (list, tuple)):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_string(value)
    return value


def redact(value: Any) -> Any:
    """Alias for :func:`redact_value`."""
    return redact_value(value)


def is_redacted(value: Any) -> bool:
    """Return True when ``value`` (or any part of it) was redacted."""
    if isinstance(value, dict):
        return any(item == _REDACTED or is_redacted(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(is_redacted(item) for item in value)
    return value == _REDACTED or (isinstance(value, str) and _REDACTED in value)


REDACTED = _REDACTED
