"""Eye controller: look, blink, bounds and deterministic idle motion."""

import math

import pytest
from app.avatar.expression import AvatarExpression
from app.avatar.eyes import (
    EyeConfig,
    EyeController,
    EyeState,
    EyeTarget,
    EyeTrackingInput,
    FakeEyeTracker,
)
from pydantic import ValidationError


class _Clock:
    value = 10.0


def _new_clock() -> tuple[_Clock, EyeController]:
    clock = _Clock()
    controller = EyeController(
        now_fn=lambda: clock.value, eye_config=EyeConfig(auto_blink_period_seconds=0.0)
    )
    return clock, controller


def test_look_clamps_to_bounds():
    _, eyes = _new_clock()
    target = eyes.look(5.0, -5.0)
    assert target == EyeTarget(x=1.0, y=-1.0)
    assert eyes.look(-0.5, 0.25) == EyeTarget(x=-0.5, y=0.25)


def test_dynamic_pupil_prefers_manual_look():
    _, eyes = _new_clock()
    eyes.look(0.5, -0.5)
    assert eyes.dynamic_pupil(1.0) == EyeTarget(x=0.5, y=-0.5)


def test_clear_look_returns_to_idle_drift():
    clock, eyes = _new_clock()
    eyes.look(0.9, 0.4)
    eyes.clear_look()
    first = eyes.dynamic_pupil(clock.value)
    second = eyes.dynamic_pupil(clock.value)
    assert first == second  # deterministic idle drift
    assert math.hypot(first.x, first.y) <= 0.26
    assert -1.0 <= first.x <= 1.0 and -1.0 <= first.y <= 1.0


def test_dynamic_pupil_drifts_over_time():
    _, eyes = _new_clock()
    a = eyes.dynamic_pupil(1.0)
    b = eyes.dynamic_pupil(2.0)
    assert a != b


def test_tracking_input_overrides_manual_look():
    clock, eyes = _new_clock()
    tracker = FakeEyeTracker(targets=[EyeTarget(x=0.25, y=0.5)])
    eyes.look(0.9, -0.9)
    eyes.set_tracking(tracker)
    assert eyes.dynamic_pupil(clock.value) == EyeTarget(x=0.25, y=0.5)
    eyes.set_tracking(None)
    assert eyes.dynamic_pupil(clock.value) is not None


def test_blink_deterministic_curve():
    clock, eyes = _new_clock()
    eyes.blink(duration=0.2)
    assert eyes.is_blinking() is True  # just started
    assert eyes.state(clock.value).blinking is False  # openness still ~1.0
    clock.value += 0.1
    state = eyes.state(clock.value)
    assert state.blinking is True
    assert state.left_openness == pytest.approx(0.0)
    clock.value += 0.11
    assert eyes.is_blinking() is False
    assert eyes.state(clock.value).left_openness == pytest.approx(1.0)


def test_blink_invalid_duration_raises():
    _, eyes = _new_clock()
    with pytest.raises(ValueError):
        eyes.blink(duration=0.0)


def test_auto_blink_periodic():
    controller = EyeController(
        now_fn=lambda: 0.0,
        eye_config=EyeConfig(auto_blink_period_seconds=2.0, blink_duration=0.2),
    )
    assert controller.state(0.0).blinking is False  # nothing scheduled yet
    assert controller.state(2.05).blinking is True  # first auto blink underway
    assert controller.state(2.5).blinking is False  # blink finished, eyes open
    assert controller.state(4.05).blinking is True  # second auto blink fires


def test_auto_blink_disabled_when_period_zero():
    controller = EyeController(
        now_fn=lambda: 0.0, eye_config=EyeConfig(auto_blink_period_seconds=0.0)
    )
    assert controller.state(100.0).blinking is False
    assert controller.state(200.0).blinking is False


def test_auto_blink_jitter_is_deterministic_and_bounded():
    def make():
        return EyeController(
            now_fn=lambda: 0.0,
            eye_config=EyeConfig(auto_blink_period_seconds=2.0, blink_jitter_seconds=0.3),
        )

    first = make()
    second = make()
    first.state(0.0)
    second.state(0.0)
    assert first._next_auto_blink_at == second._next_auto_blink_at
    assert abs(first._next_auto_blink_at - 2.0) <= 0.3


def test_auto_blink_no_jitter_by_default():
    controller = EyeController(
        now_fn=lambda: 0.0, eye_config=EyeConfig(auto_blink_period_seconds=2.0)
    )
    controller.state(0.0)
    assert controller._next_auto_blink_at == pytest.approx(2.0)


