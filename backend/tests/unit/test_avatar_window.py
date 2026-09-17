"""Window/UI boundary: config validation and the fake character window."""

import pytest
from app.avatar.renderer import FakeAvatarRenderer
from app.avatar.window import AvatarWindow, AvatarWindowConfig, FakeAvatarWindow
from pydantic import ValidationError


def test_window_config_defaults_are_character_first():
    config = AvatarWindowConfig()
    assert config.width == 420
    assert config.height == 520
    assert config.always_on_top is True
    assert config.transparent_background is True
    assert config.visible_on_start is False
    assert config.character_first is True
    assert config.position_x is None


def test_window_config_validation():
    with pytest.raises(ValidationError):
        AvatarWindowConfig(width=10)
    with pytest.raises(ValidationError):
        AvatarWindowConfig(height=5000)


def test_fake_window_initial_state():
    window = FakeAvatarWindow()
    assert window.visible is False
    assert window.closed is False
    assert window.size == (420, 520)
    assert window.position == (100, 100)
    assert window.always_on_top is True
    assert window.last_frame is None


def test_fake_window_lifecycle():
    window = FakeAvatarWindow(AvatarWindowConfig(visible_on_start=True))
    assert window.visible is True
    window.hide()
    assert window.visible is False
    assert ("hide", ()) in window.ops
    window.show()
    assert window.visible is True


def test_fake_window_position_and_size():
    window = FakeAvatarWindow()
    window.set_position(20, 40)
    assert window.position == (20, 40)
    window.set_size(300, 400)
    assert window.size == (300, 400)
    assert window.config.width == 300
    assert window.config.height == 400
    window.set_always_on_top(False)
    assert window.always_on_top is False


def test_fake_window_close():
    window = FakeAvatarWindow()
    window.show()
    window.close()
    assert window.closed is True
    assert window.visible is False


def test_fake_window_paint_without_renderer():
    window = FakeAvatarWindow()
    window.paint()
    assert window.paint_count == 1
    assert window.last_frame is None


def test_fake_window_paint_with_renderer():
    window = FakeAvatarWindow()
    renderer = FakeAvatarRenderer()
    window.attach_renderer(renderer)
    renderer.render_scene()
    window.paint()
    assert window.paint_count == 1
    assert window.last_frame is not None
    assert window.last_frame.frame_index == 1


def test_window_abstract_guard():
    with pytest.raises(TypeError):

        class Incomplete(AvatarWindow):
            pass  # type: ignore[misc]
