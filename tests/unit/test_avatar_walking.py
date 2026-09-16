"""Walking system."""

import math

import pytest
from pydantic import ValidationError

from app.avatar.walking import WalkConfig, WalkState, WalkingController, WalkingFrame


def test_walk_config_validation():
    with pytest.raises(ValidationError):
        WalkConfig(step_period_seconds=-1.0)
    with pytest.raises(ValidationError):
        WalkConfig(step_amplitude_deg=0.0)


def test_walking_controller_defaults():
    controller = WalkingController()
    assert controller.state is WalkState.STANDING
    assert controller.walked_steps == 0.0
    assert controller.is_walking() is False


def test_walking_forward():
    controller = WalkingController(now_fn=lambda: 0.0)
    assert controller.start_forward() is True
    assert controller.state is WalkState.WALKING_FORWARD
    assert controller.is_walking() is True
    frame = controller.update(0.5)
    assert frame is not None
    assert frame.state is WalkState.WALKING_FORWARD
    assert frame.left_leg_raise > 0 or frame.right_leg_raise > 0
    assert frame.bob >= 0


def test_walking_backward():
    controller = WalkingController(now_fn=lambda: 0.0)
    assert controller.start_backward() is True
    assert controller.state is WalkState.WALKING_BACKWARD
    frame = controller.update(0.5)
    assert frame is not None
    assert frame.state is WalkState.WALKING_BACKWARD


def test_walking_turning():
    controller = WalkingController(now_fn=lambda: 0.0)
    assert controller.turn() is True
    assert controller.state is WalkState.TURNING
    frame = controller.update(0.5)
    assert frame is not None
    assert frame.state is WalkState.TURNING
    assert frame.left_leg_raise == 0.0
    assert frame.right_leg_raise == 0.0


def test_walking_stop():
    controller = WalkingController(now_fn=lambda: 0.0)
    controller.start_forward()
    assert controller.stop() is True
    assert controller.state is WalkState.STANDING
    assert controller.is_walking() is False
    assert controller.update(0.5) is None


def test_walking_accumulates_steps():
    controller = WalkingController(
        config=WalkConfig(step_period_seconds=1.0),
        now_fn=lambda: 0.0,
    )
    controller.start_forward()
    controller.update(1.0)
    assert controller.walked_steps == pytest.approx(1.0)
    controller.update(3.0)
    assert controller.walked_steps == pytest.approx(3.0)


def test_walking_distance():
    controller = WalkingController(now_fn=lambda: 0.0)
    controller.start_forward()
    controller.update(2.0)
    distance = controller.walked_distance(step_length=0.5)
    assert distance > 0


def test_walking_frame_deterministic():
    a = WalkingController(config=WalkConfig(step_period_seconds=1.0), now_fn=lambda: 0.0)
    b = WalkingController(config=WalkConfig(step_period_seconds=1.0), now_fn=lambda: 0.0)
    a.start_forward()
    b.start_forward()
    fa = a.update(0.75)
    fb = b.update(0.75)
    assert fa.left_leg_raise == fb.left_leg_raise
    assert fa.bob == fb.bob


def test_walking_start_idempotent():
    controller = WalkingController(now_fn=lambda: 0.0)
    assert controller.start_forward() is True
    assert controller.start_forward() is False  # already walking


def test_walking_stop_when_standing():
    controller = WalkingController()
    assert controller.stop() is False


def test_walking_reset():
    controller = WalkingController(now_fn=lambda: 0.0)
    controller.start_forward()
    controller.update(1.0)
    controller.reset()
    assert controller.state is WalkState.STANDING
    assert controller.walked_steps == 0.0
