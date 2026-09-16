import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.permissions import ToolPermission
from app.tools.base import ToolResult
from app.tools.file_config import FileToolConfig
from app.tools.file_create import FileCreateTool
from app.tools.file_edit import FileEditTool
from app.tools.file_read import FileReadTool
from app.tools.file_search import FileSearchTool


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    return tmp_path / "work"


@pytest.fixture
def config(workdir: Path) -> FileToolConfig:
    workdir.mkdir()
    return FileToolConfig(allowed_roots=(workdir,))


def test_file_tools_declare_permission(config: FileToolConfig) -> None:
    assert FileSearchTool.permission == ToolPermission.READ
    assert FileReadTool.permission == ToolPermission.READ
    assert FileCreateTool.permission == ToolPermission.WRITE
    assert FileEditTool.permission == ToolPermission.WRITE


# ------------------------------------------------------------------
# File search
# ------------------------------------------------------------------


def test_file_search_finds_matching_files(config: FileToolConfig, workdir: Path) -> None:
    (workdir / "a.txt").write_text("a", encoding="utf-8")
    (workdir / "b.txt").write_text("b", encoding="utf-8")
    (workdir / "sub").mkdir()
    (workdir / "sub" / "c.txt").write_text("c", encoding="utf-8")
    (workdir / "note.md").write_text("n", encoding="utf-8")

    tool = FileSearchTool(config)
    result = asyncio.run(tool.execute(directory=str(workdir), pattern="*.txt"))
    assert result.success is True

    lines = (result.output or "").splitlines()
    assert lines[0] == "Found 3 match(es)"
    matches = set(lines[1:])
    assert matches == {
        str((workdir / "a.txt").resolve()),
        str((workdir / "b.txt").resolve()),
        str((workdir / "sub" / "c.txt").resolve()),
    }


def test_file_search_non_recursive(config: FileToolConfig, workdir: Path) -> None:
    (workdir / "a.txt").write_text("a", encoding="utf-8")
    (workdir / "sub").mkdir()
    (workdir / "sub" / "c.txt").write_text("c", encoding="utf-8")

    tool = FileSearchTool(config)
    result = asyncio.run(
        tool.execute(directory=str(workdir), pattern="*.txt", recursive=False)
    )
    lines = (result.output or "").splitlines()
    assert lines[0] == "Found 1 match(es)"
    assert str((workdir / "a.txt").resolve()) in lines[1:]


def test_file_search_no_matches(config: FileToolConfig, workdir: Path) -> None:
    (workdir / "a.log").write_text("a", encoding="utf-8")
    tool = FileSearchTool(config)
    result = asyncio.run(tool.execute(directory=str(workdir), pattern="*.txt"))
    assert result.success is True
    assert "No files matched" in (result.output or "")


def test_file_search_result_limit(config: FileToolConfig, workdir: Path) -> None:
    for index in range(5):
        (workdir / f"file{index}.txt").write_text("x", encoding="utf-8")
    tool = FileSearchTool(config)
    result = asyncio.run(
        tool.execute(directory=str(workdir), pattern="*.txt", max_results=2)
    )
    lines = (result.output or "").splitlines()
    assert lines[0] == "Found 2 match(es)"


def test_file_search_config_cap_wins(config: FileToolConfig, workdir: Path) -> None:
    for index in range(5):
        (workdir / f"file{index}.txt").write_text("x", encoding="utf-8")
    capped = FileToolConfig(allowed_roots=config.allowed_roots, max_search_results=1)
    tool = FileSearchTool(capped)
    result = asyncio.run(
        tool.execute(directory=str(workdir), pattern="*.txt", max_results=10)
    )
    lines = (result.output or "").splitlines()
    assert lines[0] == "Found 1 match(es)"


def test_file_search_nonexistent_directory(config: FileToolConfig, workdir: Path) -> None:
    tool = FileSearchTool(config)
    result = asyncio.run(
        tool.execute(directory=str(workdir / "missing"), pattern="*.txt")
    )
    assert result.success is False
    assert "does not exist" in (result.error or "")


