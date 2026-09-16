import asyncio
from pathlib import Path

import pytest

from app.browser.errors import (
    BrowserActionError,
    BrowserContentError,
    BrowserError,
    BrowserSessionError,
    BrowserStartupError,
)
from app.browser.fakes import FakeBrowserProvider
from app.browser.models import (
    BrowserSession,
    BrowserSessionStatus,
    TextEntryAction,
)
from app.browser.provider import BrowserProvider


def _run(coro):
    return asyncio.run(coro)


def test_browser_provider_is_abstract() -> None:
    with pytest.raises(TypeError):
        BrowserProvider()


def test_fake_provider_start_and_stop() -> None:
    provider = FakeBrowserProvider()
    assert provider.started is False
    _run(provider.start())
    assert provider.started is True
    assert provider.start_count == 1
    _run(provider.stop())
    assert provider.started is False
    assert provider.stop_count == 1


def test_fake_provider_fail_start_controlled() -> None:
    provider = FakeBrowserProvider(fail_start=True)
    with pytest.raises(BrowserStartupError):
        _run(provider.start())


def test_create_session_requires_started_browser() -> None:
    provider = FakeBrowserProvider()
    with pytest.raises(BrowserSessionError):
        _run(provider.create_session())


def test_create_session_returns_typed_session() -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    session = _run(provider.create_session(session_id="s1"))
    assert isinstance(session, BrowserSession)
    assert session.session_id == "s1"
    assert session.status == BrowserSessionStatus.ACTIVE
    assert session.current_url is None
    assert session.created_at is not None
    assert session.updated_at is not None


def test_automatic_session_id() -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    first = _run(provider.create_session())
    second = _run(provider.create_session())
    assert first.session_id != second.session_id


def test_duplicate_session_rejected() -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    _run(provider.create_session(session_id="dup"))
    with pytest.raises(BrowserSessionError, match="already exists"):
        _run(provider.create_session(session_id="dup"))


def test_has_session_and_sessions() -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    assert provider.has_session("x") is False
    _run(provider.create_session(session_id="b"))
    _run(provider.create_session(session_id="a"))
    assert provider.has_session("a") is True
    assert provider.has_session("b") is True
    assert [s.session_id for s in provider.sessions()] == ["a", "b"]


def test_close_session_marks_closed() -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    _run(provider.create_session(session_id="s"))
    _run(provider.close_session("s"))
    session = provider.sessions()[0]
    assert session.status == BrowserSessionStatus.CLOSED


def test_actions_on_closed_session_rejected() -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    _run(provider.create_session(session_id="s"))
    _run(provider.close_session("s"))
    with pytest.raises(BrowserSessionError, match="closed"):
        _run(provider.open_url("s", "http://localhost/x"))


def test_actions_on_unknown_session_rejected() -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    with pytest.raises(BrowserSessionError, match="unknown session"):
        _run(provider.open_url("nope", "http://localhost/x"))


def test_stop_clears_sessions() -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    _run(provider.create_session(session_id="s"))
    _run(provider.stop())
    assert provider.sessions() == ()
    assert provider.has_session("s") is False


def test_open_url_updates_session_state() -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    session = _run(provider.create_session(session_id="s"))
    nav = _run(provider.open_url("s", "http://localhost/hello"))
    assert nav.url == "http://localhost/hello"
    assert nav.status == 200
    assert session.current_url == "http://localhost/hello"
    assert session.title is not None


def test_get_current_url_and_title() -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    _run(provider.create_session(session_id="s"))
    _run(provider.open_url("s", "http://localhost/x"))
    assert _run(provider.get_current_url("s")) == "http://localhost/x"
    assert _run(provider.get_title("s")) is not None


def test_get_title_on_empty_session_fails() -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    _run(provider.create_session(session_id="s"))
    with pytest.raises(BrowserError):
        _run(provider.get_title("s"))


def test_read_content_truncates() -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    _run(provider.seed_page(session_id="s", content="x" * 500))
    content = _run(provider.read_content("s", max_chars=100))
    assert content.truncated is True
    assert len(content.content) == 100


def test_read_content_with_element_selector() -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    _run(provider.seed_page(session_id="s", elements={"#title": "Hello!"}))
    content = _run(provider.read_content("s", selector="#title"))
    assert content.content == "Hello!"


def test_read_content_missing_element_fails() -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    _run(provider.seed_page(session_id="s"))
    with pytest.raises(BrowserContentError, match="element not found"):
        _run(provider.read_content("s", selector="#missing"))


def test_read_before_navigation_fails() -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    _run(provider.create_session(session_id="s"))
    with pytest.raises(BrowserContentError, match="no page"):
        _run(provider.read_content("s"))


def test_click_records_and_fails_on_missing() -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    _run(provider.create_session(session_id="s"))
    result = _run(provider.click("s", "#button"))
    assert result.selector == "#button"
    assert result.ok is True

    provider.fail_click_on.add("#ghost")
    with pytest.raises(BrowserActionError):
        _run(provider.click("s", "#ghost"))


def test_type_text_records_actions() -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    _run(provider.create_session(session_id="s"))
    result = _run(
        provider.type_text("s", "#search", "cats", action=TextEntryAction.REPLACE)
    )
    assert result.chars_typed == 4
    page = provider._pages["s"]
    assert page.typing[-1]["selector"] == "#search"
    assert page.typing[-1]["action"] == "replace"


def test_screenshot_writes_file_and_metadata(tmp_path: Path) -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    _run(provider.seed_page(session_id="s"))
    target = tmp_path / "cap.png"
    shot = _run(provider.screenshot("s", path=target))
    assert shot.path == target
    assert target.exists()
    assert shot.size_bytes == len(b"fake-png-bytes")
    assert shot.format == "png"


def test_download_writes_registered_bytes(tmp_path: Path) -> None:
    provider = FakeBrowserProvider()
    _run(provider.start())
    _run(provider.seed_page(session_id="s"))
    provider.register_download("http://localhost/report.pdf", b"%PDF-fake")
    target = tmp_path / "report.pdf"
    download = _run(provider.download("s", "http://localhost/report.pdf", destination=target))
    assert download.saved_to == target
    assert download.size_bytes == 9
    assert target.read_bytes() == b"%PDF-fake"


def test_download_unknown_url_fails() -> None:
    from app.browser.errors import BrowserDownloadError

    provider = FakeBrowserProvider()
    _run(provider.start())
    _run(provider.seed_page(session_id="s"))
    with pytest.raises(BrowserDownloadError):
        _run(
            provider.download(
                "s", "http://localhost/missing", destination=Path("unused")
            )
        )
