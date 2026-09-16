"""Safe read-only system-information tool."""

from __future__ import annotations

import os
import platform
import socket
import sys
from typing import ClassVar

from app.core.permissions import ToolPermission
from app.tools.base import Tool, ToolArguments, ToolResult


class SystemInfoTool(Tool):
    """Reports safe, read-only system information.

    No environment variables, secrets or network details are exposed.
    """

    name = "system_info"
    description = (
        "Reports read-only system information: operating system, Python "
        "version, machine architecture, CPU count and hostname."
    )
    input_schema = ToolArguments
    permission: ClassVar[ToolPermission] = ToolPermission.SYSTEM

    def _collect(self) -> dict[str, str]:
        return {
            "platform": sys.platform,
            "system": platform.system() or "unknown",
            "release": platform.release() or "unknown",
            "machine": platform.machine() or "unknown",
            "architecture": ", ".join(platform.architecture()) or "unknown",
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "cpu_count": str(os.cpu_count() or "unknown"),
            "hostname": socket.gethostname(),
        }

    async def execute(self, **kwargs: object) -> ToolResult:
        self.parse_args(**kwargs)
        try:
            info = self._collect()
        except Exception as exc:
            return ToolResult.fail(
                error=f"Failed to collect system info: {type(exc).__name__}"
            )
        lines = [f"{key}: {value}" for key, value in info.items()]
        return ToolResult.ok(output="\n".join(lines))