def test_file_search_directory_outside_root(config: FileToolConfig, workdir: Path) -> None:
    outside = workdir.parent / "outside"
    outside.mkdir()
    tool = FileSearchTool(config)
    result = asyncio.run(tool.execute(directory=str(outside), pattern="*"))
    assert result.success is False
    assert "not allowed" in (result.error or "")


def test_file_search_traversal_rejected(config: FileToolConfig, workdir: Path) -> None:
    tool = FileSearchTool(config)
    escaped = str(workdir / ".." / ".." / "secret")
    result = asyncio.run(tool.execute(directory=escaped, pattern="*"))
    assert result.success is False
    assert "not allowed" in (result.error or "")


def test_file_search_pattern_with_separator_rejected(
    config: FileToolConfig, workdir: Path
) -> None:
    tool = FileSearchTool(config)
    with pytest.raises(ValidationError):
        asyncio.run(
            tool.execute(directory=str(workdir), pattern="sub/*.txt")
        )


def test_file_search_no_allowed_roots_fails_closed() -> None:
    tool = FileSearchTool()
    result = asyncio.run(
        tool.execute(directory=str(Path.cwd()), pattern="*")
    )
    assert result.success is False
    assert "not allowed" in (result.error or "")


def test_file_search_returns_deterministic_order(
    config: FileToolConfig, workdir: Path
) -> None:
    (workdir / "b.txt").write_text("b", encoding="utf-8")
    (workdir / "a.txt").write_text("a", encoding="utf-8")
    tool = FileSearchTool(config)
    result = asyncio.run(tool.execute(directory=str(workdir), pattern="*.txt"))
    lines = (result.output or "").splitlines()
    assert lines[1] < lines[2]


# ------------------------------------------------------------------
# File read
# ------------------------------------------------------------------


def test_file_read_success(config: FileToolConfig, workdir: Path) -> None:
    target = workdir / "notes.txt"
    target.write_text("hello world", encoding="utf-8")
    tool = FileReadTool(config)
    result = asyncio.run(tool.execute(path=str(target)))
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.output == "hello world"


def test_file_read_missing_file(config: FileToolConfig, workdir: Path) -> None:
    tool = FileReadTool(config)
    result = asyncio.run(tool.execute(path=str(workdir / "nope.txt")))
    assert result.success is False
    assert "does not exist" in (result.error or "")


def test_file_read_directory_rejected(config: FileToolConfig, workdir: Path) -> None:
    directory = workdir / "adir"
    directory.mkdir()
    tool = FileReadTool(config)
    result = asyncio.run(tool.execute(path=str(directory)))
    assert result.success is False
    assert "Not a regular file" in (result.error or "")


def test_file_read_traversal_rejected(config: FileToolConfig, workdir: Path) -> None:
    outside = workdir.parent / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    tool = FileReadTool(config)
    result = asyncio.run(
        tool.execute(path=str(workdir / ".." / outside.name))
    )
    assert result.success is False
    assert "not allowed" in (result.error or "")


def test_file_read_size_limit(config: FileToolConfig, workdir: Path) -> None:
    target = workdir / "big.txt"
    target.write_text("x" * 200, encoding="utf-8")
    small = FileToolConfig(allowed_roots=config.allowed_roots, read_max_bytes=100)
    tool = FileReadTool(small)
    result = asyncio.run(tool.execute(path=str(target)))
    assert result.success is False
    assert "exceeds maximum readable size" in (result.error or "")


def test_file_read_non_utf8_rejected(config: FileToolConfig, workdir: Path) -> None:
    target = workdir / "binary.bin"
    target.write_bytes(b"\xff\xfe\x00\x01")
    tool = FileReadTool(config)
    result = asyncio.run(tool.execute(path=str(target)))
    assert result.success is False
    assert "not valid UTF-8" in (result.error or "")


