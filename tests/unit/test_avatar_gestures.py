"""Arm gestures and sequencing controller."""

import pytest
from pydantic import ValidationError

from app.avatar.gestures import (
    GESTURE_SPECS,
    GestureController,
    GestureFrame,
    GestureKind,
    GestureSpec,
)


def test_gesture_specs_all_present():
    for kind in GestureKind:
        assert kind in GESTURE_SPECS
        spec = GESTURE_SPECS[kind]
        assert spec.kind is kind


def test_gesture_spec_validation():
    with pytest.raises(ValidationError):
        GestureSpec(kind=GestureKind.WAVE, duration=-1.0)
    with pytest.raises(ValidationError):
        GestureSpec(kind=GestureKind.WAVE, priority=-1)
    with pytest.raises(ValidationError):
        GestureSpec(kind=GestureKind.WAVE, left_arm_start=100.0)
    with pytest.raises(ValidationError):
        GestureSpec(kind=GestureKind.WAVE, body_tilt_deg=90.0)
    with pytest.raises(ValidationError):
        GestureSpec(kind=GestureKind.WAVE, lean=2.0)


def test_gesture_frame_validation():
    with pytest.raises(ValidationError):
        GestureFrame(kind=GestureKind.WAVE, name="wave", progress=1.5, left_arm_swing=0.0, right_arm_swing=0.0, body_tilt_deg=0.0, lean=0.0, timestamp=0.0)
    with pytest.raises(ValidationError):
        GestureFrame(kind=GestureKind.WAVE, name="wave", progress=0.5, left_arm_swing=100.0, right_arm_swing=0.0, body_tilt_deg=0.0, lean=0.0, timestamp=0.0)


def test_gesture_controller_start_and_current():
    controller = GestureController(now_fn=lambda: 0.0)
    assert controller.is_active() is False
    assert controller.start(GestureKind.WAVE) is True
    assert controller.is_active() is True
    frame = controller.current(0.5)
    assert frame is not None
    assert frame.kind is GestureKind.WAVE
    assert 0.0 <= frame.progress <= 1.0
    assert frame.left_arm_swing != 0.0


def test_gesture_priority_preemption():
    controller = GestureController(now_fn=lambda: 0.0)
    controller.start(GestureKind.WAVE)  # priority 20
    assert controller.active.kind is GestureKind.WAVE
    controller.start(GestureKind.CELEBRATE)  # priority 90 > 20
    assert controller.active.kind is GestureKind.CELEBRATE


def test_gesture_queue_fifo():
    controller = GestureController(now_fn=lambda: 0.0)
    controller.start(GestureKind.CELEBRATE)  # priority 90, active
    controller.start(GestureKind.WAVE)  # priority 20, queued (can't preempt higher priority)
    assert controller.active.kind is GestureKind.CELEBRATE
    assert controller.queue_length() == 1
    controller.current(2.0)  # CELEBRATE duration 1.4, finished
    assert controller.active.kind is GestureKind.WAVE


def test_gesture_cancel():
    controller = GestureController(now_fn=lambda: 0.0)
    controller.start(GestureKind.WAVE)
    assert controller.cancel(GestureKind.WAVE) is True
    assert controller.is_active() is False


def test_gesture_cancel_all():
    controller = GestureController(now_fn=lambda: 0.0)
    controller.start(GestureKind.WAVE)
    controller.start(GestureKind.POINT)
    controller.cancel_all()
    assert controller.is_active() is False
    assert controller.queue_length() == 0


def test_gesture_loop():
    controller = GestureController(now_fn=lambda: 0.0)
    controller.start(GestureKind.WAVE)  # loop=True
    frame1 = controller.current(0.5)
    frame2 = controller.current(1.5)
    assert frame1 is not None
    assert frame2 is not None
    assert frame2.repeat >= 1
    assert controller.is_active() is True


def test_gesture_consume_finished():
    controller = GestureController(now_fn=lambda: 0.0)
    controller.start(GestureKind.POINT)  # duration 0.9
    controller.current(1.0)  # finishes POINT
    assert controller.consume_finished() is GestureKind.POINT
    assert controller.consume_finished() is None


def test_gesture_non_interruptible_blocks_preemption():
    controller = GestureController(now_fn=lambda: 0.0)
    spec = GESTURE_SPECS[GestureKind.WARNING].model_copy(update={"interruptible": False})
    controller._active = spec
    controller._started_at = 0.0
    controller.start(GestureKind.CELEBRATE)  # higher priority but can't preempt
    assert controller.active.kind is GestureKind.WARNING
