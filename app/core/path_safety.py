"""Reusable path-safety utilities for computer-interaction tools.

All file-based tools funnel their path arguments through :class:`PathSafety`
so that:

- paths are normalized and resolved to absolute form;
- only paths that resolve *inside* an explicitly configured allowed root are
  accepted;
- ``..`` traversal, absolute-path escapes and `drive-letter` mismatch are
  rejected;
- behaviour is correct on Windows (case-insensitive containment, both ``/``
  and ``\\`` separators).

The safety policy is **fail closed**: an empty allow-list rejects everything.
"""

import os
from collections.abc import Iterable
from pathlib import Path


class PathSafetyError(Exception):
    """Raised when a path is not safely contained within an allowed root."""


def resolve_path(path: str | os.PathLike[str]) -> Path:
    """Return an absolute, normalized, resolved form of ``path``.

    Tilde expansion is applied, ``..`` segments are collapsed, and symlinks
    are resolved for the existing portion of the path.  Non-existent paths
    are normalised but never raise.
    """
    expanded = Path(os.path.expanduser(os.fspath(path)))
    return expanded.absolute().resolve(strict=False)


def _normcase(value: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.normpath(os.fspath(value)))


def is_within_root(
    path: str | os.PathLike[str], root: str | os.PathLike[str]
) -> bool:
    """Return True when ``path`` resolves inside ``root``.

    Resolution and case normalisation are applied to both sides before the
    containment check, so ``C:\\Work\\Sub`` is inside ``c:\\work`` on Windows
    while ``C:\\Worker`` is not.
    """
    resolved_path = _normcase(resolve_path(path))
    resolved_root = _normcase(resolve_path(root))
    try:
        common = _normcase(os.path.commonpath([resolved_root, resolved_path]))
    except ValueError:
        return False
    if common != resolved_root:
        return False
    return True


class PathSafety:
    """Containment guard over a configured set of allowed root directories.

    Parameters
    ----------
    allowed_roots : iterable of path-like
        Every root is resolved to an absolute path and de-duplicated.  A path
        is permitted only when it resolves under at least one allowed root.
    """

    def __init__(
        self, allowed_roots: Iterable[str | os.PathLike[str]] = ()
    ) -> None:
        resolved: dict[str, Path] = {}
        for root in allowed_roots:
            absolute = resolve_path(root)
            resolved[_normcase(absolute)] = absolute
        self._roots: tuple[Path, ...] = tuple(
            resolved[k] for k in sorted(resolved)
        )

    @property
    def roots(self) -> tuple[Path, ...]:
        """The resolved, de-duplicated allowed roots."""
        return self._roots

    def resolve(self, path: str | os.PathLike[str]) -> Path:
        """Return the resolved absolute form of ``path``."""
        return resolve_path(path)

    def within(self, path: str | os.PathLike[str]) -> bool:
        """Return True when ``path`` resolves under an allowed root."""
        resolved = self.resolve(path)
        return any(is_within_root(resolved, root) for root in self._roots)

    def ensure_within(
        self, path: str | os.PathLike[str]
    ) -> Path:
        """Resolve ``path`` and raise :class:`PathSafetyError` if unsafe."""
        resolved = self.resolve(path)
        if not self.within(resolved):
            raise PathSafetyError(
                f"path '{os.fspath(path)}' is outside the allowed roots"
            )
        return resolved