def test_file_read_callable_max_bytes_override(
    config: FileToolConfig, workdir: Path
) -> None:
    target = workdir / "medium.txt"
    target.write_text("x" * 150, encoding="utf-8")
    tool = FileReadTool(config)
    result = asyncio.run(
        tool.execute(path=str(target), max_bytes=1000)
    )
    assert result.success is True


# ------------------------------------------------------------------
# File create
# ------------------------------------------------------------------


def test_file_create_success(config: FileToolConfig, workdir: Path) -> None:
    tool = FileCreateTool(config)
    result = asyncio.run(
        tool.execute(path=str(workdir / "new.txt"), content="created!")
    )
    assert result.success is True
    target = workdir / "new.txt"
    assert target.read_text(encoding="utf-8") == "created!"
    assert str(target) in (result.output or "")
    assert "bytes" in (result.output or "")


def test_file_create_default_content(config: FileToolConfig, workdir: Path) -> None:
    tool = FileCreateTool(config)
    result = asyncio.run(tool.execute(path=str(workdir / "empty.txt")))
    assert result.success is True
    assert (workdir / "empty.txt").read_text(encoding="utf-8") == ""


def test_file_create_refuses_overwrite_by_default(
    config: FileToolConfig, workdir: Path
) -> None:
    target = workdir / "existing.txt"
    target.write_text("original", encoding="utf-8")
    tool = FileCreateTool(config)
    result = asyncio.run(
        tool.execute(path=str(target), content="overwritten")
    )
    assert result.success is False
    assert "already exists" in (result.error or "")
    assert target.read_text(encoding="utf-8") == "original"


def test_file_create_overwrite_explicit(
    config: FileToolConfig, workdir: Path
) -> None:
    target = workdir / "existing.txt"
    target.write_text("original", encoding="utf-8")
    tool = FileCreateTool(config)
    result = asyncio.run(
        tool.execute(path=str(target), content="replaced", overwrite=True)
    )
    assert result.success is True
    assert target.read_text(encoding="utf-8") == "replaced"


def test_file_create_missing_parent(config: FileToolConfig, workdir: Path) -> None:
    tool = FileCreateTool(config)
    result = asyncio.run(
        tool.execute(path=str(workdir / "no" / "dir" / "f.txt"))
    )
    assert result.success is False
    assert "Parent directory does not exist" in (result.error or "")


def test_file_create_traversal_rejected(config: FileToolConfig, workdir: Path) -> None:
    tool = FileCreateTool(config)
    result = asyncio.run(
        tool.execute(path=str(workdir / ".." / "evil.txt"), content="x")
    )
    assert result.success is False
    assert "not allowed" in (result.error or "")


def test_file_create_size_limit(config: FileToolConfig, workdir: Path) -> None:
    small = FileToolConfig(allowed_roots=config.allowed_roots, write_max_bytes=10)
    tool = FileCreateTool(small)
    result = asyncio.run(
        tool.execute(path=str(workdir / "huge.txt"), content="x" * 50)
    )
    assert result.success is False
    assert "exceeds maximum write size" in (result.error or "")


def test_file_create_nested_existing_dir(config: FileToolConfig, workdir: Path) -> None:
    nested = workdir / "a" / "b"
    nested.mkdir(parents=True)
    tool = FileCreateTool(config)
    result = asyncio.run(
        tool.execute(path=str(nested / "f.txt"), content="deep")
    )
    assert result.success is True
    assert (nested / "f.txt").read_text(encoding="utf-8") == "deep"


# ------------------------------------------------------------------
# File edit
# ------------------------------------------------------------------


def test_file_edit_success(config: FileToolConfig, workdir: Path) -> None:
    target = workdir / "doc.txt"
    target.write_text("the quick brown fox", encoding="utf-8")
    tool = FileEditTool(config)
    result = asyncio.run(
        tool.execute(
            path=str(target), old_text="brown fox", new_text="red hare"
        )
    )
    assert result.success is True
    assert "1 replacement(s)" in (result.output or "")
    assert target.read_text(encoding="utf-8") == "the quick red hare"


