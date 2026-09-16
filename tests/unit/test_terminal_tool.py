import asyncio

import pytest
from pydantic import ValidationError

from app.core.permissions import ToolPermission
from app.tools.base import Tool, ToolResult
from app.tools.terminal import (
    ApprovedTerminalTool,
    CommandEntry,
    CommandExecutor,
    CommandOutput,
    DEFAULT_ALLOWED_COMMANDS,
    SubprocessCommandExecutor,
    TerminalConfig,
)


class FakeCommandExecutor(CommandExecutor):
    def __init__(self) -> None:
        self.executed: list[tuple[str, ...]] = []
        self.responses: list[CommandOutput] = []
        self.timeout = 10.0

    async def run(
        self, argv: tuple[str, ...], *, timeout: float
    ) -> CommandOutput:
        self.executed.append(argv)
        self.timeout = timeout
        if self.responses:
            return self.responses.pop(0)
        return CommandOutput(stdout="fake ok", stderr="", exit_code=0)


class RaisingCommandExecutor(CommandExecutor):
    async def run(
        self, argv: tuple[str, ...], *, timeout: float
    ) -> CommandOutput:
        raise RuntimeError("executor exploded")


def test_terminal_metadata() -> None:
    assert ApprovedTerminalTool.name == "approved_terminal"
    assert isinstance(ApprovedTerminalTool.description, str)
    assert issubclass(ApprovedTerminalTool, Tool)
    assert ApprovedTerminalTool.permission == ToolPermission.SYSTEM


def test_default_allowlist_contains_expected_commands() -> None:
    names = {entry.name for entry in DEFAULT_ALLOWED_COMMANDS}
    assert "python_version" in names
    assert "git_version" in names
    assert "where_python" in names
    assert "whoami" in names
    assert "systeminfo" in names
    assert "ipconfig" in names
    assert "hostname" in names


def test_allowlist_entries_are_structural_argv() -> None:
    for entry in DEFAULT_ALLOWED_COMMANDS:
        entry.validate()
        assert entry.argv
        assert all(token.strip() for token in entry.argv)
        assert entry.description


def test_approved_command_success() -> None:
    executor = FakeCommandExecutor()
    tool = ApprovedTerminalTool(executor=executor)
    result = asyncio.run(tool.execute(command="whoami"))
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.output == "fake ok"
    assert executor.executed == [("whoami",)]


def test_approved_command_captures_stderr_and_exit_code() -> None:
    executor = FakeCommandExecutor()
    executor.responses.append(
        CommandOutput(stdout="", stderr="warn", exit_code=3)
    )
    tool = ApprovedTerminalTool(executor=executor)
    result = asyncio.run(tool.execute(command="hostname"))
    assert result.success is True
    assert "[stderr] warn" in (result.output or "")
    assert "[exit code: 3]" in (result.output or "")


def test_unknown_command_rejected() -> None:
    tool = ApprovedTerminalTool(executor=FakeCommandExecutor())
    result = asyncio.run(tool.execute(command="rm -rf /"))
    assert result.success is False
    assert "Unknown command" in (result.error or "")
    assert "whoami" in (result.error or "")


def test_command_chaining_rejected_by_allowlist_lookup() -> None:
    tool = ApprovedTerminalTool(executor=FakeCommandExecutor())
    for attempt in ("whoami && whoami", "whoami;rm", "whoami|cat", "whoami>f", "python;ls"):
        result = asyncio.run(tool.execute(command=attempt))
        assert result.success is False
        assert "Unknown command" in (result.error or "")


def test_timeout_returns_controlled_failure() -> None:
    executor = FakeCommandExecutor()
    executor.responses.append(
        CommandOutput(
            stdout="partial", stderr="", exit_code=1, timed_out=True
        )
    )
    tool = ApprovedTerminalTool(executor=executor)
    result = asyncio.run(tool.execute(command="whoami"))
    assert result.success is False
    assert "timed out" in (result.error or "")


def test_executor_exception_is_controlled() -> None:
    tool = ApprovedTerminalTool(executor=RaisingCommandExecutor())
    result = asyncio.run(tool.execute(command="whoami"))
    assert result.success is False
    assert "execution failed" in (result.error or "")


def test_timeout_propagated_to_executor() -> None:
    executor = FakeCommandExecutor()
    tool = ApprovedTerminalTool(
        executor=executor, config=TerminalConfig(timeout=2.5)
    )
    asyncio.run(tool.execute(command="whoami"))
    assert executor.timeout == 2.5


def test_custom_allowlist_only() -> None:
    custom = (
        CommandEntry(name="python_version", argv=("python", "--version"), description="py"),
    )
    tool = ApprovedTerminalTool(
        executor=FakeCommandExecutor(), commands=custom
    )
    result = asyncio.run(tool.execute(command="whoami"))
    assert result.success is False
    assert "python_version" in (result.error or "")

    result = asyncio.run(tool.execute(command="python_version"))
    assert result.success is True


def test_duplicate_command_names_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        ApprovedTerminalTool(
            executor=FakeCommandExecutor(),
            commands=(
                CommandEntry(name="a", argv=("a",), description="a"),
                CommandEntry(name="a", argv=("b",), description="b"),
            ),
        )


def test_allowlist_with_shell_metachars_rejected() -> None:
    bad = (
        CommandEntry(
            name="bad",
            argv=("cmd", "&& echo hacked"),
            description="unsafe",
        ),
    )
    with pytest.raises(ValueError, match="forbidden shell character"):
        ApprovedTerminalTool(executor=FakeCommandExecutor(), commands=bad)


def test_allowlist_with_empty_argv_rejected() -> None:
    with pytest.raises(ValueError, match="empty argument"):
        CommandEntry(name="bad", argv=("", ""), description="bad").validate()


def test_invalid_command_argument_is_validation_error() -> None:
    tool = ApprovedTerminalTool(executor=FakeCommandExecutor())
    with pytest.raises(ValidationError):
        asyncio.run(tool.execute())


def test_approved_command_names_are_sorted() -> None:
    tool = ApprovedTerminalTool()
    names = tool.approved_command_names
    assert names == tuple(sorted(names))
    assert "whoami" in names


def test_subprocess_executor_runs_approved_command() -> None:
    executor = SubprocessCommandExecutor()
    output = asyncio.run(
        executor.run(("python", "--version"), timeout=10.0)
    )
    assert output.exit_code == 0
    assert "Python" in output.stdout
    assert not output.timed_out


def test_subprocess_executor_missing_command() -> None:
    executor = SubprocessCommandExecutor()
    output = asyncio.run(
        executor.run(("definitely-not-a-real-command-xyz",), timeout=5.0)
    )
    assert output.exit_code != 0
    assert not output.timed_out


def test_subprocess_executor_truncates_large_output() -> None:
    executor = SubprocessCommandExecutor(max_output_bytes=50)
    code = "import sys; sys.stdout.write('x' * 500)"
    output = asyncio.run(executor.run(("python", "-c", code), timeout=10.0))
    assert output.exit_code == 0
    assert "[output truncated]" in output.stdout
    assert output.stdout.count("x") == 50
    assert output.stdout.rstrip().endswith("[output truncated]")