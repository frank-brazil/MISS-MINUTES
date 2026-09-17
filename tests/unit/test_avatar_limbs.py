"""Arms/legs: typed limb states, movement hooks and transform validation."""

import pytest
from pydantic import ValidationError

from app.avatar.config import AvatarConfig
from app.avatar.limbs import ArmsAndLegs, LimbSide, LimbState
from app.avatar.models import AvatarPart, AvatarPose, AvatarTransform

LIMB_PARTS = (AvatarPart.LEFT_ARM, AvatarPart.RIGHT_ARM, AvatarPart.LEFT_LEG, AvatarPart.RIGHT_LEG)


def test_limbs_constructed_from_config():
    limbs = ArmsAndLegs()
    states = limbs.limbs()
    assert len(states) == 4
    assert {state.part for state in states} == set(LIMB_PARTS)
    left_arm = limbs.limb(AvatarPart.LEFT_ARM)
    right_arm = limbs.limb(AvatarPart.RIGHT_ARM)
    assert left_arm is not None and right_arm is not None
    assert left_arm.side is LimbSide.LEFT
    assert left_arm.attach_x < 0 < right_arm.attach_x
    for leg in (AvatarPart.LEFT_LEG, AvatarPart.RIGHT_LEG):
        state = limbs.limb(leg)
        assert state.attach_y > 0  # below the body
        assert state.length == AvatarConfig().leg_length


def test_limb_state_validation():
    with pytest.raises(ValidationError):
        LimbState(
            part=AvatarPart.LEFT_ARM,
            side=LimbSide.LEFT,
            attach_x=0,
            attach_y=0,
            length=0.0,
            thickness=4.0,
        )
    with pytest.raises(ValidationError):
        LimbState(
            part=AvatarPart.LEFT_ARM,
            side=LimbSide.LEFT,
            attach_x=0,
            attach_y=0,
            length=10.0,
            thickness=float("nan"),
        )


def test_end_point_rotation_zero_is_down():
    state = LimbState(
        part=AvatarPart.LEFT_LEG,
        side=LimbSide.LEFT,
        attach_x=10.0,
        attach_y=90.0,
        length=36.0,
        thickness=6.0,
    )
    x, y = state.end_point()
    assert x == pytest.approx(10.0)
    assert y == pytest.approx(126.0)


def test_swing_rotates_and_clamps():
    limbs = ArmsAndLegs()
    limbs.swing(AvatarPart.LEFT_ARM, 30.0)
    assert limbs.limb(AvatarPart.LEFT_ARM).base_swing_deg == pytest.approx(30.0)
    limbs.swing(AvatarPart.RIGHT_ARM, 200.0)
    assert limbs.limb(AvatarPart.RIGHT_ARM).base_swing_deg == pytest.approx(90.0)


def test_swing_unknown_part_raises():
    limbs = ArmsAndLegs()
    with pytest.raises(ValueError):
        limbs.swing(AvatarPart.MOUTH, 10.0)


def test_raise_leg_only_for_legs():
    limbs = ArmsAndLegs()
    with pytest.raises(ValueError):
        limbs.raise_leg(AvatarPart.LEFT_ARM, 30.0)
    limbs.raise_leg(AvatarPart.LEFT_LEG, 40.0)
    assert limbs.limb(AvatarPart.LEFT_LEG).base_swing_deg == pytest.approx(-40.0)


def test_reset_zeroes_swings():
    limbs = ArmsAndLegs()
    limbs.swing(AvatarPart.RIGHT_ARM, 45.0)
    limbs.raise_leg(AvatarPart.RIGHT_LEG, 30.0)
    limbs.reset()
    assert all(state.base_swing_deg == 0.0 for state in limbs.limbs())


def test_transforms_include_all_limbs():
    limbs = ArmsAndLegs()
    transforms = limbs.transforms()
    assert {t.part for t in transforms} == set(LIMB_PARTS)
    for transform in transforms:
        LimbState.validate_transform(transform)


def test_transforms_apply_pose_swings():
    limbs = ArmsAndLegs()
    pose = AvatarPose(left_arm_swing=20.0, right_leg_raise=35.0)
    by_part = {t.part: t for t in limbs.transforms(pose)}
    left_arm = by_part[AvatarPart.LEFT_ARM]
    right_leg = by_part[AvatarPart.RIGHT_LEG]
    assert left_arm.rotation_deg == pytest.approx(20.0)
    assert right_leg.rotation_deg == pytest.approx(35.0)


def test_transform_validation_rejects_non_limb():
    with pytest.raises(ValueError):
        LimbState.validate_transform(AvatarTransform(part=AvatarPart.MOUTH))
    with pytest.raises(ValueError):
        LimbState.validate_transform(AvatarTransform(part=AvatarPart.LEFT_ARM, scale=0.0))


def test_idle_pose_transforms_match_resting():
    limbs = ArmsAndLegs()
    resting = {t.part: t for t in limbs.transforms()}
    idle = {t.part: t for t in limbs.transforms(AvatarPose.idle())}
    for part in LIMB_PARTS:
        assert resting[part] == idle[part]


def test_custom_config_changes_geometry():
    skinny = AvatarConfig(leg_length=80.0, arm_length=10.0)
    limbs = ArmsAndLegs(skinny)
    leg = limbs.limb(AvatarPart.RIGHT_LEG)
    assert leg.length == pytest.approx(80.0)
    arm = limbs.limb(AvatarPart.LEFT_ARM)
    assert arm.length == pytest.approx(10.0)
