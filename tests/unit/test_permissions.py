from app.core.permissions import ToolPermission
from app.tools.file_create import FileCreateTool
from app.tools.file_edit import FileEditTool
from app.tools.file_read import FileReadTool
from app.tools.file_search import FileSearchTool
from app.tools.screenshot import ScreenshotTool
from app.tools.system_info import SystemInfoTool
from app.tools.terminal import ApprovedTerminalTool


def test_permission_enum_values() -> None:
    assert ToolPermission.READ == "read"
    assert ToolPermission.WRITE == "write"
    assert ToolPermission.SYSTEM == "system"


def test_permission_is_an_enum() -> None:
    assert len(list(ToolPermission)) == 3
    assert set(ToolPermission) == {
        ToolPermission.READ,
        ToolPermission.WRITE,
        ToolPermission.SYSTEM,
    }


def test_read_tools_declare_read_permission() -> None:
    assert FileSearchTool.permission == ToolPermission.READ
    assert FileReadTool.permission == ToolPermission.READ


def test_write_tools_declare_write_permission() -> None:
    assert FileCreateTool.permission == ToolPermission.WRITE
    assert FileEditTool.permission == ToolPermission.WRITE
    assert ScreenshotTool.permission == ToolPermission.WRITE


def test_system_tools_declare_system_permission() -> None:
    assert SystemInfoTool.permission == ToolPermission.SYSTEM
    assert ApprovedTerminalTool.permission == ToolPermission.SYSTEM
