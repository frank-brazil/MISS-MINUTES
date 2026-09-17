"""Deterministic risk assessment for permission requests.

Risk is derived from the permission category plus a small, explicit set of
heuristics on the action/resource text.  The heuristics never claim to fully
understand natural language: they only **elevate** risk when an obviously
destructive or privileged keyword is seen.  Anything unclassifiable stays at
its category default; a category that is not known at all is reported as
``UNKNOWN`` so policies fail closed.
"""

import re

from app.security.models import PermissionCategory, RiskLevel

#: Default risk for each supported permission category.
_CATEGORY_RISK: dict[PermissionCategory, RiskLevel] = {
    PermissionCategory.READ: RiskLevel.LOW,
    PermissionCategory.WRITE: RiskLevel.MEDIUM,
    PermissionCategory.EXECUTE: RiskLevel.MEDIUM,
    PermissionCategory.BROWSER: RiskLevel.MEDIUM,
    PermissionCategory.NETWORK: RiskLevel.MEDIUM,
    PermissionCategory.SYSTEM: RiskLevel.HIGH,
    PermissionCategory.SENSITIVE: RiskLevel.CRITICAL,
    PermissionCategory.DISTRIBUTED: RiskLevel.MEDIUM,
}

#: Keywords/phrases that elevate risk for irreversible or privileged
#: operations.  Matching is case-insensitive and word-boundary aware so
#: common words like "information" (which contains "format") do not elevate.
_DESTRUCTIVE_WORDS = (
    "delete",
    "remove",
    "overwrite",
    "format",
    "drop table",
    "truncate",
    "wipe",
    "purge",
    "shutdown",
    "reboot",
    "restart",
    "uninstall",
    "escalate",
    "privilege",
    "chmod 777",
    "rm -rf",
    "kill ",
    "terminate",
    "reset password",
    "grant",
    "revoke",
    "exfiltrate",
    "ransomware",
    "backdoor",
)

#: A second tier that pushes MEDIUM-class operations up to HIGH.
_ELEVATE_TO_HIGH = (
    "sudo ",
    "admin",
    "registry",
    "credential",
    "secret",
    "password",
    "token",
    "api key",
)

_DESTRUCTIVE_RE = re.compile(
    r"(?i)\b(" + "|".join(re.escape(word.strip()) for word in _DESTRUCTIVE_WORDS) + r")\b"
)
_ELEVATE_RE = re.compile(
    r"(?i)\b(" + "|".join(re.escape(word.strip()) for word in _ELEVATE_TO_HIGH) + r")\b"
)

_ESCAPE = re.compile(r"[|&;><`$\\]")

#: Rank order used to compare risk levels.
RISK_RANK: dict[RiskLevel, int] = {
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
    RiskLevel.UNKNOWN: 5,
}


def risk_rank(level: RiskLevel) -> int:
    """Return an ordered rank for ``level`` (lower is less risky)."""
    return RISK_RANK.get(level, RISK_RANK[RiskLevel.UNKNOWN])


class RiskAssessor:
    """Assesses the risk class of a permission request deterministically."""

    def __init__(
        self,
        category_overrides: dict[PermissionCategory, RiskLevel] | None = None,
    ) -> None:
        self._overrides = dict(category_overrides or {})

    @property
    def category_overrides(self) -> dict[PermissionCategory, RiskLevel]:
        return dict(self._overrides)

    def assess(
        self,
        *,
        category: PermissionCategory,
        action: str | None = None,
        resource: str | None = None,
    ) -> RiskLevel:
        """Compute the risk class for a category and free-text context."""
        base = self._overrides.get(category) or _CATEGORY_RISK.get(category, RiskLevel.UNKNOWN)
        text = " ".join(part for part in (action, resource) if part is not None)
        if not text:
            return base

        if _ESCAPE.search(text):
            if base is RiskLevel.MEDIUM:
                return RiskLevel.HIGH
            if base is RiskLevel.HIGH:
                return RiskLevel.CRITICAL
            return base

        if _DESTRUCTIVE_RE.search(text):
            if base is RiskLevel.LOW:
                return RiskLevel.MEDIUM
            if base is RiskLevel.MEDIUM:
                return RiskLevel.HIGH
            if base is RiskLevel.HIGH:
                return RiskLevel.CRITICAL
            return base

        if _ELEVATE_RE.search(text):
            if base is RiskLevel.LOW:
                return RiskLevel.MEDIUM
            if base is RiskLevel.MEDIUM:
                return RiskLevel.HIGH
            return base

        return base
