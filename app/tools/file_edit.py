"""Safe, intentionally limited text-editing tool."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.path_safety import PathSafety, PathSafetyError
from app.core.permissions import ToolPermission
from app.tools.base import Tool, ToolResult
from app.tools.file_config import FileToolConfig


class FileEditArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Absolute path of the file to edit")
    old_text: str = Field(min_length=1, description="Exact text fragment to replace")
    new_text: str = Field(default="", description="Replacement text")
    replace_all: bool = Field(
        default=False,
        description=(
            "When True, every occurrence of old_text is replaced.  The "
            "default refuses edits where old_text appears more than once."
        ),
    )


class FileEditTool(Tool):
    """Replace an exact text fragment in a permitted text file.

    Deliberately minimal for this chunk: no regex, no arbitrary code
    rewriting, no patch execution.  The tool refuses ambiguous replacements
    (multiple occurrences) unless ``replace_all=True``, and never modifies
    files outside the allowed roots.
    """

    name = "file_edit"
    description = (
        "Replaces an exact text fragment in a text file inside an explicitly "
        "permitted directory. Refuses ambiguous replacements (multiple "
        "occurrences) unless replace_all=True."
    )
    input_schema = FileEditArguments
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

        if not resolved.exists():
            return ToolResult.fail(error=f"File does not exist: {resolved}")
        if not resolved.is_file():
            return ToolResult.fail(error=f"Not a regular file: {resolved}")

        try:
            data = resolved.read_bytes()
        except OSError as exc:
            return ToolResult.fail(error=f"Failed to read file: {type(exc).__name__}")

        if len(data) > self._config.write_max_bytes:
            return ToolResult.fail(
                error=(
                    f"File exceeds maximum writable size "
                    f"({len(data)} bytes > "
                    f"{self._config.write_max_bytes} bytes)"
                )
            )

        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return ToolResult.fail(error="File is not valid UTF-8 text")

        occurrences = text.count(args.old_text)
        if occurrences == 0:
            return ToolResult.fail(error=f"Target text not found in {resolved}")
        if occurrences > 1 and not args.replace_all:
            return ToolResult.fail(
                error=(
                    f"Target text appears {occurrences} times; refusing "
                    "ambiguous replacement. Pass replace_all=True to "
                    "replace every occurrence."
                )
            )

        new_text = (
            text.replace(args.old_text, args.new_text)
            if args.replace_all
            else text.replace(args.old_text, args.new_text, 1)
        )

        new_payload = new_text.encode("utf-8")
        if len(new_payload) > self._config.write_max_bytes:
            return ToolResult.fail(
                error=(
                    f"Resulting content exceeds maximum write size "
                    f"({len(new_payload)} bytes > "
                    f"{self._config.write_max_bytes} bytes)"
                )
            )

        try:
            resolved.write_bytes(new_payload)
        except OSError as exc:
            return ToolResult.fail(error=f"Failed to write file: {type(exc).__name__}")

        return ToolResult.ok(output=(f"Edited {resolved} ({occurrences} replacement(s))"))
