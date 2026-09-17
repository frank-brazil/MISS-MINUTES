import os
import sys
from pathlib import Path

import pytest

from app.core.path_safety import (
    PathSafety,
    PathSafetyError,
    is_within_root,
    resolve_path,
)


@pytest.fixture
def allowed(tmp_path: Path) -> Path:
    return tmp_path / "allowed"


@pytest.fixture
def surrounding(tmp_path: Path) -> Path:
    return tmp_path / "surrounding"


def test_resolve_path_returns_absolute(tmp_path: Path) -> None:
    target = tmp_path / "notes" / "a.txt"
    resolved = resolve_path(target)
    assert isinstance(resolved, Path)
    assert resolved.is_absolute()
    assert not resolved.exists()
    assert resolved == tmp_path / "notes" / "a.txt"


def test_resolve_path_normalizes_parent_segments(tmp_path: Path) -> None:
    path = tmp_path / "a" / ".." / "b" / "c.txt"
    resolved = resolve_path(path)
    assert resolved == tmp_path / "b" / "c.txt"


def test_is_within_root_subdirectory(tmp_path: Path) -> None:
    root = tmp_path / "root"
    inside = root / "docs" / "file.txt"
    assert is_within_root(inside, root) is True


def test_is_within_root_exact_equal(tmp_path: Path) -> None:
    root = tmp_path / "root"
    assert is_within_root(root, root) is True


def test_is_within_root_outside_sibling(tmp_path: Path) -> None:
    root = tmp_path / "root"
    sibling = tmp_path / "root2" / "file.txt"
    assert is_within_root(sibling, root) is False


def test_is_within_root_prefix_collision_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data"
    decoy = tmp_path / "database" / "file.txt"
    assert is_within_root(decoy, root) is False


def test_traversal_outside_root_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    traversal = root / ".." / "secret.txt"
    assert is_within_root(traversal, root) is False


def test_absolute_path_escape_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    system32 = Path(os.environ.get("WINDIR", "/")) / "System32" / "x"
    assert is_within_root(system32, root) is False


def test_path_safety_empty_roots_fail_closed(tmp_path: Path) -> None:
    safety = PathSafety()
    assert safety.roots == ()
    assert safety.within(tmp_path) is False
    with pytest.raises(PathSafetyError):
        safety.ensure_within(tmp_path / "x")


def test_path_safety_constructed_without_roots_allows_nothing() -> None:
    safety = PathSafety([])
    assert safety.within("C:\\anything") is False


def test_path_safety_roots_are_absolute_and_deduplicated(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    cwd_relative = os.path.relpath(root, Path.cwd())
    safety = PathSafety([root, root, cwd_relative])
    assert len(safety.roots) == 1
    assert safety.roots[0] == resolve_path(root)


def test_path_safety_ensure_within_returns_resolved(tmp_path: Path) -> None:
    safety = PathSafety([tmp_path])
    inside = tmp_path / "sub" / ".." / "file.txt"
    resolved = safety.ensure_within(inside)
    assert resolved == tmp_path / "file.txt"


def test_path_safety_within_nonexistent_deep_path(tmp_path: Path) -> None:
    safety = PathSafety([tmp_path])
    deep = tmp_path / "not" / "yet" / "created.txt"
    assert safety.within(deep) is True


def test_path_safety_multiple_roots() -> None:
    safety = PathSafety([r"C:\\one", r"C:\\two"])
    assert len(safety.roots) == 2


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_windows_case_insensitive_containment(tmp_path: Path) -> None:
    root = tmp_path / "Root"
    inside = tmp_path / "root" / "sub" / "f.txt"
    assert is_within_root(inside, root) is True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_windows_different_drive_rejected() -> None:
    root = "C:\\Work"
    assert is_within_root("D:\\Work\\file.txt", root) is False


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_windows_forward_slash_traversal_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    raw = f"{root}/sub/../../../escape.txt"
    assert is_within_root(raw, root) is False
