import asyncio
from pathlib import Path

import pytest
from app.browser.fakes import FakeBrowserProvider
from app.browser.policy import UrlPolicy
from app.browser.tools import BrowserToolBundle
from app.core.permissions import ToolPermission
from app.tools.base import Tool, ToolResult
from app.tools.file_config import FileToolConfig
from pydantic import ValidationError


def _run(coro):
    return asyncio.run(coro)


def _bundle(tmp_path: Path, *, allow_hosts: tuple[str, ...] = ("localhost",)) -> BrowserToolBundle:
    download_root = tmp_path / "downloads"
    download_root.mkdir()
    config = FileToolConfig(allowed_roots=(download_root,), write_max_bytes=65_536)
    policy = UrlPolicy(allow_domains=allow_hosts)
    provider = FakeBrowserProvider()
    bundle = BrowserToolBundle(
        provider=provider,
        url_policy=policy,
        download_config=config,
    )
    return bundle


def test_bundle_constructs_five_tools(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    names = {tool.name for tool in bundle.tools()}
    assert names == {
        "browser_open",
        "browser_read",
        "browser_click",
        "browser_type",
        "browser_download",
    }
    for tool in bundle.tools():
        assert isinstance(tool, Tool)


def test_bundle_declares_permissions(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    assert bundle.open_tool.permission == ToolPermission.SYSTEM
    assert bundle.read_tool.permission == ToolPermission.SYSTEM
    assert bundle.click_tool.permission == ToolPermission.SYSTEM
    assert bundle.type_tool.permission == ToolPermission.SYSTEM
    assert bundle.download_tool.permission == ToolPermission.WRITE


def test_bundle_start_and_stop(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    assert bundle.provider.started is True
    _run(bundle.stop())
    assert bundle.provider.started is False


# ------------------------------------------------------------------
# browser_open
# ------------------------------------------------------------------


def test_open_success(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    result = _run(bundle.open_tool.execute(url="http://localhost/page"))
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert "http://localhost/page" in (result.output or "")
    assert "default" in (result.output or "")


def test_open_with_explicit_session(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    result = _run(bundle.open_tool.execute(url="http://localhost/x", session_id="s1"))
    assert result.success is True
    assert "s1" in (result.output or "")


def test_open_rejects_disallowed_domain(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    result = _run(bundle.open_tool.execute(url="https://example.com/"))
    assert result.success is False
    assert "URL rejected" in (result.error or "")
    assert bundle.provider.sessions() == ()


def test_open_rejects_javascript_url(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    result = _run(bundle.open_tool.execute(url="javascript:alert(1)"))
    assert result.success is False
    assert "URL rejected" in (result.error or "")


def test_open_rejects_file_url(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, allow_hosts=("localhost",))
    _run(bundle.start())
    result = _run(bundle.open_tool.execute(url="file:///C:/Windows/secret.txt"))
    assert result.success is False
    assert "URL rejected" in (result.error or "")


def test_open_missing_extra_args_rejected(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    with pytest.raises(ValidationError):
        _run(bundle.open_tool.execute())


def test_open_exception_becomes_controlled_failure(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    provider = bundle.provider
    original = provider.open_url

    async def broken(session_id: str, url: str):
        raise RuntimeError("engine crashed")

    provider.open_url = broken
    result = _run(bundle.open_tool.execute(url="http://localhost/x"))
    assert result.success is False
    assert "failed" in (result.error or "").lower()
    provider.open_url = original


# ------------------------------------------------------------------
# browser_read
# ------------------------------------------------------------------


def test_read_returns_page_content(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    _run(bundle.provider.seed_page(content="Top secret report"))
    result = _run(bundle.read_tool.execute())
    assert result.success is True
    assert result.output == "Top secret report"


def test_read_with_selector(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    _run(bundle.provider.seed_page(elements={"#price": "42"}))
    result = _run(bundle.read_tool.execute(selector="#price"))
    assert result.success is True
    assert result.output == "42"


def test_read_missing_element_fails(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    _run(bundle.provider.seed_page())
    result = _run(bundle.read_tool.execute(selector="#missing"))
    assert result.success is False
    assert "element not found" in (result.error or "")


def test_read_on_empty_session_fails(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    result = _run(bundle.read_tool.execute())
    assert result.success is False
    assert "no page" in (result.error or "")


def test_read_invalid_max_chars_rejected(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    with pytest.raises(ValidationError):
        _run(bundle.read_tool.execute(max_chars=0))
    with pytest.raises(ValidationError):
        _run(bundle.read_tool.execute(max_chars=1_000_000))


# ------------------------------------------------------------------
# browser_click
# ------------------------------------------------------------------


def test_click_success(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    _run(bundle.provider.seed_page())
    result = _run(bundle.click_tool.execute(selector="#submit"))
    assert result.success is True
    assert "#submit" in (result.output or "")


def test_click_missing_element_fails(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    _run(bundle.provider.seed_page())
    bundle.provider.fail_click_on.add("#ghost")
    result = _run(bundle.click_tool.execute(selector="#ghost"))
    assert result.success is False
    assert "element not found" in (result.error or "")


def test_click_blank_selector_rejected(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    with pytest.raises(ValidationError):
        _run(bundle.click_tool.execute(selector=""))


# ------------------------------------------------------------------
# browser_type
# ------------------------------------------------------------------


def test_type_success(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    _run(bundle.provider.seed_page())
    result = _run(bundle.type_tool.execute(selector="#search", text="cats"))
    assert result.success is True
    assert "4 characters" in (result.output or "")


def test_type_replace_action(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    _run(bundle.provider.seed_page())
    result = _run(bundle.type_tool.execute(selector="#search", text="dogs", action="replace"))
    assert result.success is True
    assert "Replaced" in (result.output or "")


def test_type_clear_action(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    _run(bundle.provider.seed_page())
    result = _run(bundle.type_tool.execute(selector="#search", action="clear"))
    assert result.success is True
    assert "Cleared" in (result.output or "")


def test_type_invalid_action_rejected(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    with pytest.raises(ValidationError):
        _run(bundle.type_tool.execute(selector="#s", text="x", action="paste"))


# ------------------------------------------------------------------
# browser_download
# ------------------------------------------------------------------


def test_download_success(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    _run(bundle.provider.seed_page())
    bundle.provider.register_download(
        "http://localhost/report.pdf", b"%PDF-fake-bytes", "report.pdf"
    )
    dest_root = tmp_path / "downloads"
    result = _run(
        bundle.download_tool.execute(
            url="http://localhost/report.pdf",
            destination=str(dest_root),
        )
    )
    assert result.success is True
    assert "report.pdf" in (result.output or "")
    saved = dest_root / "report.pdf"
    assert saved.exists()


def test_download_to_explicit_file(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    _run(bundle.provider.seed_page())
    bundle.provider.register_download("http://localhost/a.bin", b"\x00\x01")
    target = tmp_path / "downloads" / "custom.bin"
    result = _run(
        bundle.download_tool.execute(url="http://localhost/a.bin", destination=str(target))
    )
    assert result.success is True
    assert target.exists()


def test_download_rejects_unsafe_url(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    dest_root = tmp_path / "downloads"
    result = _run(
        bundle.download_tool.execute(url="file:///C:/Windows/x", destination=str(dest_root))
    )
    assert result.success is False
    assert "URL rejected" in (result.error or "")


def test_download_outside_allowed_root(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    outside = tmp_path / "outside"
    outside.mkdir()
    result = _run(
        bundle.download_tool.execute(
            url="http://localhost/f.bin",
            destination=str(outside / "f.bin"),
        )
    )
    assert result.success is False
    assert "not allowed" in (result.error or "")


def test_download_no_allowed_root_fails(tmp_path: Path) -> None:
    provider = FakeBrowserProvider()
    bundle = BrowserToolBundle(provider=provider)
    _run(bundle.start())
    result = _run(
        bundle.download_tool.execute(
            url="http://localhost/f.bin", destination=str(tmp_path / "f.bin")
        )
    )
    assert result.success is False
    assert "no allowed download directory" in (result.error or "")


def test_download_missing_parent_dir_fails(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    result = _run(
        bundle.download_tool.execute(
            url="http://localhost/f.bin",
            destination=str(tmp_path / "downloads" / "no" / "dir" / "f.bin"),
        )
    )
    assert result.success is False
    assert "does not exist" in (result.error or "")


def test_download_no_registered_content_fails(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    dest_root = tmp_path / "downloads"
    result = _run(
        bundle.download_tool.execute(url="http://localhost/missing.bin", destination=str(dest_root))
    )
    assert result.success is False
    assert "no download available" in (result.error or "")


def test_download_existing_target_fails(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    bundle.provider.register_download("http://localhost/f.bin", b"x")
    target = tmp_path / "downloads" / "f.bin"
    target.write_bytes(b"existing")
    result = _run(
        bundle.download_tool.execute(url="http://localhost/f.bin", destination=str(target))
    )
    assert result.success is False
    assert "already exists" in (result.error or "")


# ------------------------------------------------------------------
# closed sessions
# ------------------------------------------------------------------


def test_tool_on_closed_session_fails(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    _run(bundle.open_tool.execute(url="http://localhost/x"))
    _run(bundle.provider.close_session("default"))
    result = _run(bundle.read_tool.execute())
    assert result.success is False
    assert "closed" in (result.error or "").lower()


def test_default_session_auto_created(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _run(bundle.start())
    assert bundle.provider.has_session("default") is False
    _run(bundle.open_tool.execute(url="http://localhost/x"))
    assert bundle.provider.has_session("default") is True
