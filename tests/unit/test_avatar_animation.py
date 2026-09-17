"""Animation controller: deterministic poses and the success hop."""

import math

import pytest
from pydantic import ValidationError

from app.avatar.animation import AnimationConfig, AnimationController, AnimationMode
from app.avatar.models import AvatarPose


class Clock:
    value = 0.0


def _controller() -> tuple[Clock, AnimationController]:
    clock = Clock()
    controller = AnimationController(now_fn=lambda: clock.value)
    return clock, controller


def _phase_offset(period: float) -> tuple[float, float]:
    """(quarter-period, amplitude reached at that offset) pattern."""
    return (period / 4.0, 1.0)


def test_idle_bob_is_deterministic_and_cyclic():
    clock, animation = _controller()
    zero = animation.pose(0.0)
    assert zero.body_bob == pytest.approx(0.0)
    quarter, factor = _phase_offset(animation.config.idle_bob_period_seconds)
    peak = animation.pose(clock.value + quarter)
    assert peak.body_bob == pytest.approx(animation.config.idle_bob_amplitude * factor)


def test_idle_tilt_is_subtle():
    _, animation = _controller()
    peak = animation.pose(animation.config.idle_tilt_period_seconds / 4.0)
    assert peak.body_tilt_deg == pytest.approx(animation.config.idle_tilt_amplitude)


def test_listening_pose_leans_forward():
    _, animation = _controller()
    animation.set_mode(AnimationMode.LISTENING)
    pose = animation.pose(0.25)
    assert pose.body_tilt_deg == animation.config.listening_tilt_deg
    assert pose.lean == animation.config.listening_lean
    assert pose.body_bob <= animation.config.listening_bob_amplitude


def test_thinking_pose_reclines():
    _, animation = _controller()
    animation.set_mode(AnimationMode.THINKING)
    pose = animation.pose(0.25)
    assert pose.body_tilt_deg == animation.config.thinking_tilt_deg
    assert pose.lean == animation.config.thinking_lean
    assert pose.face_tilt_deg == pytest.approx(-3.0)


def test_working_pose_focuses():
    _, animation = _controller()
    animation.set_mode(AnimationMode.WORKING)
    pose = animation.pose(0.25)
    assert pose.body_tilt_deg == animation.config.working_tilt_deg
    assert pose.lean == animation.config.working_lean


def test_success_hop_completes_once():
    clock, animation = _controller()
    assert animation.set_mode(AnimationMode.SUCCESS) is AnimationMode.IDLE
    # no completion at the start
    animation.pose(clock.value)
    assert animation.consume_completion() is None

    mid = clock.value + animation.config.success_hop_period_seconds / 2.0
    mid_pose = animation.pose(mid)
    assert mid_pose.body_bob == pytest.approx(animation.config.success_hop_amplitude)

    finished = clock.value + animation.config.success_duration_seconds + 0.1
    animation.pose(finished)
    assert animation.mode is AnimationMode.IDLE
    assert animation.consume_completion() == "success"
    assert animation.consume_completion() is None  # one-shot event


def test_set_mode_same_returns_none():
    _, animation = _controller()
    assert animation.set_mode(AnimationMode.IDLE) is None
    assert animation.mode is AnimationMode.IDLE


def test_update_uses_injected_clock():
    clock, animation = _controller()
    animation.set_mode(AnimationMode.LISTENING)
    clock.value = 0.5
    pose = animation.update()
    assert pose.body_tilt_deg == animation.config.listening_tilt_deg


def test_reset_restores_idle():
    clock, animation = _controller()
    animation.set_mode(AnimationMode.THINKING)
    animation.reset()
    assert animation.mode is AnimationMode.IDLE
    assert animation.consume_completion() is None
    assert animation.pose(clock.value) == AvatarPose(
        body_bob=0.0, body_tilt_deg=0.0
    ) or animation.pose(clock.value).body_bob == pytest.approx(0.0)


def test_pose_has_finite_values():
    _, animation = _controller()
    for mode in AnimationMode:
        animation.set_mode(mode)
        pose = animation.pose(1.234)
        for value in pose.model_dump().values():
            assert math.isfinite(value)


def test_config_validation():
    with pytest.raises(ValidationError):
        AnimationConfig(success_duration_seconds=0.0)
    with pytest.raises(ValidationError):
        AnimationConfig(idle_bob_amplitude=-3.0)
    with pytest.raises(ValidationError):
        AnimationConfig(working_tilt_deg=float("nan"))
