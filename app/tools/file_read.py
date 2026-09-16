"""Safe file-reading tool with root enforcement and size limits."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.path_safety import PathSafetyError, PathSafety
from app.core.permissions import ToolPermission
from app.tools.base import Tool, ToolResult
from app.tools.file_config import FileToolConfig


class FileReadArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Absolute path of the file to read")
    max_bytes: int | None = Field(
        default=None,
        ge=1,
        le=10_485_760,
        description=(
            "Maximum bytes to allow.  When the file exceeds this limit the "
            "tool returns a controlled failure rather than partial content.  "
            "Defaults to the configured read limit."
        ),
    )


class FileReadTool(Tool):
    """Read a text file that resides inside an explicitly allowed root.

    The file must be UTF-8–decodable.  Files larger than the configured
    (or caller-specified) read limit are rejected to prevent unbounded
    memory consumption.
    """

    name = "file_read"
    description = (
        "Reads a UTF-8 text file. The file must be inside an explicitly "
        "permitted directory. Returns the full file content."
    )
    input_schema = FileReadArguments
    permission: ClassVar[ToolPermission] = ToolPermission.READ

    def __init__(self, config: FileToolConfig | None = None) -> None:
        self._config = config or FileToolConfig()
        self._safety = PathSafety(self._config.allowed_roots)

    async def execute(self, **kwargs: object) -> ToolResult:
        args = self.parse_args(**kwargs)

        try:
            resolved = self._safety.ensure_within(args.path)
        except PathSafetyError as exc:
            return ToolResult.fail(error=f"Path not allowed: {exc}")

        if not resolved.exists():
            return ToolResult.fail(
                error=f"File does not exist: {resolved}"
            )
        if not resolved.is_file():
            return ToolResult.fail(error=f"Not a regular file: {resolved}")

        limit = args.max_bytes or self._config.read_max_bytes

        try:
            data = resolved.read_bytes()
        except OSError as exc:
            return ToolResult.fail(
                error=f"Failed to read file: {type(exc).__name__}"
            )

        if len(data) > limit:
            return ToolResult.fail(
                error=(
                    f"File exceeds maximum readable size "
                    f"({len(data)} bytes > {limit} bytes)"
                )
            )

        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return ToolResult.fail(
                error="File is not valid UTF-8 text"
            )

        return ToolResult.ok(output=text)