"""Safety guarantees for the avatar layer.

The avatar engine must be fully offline and deterministic: no AI/provider
dependency, no network, no foreign runtime import. These tests pin that down.
"""

import re
from pathlib import Path

from app.avatar.controller import AvatarController, AvatarSignal
from app.avatar.renderer import FakeAvatarRenderer

PACKAGE = Path(__file__).resolve().parents[2] / "app" / "avatar"
BANNED = ("openai", "fastapi", "uvicorn", "httpx", "requests", "socket", "aiohttp")


def _avatar_sources() -> list[Path]:
    return sorted(PACKAGE.glob("*.py")) + sorted(PACKAGE.glob("*/*.py"))


def test_avatar_package_does_not_import_foreign_services():
    violations: list[str] = []
    for path in _avatar_sources():
        source = path.read_text(encoding="utf-8").lower()
        for token in BANNED:
            if re.search(rf"(^|\b)(import|from)\s+{token}", source):
                violations.append(f"{path.name}: {token}")
    assert not violations


def test_avatar_package_has_no_threading_or_network_primitives():
    for path in _avatar_sources():
        source = path.read_text(encoding="utf-8").lower()
        assert "threading." not in source
        assert "socket" not in source
        assert "urllib" not in source


def test_engine_works_fully_offline():
    clock = {"value": 1.0}

    def now_fn() -> float:
        return clock["value"]

    controller = AvatarController(FakeAvatarRenderer(), now_fn=now_fn)
    assert controller.start() is True
    for signal in (
        AvatarSignal.LISTENING,
        AvatarSignal.THINKING,
        AvatarSignal.WORKING,
        AvatarSignal.SPEAKING,
        AvatarSignal.SUCCESS,
        AvatarSignal.IDLE,
    ):
        assert controller.handle(signal) is True
    controller.blink()
    controller.look(0.3, -0.4)
    controller.set_clock_time(9, 42)
    clock["value"] += 5.0
    frame = controller.update()
    assert frame.primitives
    assert controller.stop() is True


def test_avatar_layer_has_no_dependency_on_voice_or_ai():
    """Core avatar modules must not import voice/AI internals (the voice
    adapter and tts adapter are the single, explicit boundaries and may)."""
    for path in _avatar_sources():
        source = path.read_text(encoding="utf-8")
        if path.name in ("voice_adapter.py", "tts_adapter.py"):
            continue
        assert "app.voice" not in source, path.name
        assert "app.ai" not in source, path.name
        assert "app.orchestrator" not in source, path.name
