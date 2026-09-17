"""Approved, allowlisted terminal tool.

This tool never accepts free-form shell input.  Commands are expressed
structurally as allowlisted entries, each mapping to a fixed argument-vector
executed directly (``shell=False``, no ``eval``/``exec``).  Unknown commands,
command chaining, redirection and shell metacharacters are rejected.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.permissions import ToolPermission
from app.tools.base import Tool, ToolResult

_SHELL_METACHARACTERS = frozenset("&|;><`$\\\n\r\0")


@dataclass(frozen=True)
class CommandEntry:
    """A single allowlisted command expressed as a fixed argument vector."""

    name: str
    argv: tuple[str, ...]
    description: str

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("command name must not be blank")
        if not self.argv or any(not token.strip() for token in self.argv):
            raise ValueError(f"command '{self.name}' has an empty argument")
        for token in self.argv:
            for ch in _SHELL_METACHARACTERS:
                if ch in token:
                    raise ValueError(
                        f"command '{self.name}' contains forbidden shell character {ch!r}"
                    )


DEFAULT_ALLOWED_COMMANDS: tuple[CommandEntry, ...] = (
    CommandEntry(
        name="python_version",
        argv=("python", "--version"),
        description="Print the Python version",
    ),
    CommandEntry(
        name="git_version",
        argv=("git", "--version"),
        description="Print the Git version",
    ),
    CommandEntry(
        name="where_python",
        argv=("where", "python"),
        description="Show the location of the python executable (Windows)",
    ),
    CommandEntry(
        name="whoami",
        argv=("whoami",),
        description="Print the current user name",
    ),
    CommandEntry(
        name="hostname",
        argv=("hostname",),
        description="Print the hostname",
    ),
    CommandEntry(
        name="systeminfo",
        argv=("systeminfo",),
        description="Print system information (Windows)",
    ),
    CommandEntry(
        name="ipconfig",
        argv=("ipconfig",),
        description="Print IP configuration (Windows)",
    ),
)


class CommandOutput:
    """Captured output of an executed command."""

    __slots__ = ("stdout", "stderr", "exit_code", "timed_out")

    def __init__(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        timed_out: bool = False,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.timed_out = timed_out


class CommandExecutor(ABC):
    """Runs an allowlisted argument vector with a timeout."""

    @abstractmethod
    async def run(self, argv: tuple[str, ...], *, timeout: float) -> CommandOutput:
        raise NotImplementedError


class SubprocessCommandExecutor(CommandExecutor):
    """Runs commands via ``asyncio.create_subprocess_exec`` (no shell)."""

    def __init__(self, max_output_bytes: int = 8192) -> None:
        self._max_output_bytes = max_output_bytes

    def _truncate(self, raw: bytes) -> str:
        text = raw.decode("utf-8", errors="replace")
        if len(text) > self._max_output_bytes:
            text = text[: self._max_output_bytes] + "\n[output truncated]"
        return text.strip()

    async def run(self, argv: tuple[str, ...], *, timeout: float) -> CommandOutput:
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return CommandOutput("", "command not found", 127)
        except OSError:
            return CommandOutput("", "failed to start command", 126)

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            stdout, stderr = await process.communicate()
            return CommandOutput(
                self._truncate(stdout),
                self._truncate(stderr),
                int(process.returncode or 1),
                timed_out=True,
            )

        return CommandOutput(
            self._truncate(stdout),
            self._truncate(stderr),
            int(process.returncode or 0),
            timed_out=False,
        )


@dataclass(frozen=True)
class TerminalConfig:
    """Configuration for the approved terminal tool."""

    timeout: float = 10.0


class ApprovedTerminalArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = Field(description="Name of an approved command from the allowlist")


class ApprovedTerminalTool(Tool):
    """Runs only allowlisted, read-only commands.

    Commands are identified by name and mapped to a fixed argument vector.
    Free-form shell input, command chaining, redirection and unknown
    commands are all rejected.  No environment variables or secrets are
    ever exposed.
    """

    name = "approved_terminal"
    description = (
        "Runs an allowlisted, read-only command. Only the approved commands "
        "may be invoked: python_version, git_version, where_python, whoami, "
        "hostname, systeminfo, ipconfig."
    )
    input_schema = ApprovedTerminalArguments
    permission: ClassVar[ToolPermission] = ToolPermission.SYSTEM

    def __init__(
        self,
        *,
        executor: CommandExecutor | None = None,
        commands: tuple[CommandEntry, ...] | None = None,
        config: TerminalConfig | None = None,
    ) -> None:
        self._commands = tuple(commands or DEFAULT_ALLOWED_COMMANDS)
        self._config = config or TerminalConfig()

        by_name: dict[str, CommandEntry] = {}
        for entry in self._commands:
            entry.validate()
            if entry.name in by_name:
                raise ValueError(f"duplicate command name '{entry.name}' in allowlist")
            by_name[entry.name] = entry
        self._by_name = by_name

        self._executor = executor or SubprocessCommandExecutor()

    @property
    def approved_command_names(self) -> tuple[str, ...]:
        """Names of every command in the allowlist."""
        return tuple(sorted(self._by_name))

    async def execute(self, **kwargs: object) -> ToolResult:
        args = self.parse_args(**kwargs)

        entry = self._by_name.get(args.command)
        if entry is None:
            known = ", ".join(self.approved_command_names)
            return ToolResult.fail(
                error=(f"Unknown command '{args.command}'. Approved commands: {known}")
            )

        try:
            output = await self._executor.run(entry.argv, timeout=self._config.timeout)
        except Exception as exc:
            return ToolResult.fail(error=f"Command execution failed: {type(exc).__name__}")

        if output.timed_out:
            return ToolResult.fail(error=f"Command '{args.command}' timed out")

        parts: list[str] = []
        if output.stdout:
            parts.append(output.stdout.strip())
        if output.stderr:
            parts.append(f"[stderr] {output.stderr.strip()}")
        if output.exit_code != 0:
            parts.append(f"[exit code: {output.exit_code}]")
        if not parts:
            parts.append("(no output)")

        return ToolResult.ok(output="\n".join(parts))
