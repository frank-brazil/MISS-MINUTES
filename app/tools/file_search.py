"""Safe file-search tool with explicit allowed-root enforcement."""

from __future__ import annotations

import fnmatch
import os
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.path_safety import PathSafety, PathSafetyError
from app.core.permissions import ToolPermission
from app.tools.base import Tool, ToolResult
from app.tools.file_config import FileToolConfig


class FileSearchArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    directory: str = Field(description="Directory to search inside")
    pattern: str = Field(
        description="Filename wildcard pattern (e.g. '*.txt', '*.py')"
    )
    recursive: bool = Field(default=True, description="Search subdirectories")
    max_results: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="Maximum number of matches to return",
    )

    @field_validator("pattern")
    @classmethod
    def _pattern_is_plain_filename(cls, value: str) -> str:
        if "/" in value or "\\" in value:
            raise ValueError("pattern must be a filename pattern, not a path")
        if value in (".", ".."):
            raise ValueError("pattern must be a valid filename pattern")
        return value


class FileSearchTool(Tool):
    """Search for files matching a wildcard pattern inside allowed roots.

    Only explicitly configured directories are ever searched.  Path traversal
    outside those directories is rejected at both the argument-validation
    level and an additional per-result safety check.
    """

    name = "file_search"
    description = (
        "Searches for files by wildcard filename pattern inside an explicitly "
        "permitted directory. Returns matching absolute paths."
    )
    input_schema = FileSearchArguments
    permission: ClassVar[ToolPermission] = ToolPermission.READ

    def __init__(self, config: FileToolConfig | None = None) -> None:
        self._config = config or FileToolConfig()
        self._safety = PathSafety(self._config.allowed_roots)

    async def execute(self, **kwargs: object) -> ToolResult:
        args = self.parse_args(**kwargs)

        try:
            root = self._safety.ensure_within(args.directory)
        except PathSafetyError as exc:
            return ToolResult.fail(error=f"Directory not allowed: {exc}")

        if not root.exists():
            return ToolResult.fail(
                error=f"Directory does not exist: {root}"
            )
        if not root.is_dir():
            return ToolResult.fail(error=f"Not a directory: {root}")

        cap = min(self._config.max_search_results, args.max_results)
        matches: list[str] = []

        iterator = root.rglob("*") if args.recursive else root.glob("*")
        try:
            for candidate in iterator:
                if len(matches) >= cap:
                    break
                if not candidate.is_file():
                    continue
                if not fnmatch.fnmatch(candidate.name, args.pattern):
                    continue
                resolved = self._safety.resolve(candidate)
                if not self._safety.within(resolved):
                    continue
                matches.append(os.fspath(resolved))
        except OSError as exc:
            return ToolResult.fail(
                error=f"Search failed: {type(exc).__name__}"
            )

        matches.sort()

        if not matches:
            return ToolResult.ok(
                output=f"No files matched '{args.pattern}' in {root}"
            )

        lines = [f"Found {len(matches)} match(es)", *matches]
        return ToolResult.ok(output="\n".join(lines))
