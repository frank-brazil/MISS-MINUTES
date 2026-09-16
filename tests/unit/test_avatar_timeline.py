"""Deterministic animation timelines."""

import pytest

from app.avatar.timeline import AnimationTimeline, Easing, TimelineKeyframe, ease


def test_ease_linear():
    assert ease(0.0, Easing.LINEAR) == pytest.approx(0.0)
    assert ease(0.5, Easing.LINEAR) == pytest.approx(0.5)
    assert ease(1.0, Easing.LINEAR) == pytest.approx(1.0)


def test_ease_in():
    assert ease(0.0, Easing.EASE_IN) == pytest.approx(0.0)
    assert ease(0.5, Easing.EASE_IN) == pytest.approx(0.25)
    assert ease(1.0, Easing.EASE_IN) == pytest.approx(1.0)


def test_ease_out():
    assert ease(0.0, Easing.EASE_OUT) == pytest.approx(0.0)
    assert ease(0.5, Easing.EASE_OUT) == pytest.approx(0.75)
    assert ease(1.0, Easing.EASE_OUT) == pytest.approx(1.0)


def test_ease_in_out():
    assert ease(0.0, Easing.EASE_IN_OUT) == pytest.approx(0.0)
    assert ease(0.5, Easing.EASE_IN_OUT) == pytest.approx(0.5)
    assert ease(1.0, Easing.EASE_IN_OUT) == pytest.approx(1.0)


def test_ease_clamps():
    assert ease(-0.5, Easing.LINEAR) == pytest.approx(0.0)
    assert ease(2.0, Easing.LINEAR) == pytest.approx(1.0)


def test_keyframe_validation():
    with pytest.raises(Exception):
        TimelineKeyframe(time=-1.0, values={"x": 1.0})


def test_timeline_empty():
    timeline = AnimationTimeline()
    assert timeline.duration == 0.0
    assert timeline.playing is False
    assert timeline.play() is True
    assert timeline.playing is True
    result = timeline.evaluate(0.0)
    assert result == {}
    assert timeline.pause() is True
    assert timeline.playing is False


def test_timeline_play_pause():
    timeline = AnimationTimeline(
        [TimelineKeyframe(time=0.0, values={"x": 0.0}), TimelineKeyframe(time=1.0, values={"x": 1.0})],
        now_fn=lambda: 0.0,
    )
    assert timeline.play() is True
    assert timeline.playing is True
    assert timeline.play() is False  # already playing
    result = timeline.evaluate(0.5)
    assert result is not None
    assert result["x"] == pytest.approx(0.5)
    assert timeline.pause() is True
    assert timeline.playing is False
    assert timeline.evaluate(0.5) is None  # not playing


def test_timeline_completion():
    timeline = AnimationTimeline(
        [TimelineKeyframe(time=0.0, values={"x": 0.0}), TimelineKeyframe(time=1.0, values={"x": 10.0})],
        now_fn=lambda: 0.0,
    )
    timeline.play()
    result = timeline.evaluate(1.5)
    assert result is not None
    assert result["x"] == pytest.approx(10.0)
    assert timeline.playing is False  # auto-paused
    assert timeline.consume_completion() == "timeline"
    assert timeline.consume_completion() is None


def test_timeline_easing():
    timeline = AnimationTimeline(
        [TimelineKeyframe(time=0.0, values={"x": 0.0}, easing=Easing.LINEAR), TimelineKeyframe(time=1.0, values={"x": 1.0})],
        now_fn=lambda: 0.0,
    )
    timeline.play()
    result = timeline.evaluate(0.5)
    assert result is not None
    assert result["x"] == pytest.approx(0.5)


def test_timeline_cancel():
    timeline = AnimationTimeline(
        [TimelineKeyframe(time=0.0, values={"x": 0.0}), TimelineKeyframe(time=10.0, values={"x": 100.0})],
        now_fn=lambda: 0.0,
    )
    timeline.play()
    assert timeline.cancel() is True
    assert timeline.playing is False
    assert timeline.cancel() is False  # not playing


def test_timeline_deterministic():
    a = AnimationTimeline(
        [TimelineKeyframe(time=0.0, values={"x": 0.0}), TimelineKeyframe(time=1.0, values={"x": 1.0})],
        now_fn=lambda: 0.0,
    )
    b = AnimationTimeline(
        [TimelineKeyframe(time=0.0, values={"x": 0.0}), TimelineKeyframe(time=1.0, values={"x": 1.0})],
        now_fn=lambda: 0.0,
    )
    a.play()
    b.play()
    assert a.evaluate(0.3) == b.evaluate(0.3)


def test_timeline_add_keyframe():
    timeline = AnimationTimeline(now_fn=lambda: 0.0)
    timeline.add(TimelineKeyframe(time=0.0, values={"x": 0.0}))
    timeline.add(TimelineKeyframe(time=1.0, values={"x": 10.0}))
    timeline.play()
    result = timeline.evaluate(0.5)
    assert result is not None
    assert result["x"] == pytest.approx(5.0)
