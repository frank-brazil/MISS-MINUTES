"""Avatar movement controller."""

import pytest
from app.avatar.movement import AvatarMovementController, MovementConfig


def test_movement_config_validation():
    with pytest.raises(Exception):
        MovementConfig(speed=-1.0)


def test_movement_defaults():
    controller = AvatarMovementController()
    assert controller.position == (0.0, 0.0)
    assert controller.moving is False
    assert controller.target is None


def test_move_to():
    controller = AvatarMovementController(config=MovementConfig(speed=10.0), now_fn=lambda: 0.0)
    assert controller.move_to(10.0, 0.0) is True
    assert controller.moving is True
    assert controller.target == (10.0, 0.0)
    pos = controller.update(0.5)
    assert pos[0] > 0.0
    assert pos[1] == pytest.approx(0.0)


def test_move_completes():
    controller = AvatarMovementController(config=MovementConfig(speed=10.0), now_fn=lambda: 0.0)
    controller.move_to(10.0, 0.0)
    controller.update(2.0)  # distance 10, speed 10 → 2 seconds
    assert controller.moving is False
    assert controller.position == pytest.approx((10.0, 0.0))


def test_stop_freezes_position():
    controller = AvatarMovementController(config=MovementConfig(speed=10.0), now_fn=lambda: 0.0)
    controller.move_to(10.0, 0.0)
    controller.update(0.5)
    assert controller.stop() is True
    assert controller.moving is False
    pos = controller.position
    controller.update(1.0)
    assert controller.position == pos


def test_move_to_same_target_returns_false():
    controller = AvatarMovementController(now_fn=lambda: 0.0)
    controller.move_to(5.0, 5.0)
    assert controller.move_to(5.0, 5.0) is False


def test_reset():
    controller = AvatarMovementController(now_fn=lambda: 0.0)
    controller.move_to(10.0, 10.0)
    controller.update(0.5)
    controller.reset()
    assert controller.position == (0.0, 0.0)
    assert controller.moving is False
