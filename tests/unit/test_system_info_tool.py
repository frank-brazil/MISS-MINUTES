import asyncio
import os

from app.core.permissions import ToolPermission
from app.tools.base import Tool, ToolResult
from app.tools.system_info import SystemInfoTool

EXPECTED_KEYS = {
    "platform",
    "system",
    "release",
    "machine",
    "architecture",
    "python_version",
    "python_implementation",
    "cpu_count",
    "hostname",
}


def test_system_info_metadata() -> None:
    assert SystemInfoTool.name == "system_info"
    assert isinstance(SystemInfoTool.description, str)
    assert SystemInfoTool.description
    assert issubclass(SystemInfoTool, Tool)
    assert SystemInfoTool.permission == ToolPermission.SYSTEM


def test_collect_returns_structure() -> None:
    info = SystemInfoTool()._collect()
    assert isinstance(info, dict)
    assert set(info) == EXPECTED_KEYS
    for value in info.values():
        assert value
        assert "\n" not in value


def test_execute_success() -> None:
    result = asyncio.run(SystemInfoTool().execute())
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.error is None
    assert result.output is not None

    lines = result.output.splitlines()
    keys = {line.split(":", 1)[0] for line in lines}
    assert keys == EXPECTED_KEYS


def test_output_does_not_expose_environment_variables() -> None:
    result = asyncio.run(SystemInfoTool().execute())
    output = result.output or ""
    env_indicators = ("PATH=", "HOME=", "USERPROFILE=", "OS=", "TEMP=")
    for indicator in env_indicators:
        assert indicator not in output
    for line in output.splitlines():
        key = line.split(":", 1)[0]
        assert key in EXPECTED_KEYS


def test_no_arguments_required() -> None:
    info = SystemInfoTool()._collect()
    assert set(info) == EXPECTED_KEYS


def test_cpu_count_is_numeric_or_unknown() -> None:
    info = SystemInfoTool()._collect()
    assert info["cpu_count"] == "unknown" or info["cpu_count"].isdigit()
    if os.cpu_count() is not None:
        assert info["cpu_count"] == str(os.cpu_count())