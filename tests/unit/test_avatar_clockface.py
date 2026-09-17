"""Clock-face component: markings, hands, angles and validation."""

import pytest
from pydantic import ValidationError

from app.avatar.clockface import ClockFace, ClockHandState
from app.avatar.config import AvatarConfig
from app.avatar.models import AvatarPart


def test_marking_angles_count_and_spacing():
    face = ClockFace()
    angles = face.marking_angles()
    assert len(angles) == AvatarConfig().markings_count == 12
    assert len(set(round(a, 6) for a in angles)) == 12
    assert angles[0] == pytest.approx(0.0)
    assert angles[1] == pytest.approx(30.0)


def test_custom_marking_count():
    face = ClockFace(AvatarConfig(markings_count=4))
    assert face.marking_angles() == pytest.approx((0.0, 90.0, 180.0, 270.0))


def test_hand_angles_math():
    hour, minute = ClockFace.hand_angles(10, 10)
    assert hour == pytest.approx(305.0)
    assert minute == pytest.approx(60.0)
    assert ClockFace.hand_angles(0, 0) == (0.0, 0.0)
    hour13, _ = ClockFace.hand_angles(13, 0)
    assert hour13 == pytest.approx(30.0)
    hour, minute = ClockFace.hand_angles(3, 15, 0)
    assert hour == pytest.approx(97.5)
    assert minute == pytest.approx(90.0)


def test_set_time_returns_valid_hands():
    face = ClockFace()
    hour_hand, minute_hand = face.set_time(3, 15)
    assert hour_hand.part is AvatarPart.HOUR_HAND
    assert minute_hand.part is AvatarPart.MINUTE_HAND
    assert hour_hand.length == pytest.approx(AvatarConfig().hour_hand_length)
    assert minute_hand.length == pytest.approx(AvatarConfig().minute_hand_length)
    assert minute_hand.angle_deg == pytest.approx(90.0)


def test_hand_endpoint_visible_math_coords():
    hand = ClockHandState(
        part=AvatarPart.HOUR_HAND, length=40.0, thickness=4.0, color="#000000", angle_deg=0.0
    )
    x, y = hand.endpoint()
    assert x == pytest.approx(0.0)
    assert y == pytest.approx(-40.0)  # 12 o'clock is up in math coordinates


def test_hands_fit_inside_radius():
    face = ClockFace()
    hour_hand, minute_hand = face.set_time(6, 30)
    for hand in (hour_hand, minute_hand):
        ClockFace.validate_hand(hand)
        assert hand.length < face.radius


def test_validate_hand_rejects_invalid():
    with pytest.raises(ValueError):
        ClockFace.validate_hand(
            ClockHandState(part=AvatarPart.MOUTH, length=10.0, thickness=2.0, color="#000000")
        )
    with pytest.raises(ValueError):
        ClockFace.validate_hand(
            ClockHandState(part=AvatarPart.HOUR_HAND, length=0.0, thickness=2.0, color="#000000")
        )


def test_hand_state_validation():
    with pytest.raises(ValidationError):
        ClockHandState(
            part=AvatarPart.HOUR_HAND,
            length=10.0,
            thickness=2.0,
            color="#000000",
            angle_deg=float("inf"),
        )
    with pytest.raises(ValidationError):
        ClockHandState(part=AvatarPart.HOUR_HAND, length=-1.0, thickness=2.0, color="#000000")


def test_transforms_for_include_pivot_and_hands():
    face = ClockFace()
    transforms = face.transforms_for(10, 10, scale=1.0)
    assert [t.part for t in transforms] == [
        AvatarPart.CENTER_PIVOT,
        AvatarPart.HOUR_HAND,
        AvatarPart.MINUTE_HAND,
    ]
    pivot = face.center_pivot()
    assert pivot.part is AvatarPart.CENTER_PIVOT
    assert pivot.scale == 1.0


def test_handed_angles_are_stable():
    face = ClockFace()
    assert face.set_time(12, 0)[0].angle_deg == pytest.approx(0.0)
    assert face.set_time(12, 0)[1].angle_deg == pytest.approx(0.0)
