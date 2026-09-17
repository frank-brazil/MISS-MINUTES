"""Renderer boundary: primitives, deterministic frames and the fake renderer."""

import pytest
from pydantic import ValidationError

from app.avatar.config import AvatarConfig
from app.avatar.expression import AvatarExpression
from app.avatar.eyes import EyeState
from app.avatar.models import AvatarPart, AvatarPose, AvatarState, AvatarTransform
from app.avatar.mouth import MouthShape, MouthState
from app.avatar.renderer import (
    AvatarRenderer,
    FakeAvatarRenderer,
    RenderFrame,
    RenderPrimitive,
)


def _renderer() -> FakeAvatarRenderer:
    return FakeAvatarRenderer(AvatarConfig())


def test_render_scene_produces_character_frame():
    renderer = _renderer()
    frame = renderer.render_scene()
    assert frame.frame_index == 1
    assert frame.state is AvatarState.IDLE
    assert frame.expression == "neutral"
    assert frame.primitives

    assert len(frame.primitives_for(AvatarPart.CLOCK_BODY)) == 2  # outline + fill
    assert frame.primitives_for(AvatarPart.CLOCK_FACE)
    assert len(frame.primitives_for(AvatarPart.MINUTE_HAND)) == 1
    assert len(frame.primitives_for(AvatarPart.HOUR_HAND)) == 1
    assert len(frame.primitives_for(AvatarPart.CENTER_PIVOT)) == 1
    for part in (AvatarPart.LEFT_EYE, AvatarPart.RIGHT_EYE):
        assert frame.primitives_for(part)
    assert frame.primitives_for(AvatarPart.MOUTH)
    for part in (
        AvatarPart.LEFT_ARM,
        AvatarPart.RIGHT_ARM,
        AvatarPart.LEFT_LEG,
        AvatarPart.RIGHT_LEG,
    ):
        assert frame.primitives_for(part)
    for part in (
        AvatarPart.LEFT_SHOE,
        AvatarPart.RIGHT_SHOE,
        AvatarPart.LEFT_HAND,
        AvatarPart.RIGHT_HAND,
    ):
        assert frame.primitives_for(part)


def test_markings_rendered():
    config = AvatarConfig(markings_count=12)
    renderer = FakeAvatarRenderer(config)
    frame = renderer.render_scene()
    markings = [p for p in frame.primitives if p.part is AvatarPart.CLOCK_FACE and p.kind == "line"]
    assert len(markings) == 12


def test_body_uses_configured_color():
    config = AvatarConfig(body_color="#FFEDED")
    renderer = FakeAvatarRenderer(config)
    frame = renderer.render_scene()
    body_fills = [p for p in frame.primitives_for(AvatarPart.CLOCK_BODY) if p.fill]
    assert body_fills
    assert body_fills[-1].color == "#ffeded"


def test_frame_index_increments():
    renderer = _renderer()
    assert renderer.render_scene().frame_index == 1
    assert renderer.render_scene().frame_index == 2
    assert renderer.last_frame.frame_index == 2


def test_update_expression_and_eyes():
    renderer = _renderer()
    renderer.update_expression("happy", AvatarExpression(mouth_shape=MouthShape.SMILE))
    renderer.update_eyes(EyeState(left_openness=0.4, right_openness=0.4))
    renderer.update_mouth(MouthState(shape=MouthShape.SMILE, openness=0.5))
    frame = renderer.render_scene()
    assert frame.expression == "happy"
    eyes = [p for p in frame.primitives_for(AvatarPart.LEFT_EYE) if p.kind == "ellipse"]
    assert eyes
    assert eyes[0].ry < AvatarConfig().eye_size / 2.0  # squinted eyes
    smiles = frame.primitives_for(AvatarPart.MOUTH)
    assert smiles and smiles[0].kind == "line"


def test_update_transform_overrides_limb_geometry():
    renderer = _renderer()
    transform = AvatarTransform(
        part=AvatarPart.LEFT_ARM, offset_x=15.0, offset_y=-20.0, rotation_deg=45.0
    )
    renderer.update_transform(transform.part, transform)
    frame = renderer.render_scene()
    arm_lines = [p for p in frame.primitives_for(AvatarPart.LEFT_ARM)]
    assert arm_lines
    line = arm_lines[0]
    assert line.x == pytest.approx(15.0)
    assert line.y == pytest.approx(-20.0)


def test_set_clock_time_changes_hands():
    renderer = _renderer()
    renderer.set_clock_time(3, 15)
    renderer.render_scene()
    renderer.set_clock_time(12, 30)
    later = renderer.render_scene()
    assert renderer.calls[-1] == "set_clock_time"
    assert any(p.part is AvatarPart.MINUTE_HAND for p in later.primitives)


def test_close_cleans_up():
    renderer = _renderer()
    renderer.render_scene()
    renderer.close()
    assert renderer.closed is True
    assert renderer.last_frame is None
    assert "close" in renderer.calls


def test_pose_pushed_to_frames():
    renderer = _renderer()
    pose = AvatarPose(body_bob=4.0, lean=0.2)
    renderer.update_pose(pose)
    frame = renderer.render_scene()
    assert frame.pose == pose


def test_render_primitive_kind_validation():
    with pytest.raises(ValidationError):
        RenderPrimitive(kind="circle", radius=-1.0)
    with pytest.raises(ValidationError):
        RenderPrimitive(kind="line")
    with pytest.raises(ValidationError):
        RenderPrimitive(kind="ellipse", rx=1.0, ry=0.0)
    RenderPrimitive(kind="line", x2=10.0, y2=10.0, thickness=2.0)


def test_render_frame_validation():
    with pytest.raises(ValidationError):
        RenderFrame(
            frame_index=1,
            state=AvatarState.IDLE,
            expression="neutral",
            pose=AvatarPose(),
            primitives=["not-a-primitive"],
        )


def test_renderer_abstract_guard():
    with pytest.raises(TypeError):

        class Incomplete(AvatarRenderer):
            pass  # type: ignore[misc]


def test_primitive_for_defaults():
    primitive = RenderPrimitive(kind="ellipse", rx=2.0, ry=3.0)
    assert primitive.fill is True
    assert primitive.color == "#000000"
    assert primitive.part is None