def test_file_edit_target_not_found(config: FileToolConfig, workdir: Path) -> None:
    target = workdir / "doc.txt"
    target.write_text("hello", encoding="utf-8")
    tool = FileEditTool(config)
    result = asyncio.run(
        tool.execute(path=str(target), old_text="missing", new_text="x")
    )
    assert result.success is False
    assert "Target text not found" in (result.error or "")


def test_file_edit_ambiguous_replacement_refused(
    config: FileToolConfig, workdir: Path
) -> None:
    target = workdir / "doc.txt"
    target.write_text("one two one three one", encoding="utf-8")
    tool = FileEditTool(config)
    result = asyncio.run(
        tool.execute(path=str(target), old_text="one", new_text="ONE")
    )
    assert result.success is False
    assert "ambiguous" in (result.error or "")
    assert target.read_text(encoding="utf-8") == "one two one three one"


def test_file_edit_replace_all(config: FileToolConfig, workdir: Path) -> None:
    target = workdir / "doc.txt"
    target.write_text("one two one three one", encoding="utf-8")
    tool = FileEditTool(config)
    result = asyncio.run(
        tool.execute(
            path=str(target), old_text="one", new_text="ONE", replace_all=True
        )
    )
    assert result.success is True
    assert "3 replacement(s)" in (result.output or "")
    assert target.read_text(encoding="utf-8") == "ONE two ONE three ONE"


def test_file_edit_single_occurrence_not_ambiguous(
    config: FileToolConfig, workdir: Path
) -> None:
    target = workdir / "doc.txt"
    target.write_text("apple banana apple", encoding="utf-8")
    tool = FileEditTool(config)
    result = asyncio.run(
        tool.execute(path=str(target), old_text="banana", new_text="cherry")
    )
    assert result.success is True
    assert target.read_text(encoding="utf-8") == "apple cherry apple"


def test_file_edit_size_limit(config: FileToolConfig, workdir: Path) -> None:
    big_config = FileToolConfig(allowed_roots=config.allowed_roots, write_max_bytes=20_000)
    create = FileCreateTool(big_config)
    target = workdir / "big.txt"
    content = "word " * 3000
    created = asyncio.run(create.execute(path=str(target), content=content))
    assert created.success is True, created.error

    small = FileToolConfig(allowed_roots=config.allowed_roots, write_max_bytes=2_000)
    tool = FileEditTool(small)
    result = asyncio.run(
        tool.execute(path=str(target), old_text="word", new_text="term")
    )
    assert result.success is False
    assert "exceeds maximum writable size" in (result.error or "")


def test_file_edit_traversal_rejected(config: FileToolConfig, workdir: Path) -> None:
    outside = workdir.parent / "doc.txt"
    outside.write_text("secret", encoding="utf-8")
    tool = FileEditTool(config)
    result = asyncio.run(
        tool.execute(
            path=str(workdir / ".." / "doc.txt"),
            old_text="secret",
            new_text="X",
        )
    )
    assert result.success is False
    assert "not allowed" in (result.error or "")


def test_file_edit_missing_file(config: FileToolConfig, workdir: Path) -> None:
    tool = FileEditTool(config)
    result = asyncio.run(
        tool.execute(
            path=str(workdir / "absent.txt"), old_text="a", new_text="b"
        )
    )
    assert result.success is False
    assert "does not exist" in (result.error or "")


def test_file_edit_empty_old_text_rejected(
    config: FileToolConfig, workdir: Path
) -> None:
    tool = FileEditTool(config)
    with pytest.raises(ValidationError):
        asyncio.run(
            tool.execute(
                path=str(workdir / "doc.txt"), old_text="", new_text="x"
            )
        )