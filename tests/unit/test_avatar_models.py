"""Typed avatar models: enums, transforms and poses."""

import pytest
from pydantic import ValidationError

from app.avatar.models import (
    AvatarPart,
    AvatarPose,
    AvatarState,
    AvatarTransform,
)


def test_state_enum_contains_required_states():
    required = {
        "idle",
        "listening",
        "thinking",
        "working",
        "speaking",
        "happy",
        "concerned",
        "warning",
        "success",
        "error",
        "sleeping",
        "hidden",
        "walking",
        "explaining",
        "interrupted",
    }
    assert {state.value for state in AvatarState} == required


def test_part_enum_covers_character():
    values = {part.value for part in AvatarPart}
    assert {"clock_body", "clock_face", "hour_hand", "minute_hand", "left_eye",
            "right_eye", "mouth", "left_arm", "right_arm", "left_hand", "right_hand",
            "left_leg", "right_leg", "left_shoe", "right_shoe", "center_pivot"} <= values


def test_transform_defaults():
    transform = AvatarTransform(part=AvatarPart.LEFT_ARM)
    assert transform.offset_x == 0.0
    assert transform.rotation_deg == 0.0
    assert transform.scale == 1.0


def test_transform_accepts_custom_values():
    transform = AvatarTransform(
        part=AvatarPart.HOUR_HAND,
        offset_x=5.0,
        offset_y=-2.0,
        rotation_deg=90.0,
        scale=1.5,
    )
    assert transform.rotation_deg == 90.0
    assert transform.scale == 1.5
    assert transform.part is AvatarPart.HOUR_HAND


def test_transform_rejects_nonpositive_scale():
    for scale in (0.0, -1.0):
        with pytest.raises(ValidationError):
            AvatarTransform(part=AvatarPart.MOUTH, scale=scale)


def test_transform_rejects_nonfinite():
    with pytest.raises(ValidationError):
        AvatarTransform(part=AvatarPart.MOUTH, offset_x=float("inf"))


def test_pose_defaults_to_idle_pose():
    pose = AvatarPose()
    assert pose == AvatarPose.idle()
    assert pose.body_bob == 0.0
    assert pose.lean == 0.0


def test_pose_accepts_valid_range():
    pose = AvatarPose(
        body_bob=3.5,
        body_tilt_deg=10.0,
        face_tilt_deg=-4.0,
        lean=0.3,
        left_arm_swing=20.0,
        right_leg_raise=45.0,
    )
    assert pose.left_arm_swing == 20.0
    assert pose.right_leg_raise == 45.0


def test_pose_bounds_are_enforced():
    with pytest.raises(ValidationError):
        AvatarPose(body_tilt_deg=120.0)
    with pytest.raises(ValidationError):
        AvatarPose(left_arm_swing=95.0)
    with pytest.raises(ValidationError):
        AvatarPose(right_leg_raise=150.0)
    with pytest.raises(ValidationError):
        AvatarPose(lean=2.0)
    with pytest.raises(ValidationError):
        AvatarPose(body_bob=float("nan"))


def test_pose_allows_forward_leg_raise():
    pose = AvatarPose(left_leg_raise=120.0)
    assert pose.left_leg_raise == 120.0