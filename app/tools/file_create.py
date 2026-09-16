"""Safe file-creation tool with overwrite protection."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.path_safety import PathSafetyError, PathSafety
from app.core.permissions import ToolPermission
from app.tools.base import Tool, ToolResult
from app.tools.file_config import FileToolConfig


class FileCreateArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Absolute path of the file to create")
    content: str = Field(
        default="", description="Text content to write to the file"
    )
    overwrite: bool = Field(
        default=False,
        description=(
            "When True, an existing file may be replaced.  The default is "
            "False, protecting existing files."
        ),
    )


class FileCreateTool(Tool):
    """Create a text file inside an explicitly allowed writable directory.

    Existing files are never modified unless the caller explicitly passes
    ``overwrite=True``.  Content is size-limited and path traversal outside
    the allowed roots is rejected.
    """

    name = "file_create"
    description = (
        "Creates a text file inside an explicitly permitted directory.  "
        "Refuses to overwrite existing files unless overwrite=True."
    )
    input_schema = FileCreateArguments
    permission: ClassVar[ToolPermission] = ToolPermission.WRITE

    def __init__(self, config: FileToolConfig | None = None) -> None:
        self._config = config or FileToolConfig()
        self._safety = PathSafety(self._config.allowed_roots)

    async def execute(self, **kwargs: object) -> ToolResult:
        args = self.parse_args(**kwargs)

        try:
            resolved = self._safety.ensure_within(args.path)
        except PathSafetyError as exc:
            return ToolResult.fail(error=f"Path not allowed: {exc}")

        if resolved.exists():
            if not args.overwrite:
                return ToolResult.fail(
                    error=f"File already exists: {resolved}"
                )
            if not resolved.is_file():
                return ToolResult.fail(
                    error=f"Not a regular file: {resolved}"
                )

        parent = resolved.parent
        if not parent.exists():
            return ToolResult.fail(
                error=f"Parent directory does not exist: {parent}"
            )
        if not parent.is_dir():
            return ToolResult.fail(
                error=f"Parent is not a directory: {parent}"
            )

        payload = args.content.encode("utf-8")
        if len(payload) > self._config.write_max_bytes:
            return ToolResult.fail(
                error=(
                    f"Content exceeds maximum write size "
                    f"({len(payload)} bytes > "
                    f"{self._config.write_max_bytes} bytes)"
                )
            )

        try:
            resolved.write_bytes(payload)
        except OSError as exc:
            return ToolResult.fail(
                error=f"Failed to create file: {type(exc).__name__}"
            )

        size = resolved.stat().st_size
        return ToolResult.ok(
            output=f"Created {resolved} ({size} bytes)"
        )