def test_pupil_interpolation_moves_toward_target():
    _, eyes = _new_clock()
    eyes.look(1.0, 0.0)
    assert eyes.dynamic_pupil(0.0) == EyeTarget(x=1.0, y=0.0)  # first call snaps
    eyes.look(0.0, 0.0)
    moved = eyes.dynamic_pupil(0.5)
    assert 0.0 < moved.x < 1.0
    settled = eyes.dynamic_pupil(5.0)
    assert settled.x == pytest.approx(0.0, abs=0.001)


def test_interpolation_speed_zero_snaps():
    clock = _Clock()
    eyes = EyeController(
        now_fn=lambda: clock.value,
        eye_config=EyeConfig(auto_blink_period_seconds=0.0, interpolation_speed=0.0),
    )
    eyes.look(0.3, 0.2)
    assert eyes.dynamic_pupil(0.0) == EyeTarget(x=0.3, y=0.2)
    eyes.look(1.0, -1.0)
    clock.value += 2.0
    assert eyes.dynamic_pupil(clock.value) == EyeTarget(x=1.0, y=-1.0)


def test_look_directions():
    _, eyes = _new_clock()
    assert eyes.look_left() == EyeTarget(x=-0.6, y=0.0)
    assert eyes.look_right() == EyeTarget(x=0.6, y=0.0)
    assert eyes.look_up() == EyeTarget(x=0.0, y=-0.6)
    assert eyes.look_down() == EyeTarget(x=0.0, y=0.6)
    assert eyes.look_center() == EyeTarget(x=0.0, y=0.0)
    assert eyes.look_up_left() == EyeTarget(x=-0.5, y=-0.5)
    assert eyes.look_up_right() == EyeTarget(x=0.5, y=-0.5)


def test_look_at_sets_manual_target():
    _, eyes = _new_clock()
    target = EyeTarget(x=0.25, y=-0.4)
    assert eyes.look_at(target) == target
    assert eyes.dynamic_pupil(1.0) == target


def test_cancel_blink_opens_eyes():
    clock, eyes = _new_clock()
    eyes.blink(duration=0.2)
    clock.value += 0.1
    assert eyes.is_blinking() is True
    assert eyes.cancel_blink() is True
    assert eyes.is_blinking() is False
    assert eyes.state(clock.value).left_openness == pytest.approx(1.0)
    assert eyes.cancel_blink() is False  # nothing left to cancel


def test_eye_state_validation():
    with pytest.raises(ValidationError):
        EyeState(left_openness=1.5)
    with pytest.raises(ValidationError):
        EyeState(pupil_x=2.0)


def test_combine_adds_expression_pupil():
    _, eyes = _new_clock()
    state = eyes.state(10.0)
    expression = AvatarExpression(pupil_x=0.3, pupil_y=0.2)
    combined = eyes.combine(EyeState(), expression)
    assert combined.pupil_x == pytest.approx(0.3)
    assert combined.pupil_y == pytest.approx(0.2)
    with_expression = eyes.combine(state, expression)
    assert with_expression.pupil_x == pytest.approx(state.pupil_x + 0.3)
    clamped = eyes.combine(EyeState(pupil_x=0.9), AvatarExpression(pupil_x=0.5))
    assert clamped.pupil_x == 1.0


def test_fake_tracker_script():
    tracker = FakeEyeTracker(targets=[EyeTarget(x=0.1, y=0.2)])
    tracker.feed(EyeTarget(x=0.3, y=-0.4), None)
    assert tracker.read() == EyeTarget(x=0.1, y=0.2)
    assert tracker.read() == EyeTarget(x=0.3, y=-0.4)
    assert tracker.read() is None
    tracker.close()
    assert tracker.read() is None


def test_eye_config_validation():
    with pytest.raises(ValidationError):
        EyeConfig(blink_duration=-0.1)
    assert EyeConfig(auto_blink_period_seconds=0.0).auto_blink_period_seconds == 0.0


def test_tracking_input_abstract_guard():
    with pytest.raises(TypeError):

        class Incomplete(EyeTrackingInput):
            def read(self) -> EyeTarget | None:  # pragma: no cover
                return None


def test_close_releases_tracking():
    tracker = FakeEyeTracker(targets=[EyeTarget(x=0.1, y=0.1)])
    eyes = EyeController(tracking=tracker)
    eyes.close()
    assert tracker.read() is None
