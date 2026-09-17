"""Avatar controller: signals, lifecycle, direct controls and events."""

import pytest

from app.avatar.config import AvatarConfig
from app.avatar.controller import SIGNAL_MAP, AvatarController, AvatarSignal
from app.avatar.events import AvatarEventType
from app.avatar.models import AvatarPart, AvatarState
from app.avatar.renderer import FakeAvatarRenderer
from app.avatar.window import AvatarWindowConfig, FakeAvatarWindow


class Clock:
    value = 0.5


def _make_controller(
    window: bool = False,
) -> tuple[AvatarController, Clock, FakeAvatarRenderer, FakeAvatarWindow | None]:
    clock = Clock()
    renderer = FakeAvatarRenderer()
    win = FakeAvatarWindow(AvatarWindowConfig()) if window else None
    controller = AvatarController(renderer, window=win, now_fn=lambda: clock.value)
    return controller, clock, renderer, win


def test_signal_map_covers_signals():
    for signal in AvatarSignal:
        assert signal in SIGNAL_MAP


def test_start_lifecycle():
    controller, _, renderer, win = _make_controller(window=True)
    assert controller.start() is True
    assert controller.running is True
    assert controller.state is AvatarState.IDLE
    assert controller.expression == "neutral"
    assert win is not None and win.visible is True
    types = [event.event_type for event in controller.events.events()]
    assert AvatarEventType.AVATAR_STARTED in types
    assert AvatarEventType.EXPRESSION_CHANGED in types
    assert AvatarEventType.ANIMATION_STARTED in types
    assert controller.start() is False  # idempotent


def test_handle_requires_start():
    controller, _, _, _ = _make_controller()
    assert controller.handle(AvatarSignal.LISTENING) is False
    assert controller.blink() is False
    assert controller.look(0.0, 0.0) is False
    assert not controller.events.events()


def test_signal_chain_maps_state_and_expression():
    controller, clock, _, _ = _make_controller()
    controller.start()
    clock.value = 1.0
    chain = (
        (AvatarSignal.LISTENING, AvatarState.LISTENING, "focused"),
        (AvatarSignal.THINKING, AvatarState.THINKING, "thinking"),
        (AvatarSignal.WORKING, AvatarState.WORKING, "focused"),
        (AvatarSignal.SPEAKING, AvatarState.SPEAKING, "happy"),
        (AvatarSignal.SUCCESS, AvatarState.SUCCESS, "success"),
        (AvatarSignal.IDLE, AvatarState.IDLE, "neutral"),
    )
    for signal, state, expression in chain:
        assert controller.handle(signal) is True
        assert controller.state is state
        assert controller.expression == expression


def test_invalid_transition_returns_false_safely():
    controller, _, _, _ = _make_controller()
    controller.start()
    controller.handle(AvatarSignal.SUCCESS)
    before = controller.state
    count_before = controller.events.count()
    assert controller.handle(AvatarSignal.ERROR) is False  # SUCCESS -> ERROR invalid
    assert controller.state is before
    assert controller.events.count() == count_before


def test_hidden_signal_hides_window():
    controller, _, _, win = _make_controller(window=True)
    controller.start()
    assert controller.handle(AvatarSignal.HIDE) is True
    assert controller.state is AvatarState.HIDDEN
    assert win is not None and win.visible is False
    assert controller.handle(AvatarSignal.LISTENING) is False  # HIDDEN -> LISTENING invalid


def test_blink_records_event():
    controller, clock, renderer, _ = _make_controller()
    controller.start()
    controller.blink(duration=0.2)
    assert controller.events.events_of_type(AvatarEventType.BLINK)
    clock.value += 0.1
    controller.update()
    assert renderer._eyes.blinking is True  # mid-blink captured in the frame


def test_look_records_event_and_affects_pupils():
    controller, clock, renderer, _ = _make_controller()
    controller.start()
    controller.handle(AvatarSignal.WORKING)  # focused expression, pupil 0
    assert controller.look(1.0, 0.0) is True
    assert controller.events.events_of_type(AvatarEventType.LOOK_CHANGED)
    clock.value += 2.0  # let pupil interpolation converge to the target
    controller.update(now=controller.events.now)
    assert renderer._eyes.pupil_x == pytest.approx(1.0)


def test_look_clamps():
    controller, clock, _, _ = _make_controller()
    controller.start()
    controller.look(3.0, -2.0)
    clock.value += 2.0
    controller.update(now=clock.value)
    assert controller.eyes.state(clock.value).pupil_x == pytest.approx(1.0)


def test_set_clock_time_validation():
    controller, _, renderer, _ = _make_controller()
    controller.start()
    assert controller.set_clock_time(24, 0) is False
    assert controller.set_clock_time(12, 61) is False
    assert controller.set_clock_time(10, 10) is True
    assert renderer.calls[-1] == "set_clock_time"


def test_update_renders_and_paints_window():
    controller, clock, renderer, win = _make_controller(window=True)
    controller.start()
    frame = controller.update()
    assert frame == controller.frame()
    assert frame.frame_index >= 1
    assert win is not None and win.paint_count >= 1
    assert renderer.last_frame is frame
    assert win.last_frame is frame  # window paints the already-rendered frame


def test_animation_completed_after_success_hop():
    controller, clock, _, _ = _make_controller()
    controller.start()
    controller.handle(AvatarSignal.WORKING)
    controller.handle(AvatarSignal.SUCCESS)
    assert (
        controller.events.events_of_type(AvatarEventType.ANIMATION_STARTED)[-1].animation
        == "success"
    )
    clock.value += AvatarConfig().hour_hand_length  # irrelevant, just past 1.8s
    controller.update()
    completed = controller.events.events_of_type(AvatarEventType.ANIMATION_COMPLETED)
    assert len(completed) == 1
    assert completed[0].animation == "success"
    controller.update()
    assert len(controller.events.events_of_type(AvatarEventType.ANIMATION_COMPLETED)) == 1


def test_state_changed_events_include_previous():
    controller, _, _, _ = _make_controller()
    controller.start()
    controller.handle(AvatarSignal.LISTENING)
    controller.handle(AvatarSignal.THINKING)
    states = controller.events.events_of_type(AvatarEventType.STATE_CHANGED)
    assert states[0].state is AvatarState.LISTENING
    assert states[0].previous_state is AvatarState.IDLE
    assert states[1].previous_state is AvatarState.LISTENING


def test_expression_events_flow():
    controller, _, _, _ = _make_controller()
    controller.start()
    controller.handle(AvatarSignal.THINKING)
    expressions = controller.events.events_of_type(AvatarEventType.EXPRESSION_CHANGED)
    assert expressions[-1].expression == "thinking"
    assert controller.renderer.last_frame.expression == "thinking"


def test_stop_lifecycle():
    controller, _, renderer, win = _make_controller(window=True)
    controller.start()
    assert controller.stop() is True
    assert controller.running is False
    assert AvatarEventType.AVATAR_STOPPED in [e.event_type for e in controller.events.events()]
    assert renderer.closed is True
    assert win is not None and win.closed is True and win.visible is False
    assert controller.stop() is False


def test_color_config_propagates_to_renderer():
    controller, _, renderer, _ = _make_controller()
    controller.start()
    body = renderer.last_frame.primitives_for(AvatarPart.CLOCK_BODY)
    assert body and body[-1].color == AvatarConfig().body_color.lower()


def test_no_global_state_between_controllers():
    clock_a = Clock()
    a = AvatarController(FakeAvatarRenderer(), now_fn=lambda: clock_a.value)
    a.start()
    a.handle(AvatarSignal.LISTENING)
    b = AvatarController(FakeAvatarRenderer(), now_fn=lambda: 0.5)
    b.start()
    assert a.state is AvatarState.LISTENING
    assert b.state is AvatarState.IDLE


# -- CHUNK 33 integration tests -------------------------------------------


def test_walking_signal_emits_events_and_frames():
    controller, clock, renderer, _ = _make_controller()
    controller.start()
    clock.value += 1.0
    assert controller.handle(AvatarSignal.WALKING) is True
    assert controller.state is AvatarState.WALKING
    assert controller.events.events_of_type(AvatarEventType.WALKING_STARTED)
    frame = controller.last_frame
    assert frame is not None and frame.walking is not None
    assert frame.walking.state.value == "walking_forward"
    clock.value += 3.0
    assert controller.handle(AvatarSignal.IDLE) is True
    assert controller.events.events_of_type(AvatarEventType.WALKING_STOPPED)
    assert controller.walking.state.value == "standing"


def test_explaining_signal_starts_explain_gesture():
    controller, _, renderer, _ = _make_controller()
    controller.start()
    assert controller.handle(AvatarSignal.EXPLAINING) is True
    assert controller.state is AvatarState.EXPLAINING
    started = controller.events.events_of_type(AvatarEventType.GESTURE_STARTED)
    assert started and started[-1].gesture == "explain"
    frame = controller.last_frame
    assert frame is not None and frame.gesture is not None
    assert frame.gesture.kind.value == "explain"
    assert renderer.gesture is not None


def test_success_starts_celebrate_gesture_and_terminates():
    controller, clock, _, _ = _make_controller()
    controller.start()
    controller.handle(AvatarSignal.WORKING)
    controller.handle(AvatarSignal.SUCCESS)
    started = controller.events.events_of_type(AvatarEventType.GESTURE_STARTED)
    assert started and started[-1].gesture == "celebrate"
    clock.value += 3.0
    controller.update()
    finished = controller.events.events_of_type(AvatarEventType.GESTURE_FINISHED)
    assert finished and finished[-1].gesture == "celebrate"


def test_warning_starts_warning_gesture():
    controller, _, _, _ = _make_controller()
    controller.start()
    assert controller.handle(AvatarSignal.WARNING) is True
    started = controller.events.events_of_type(AvatarEventType.GESTURE_STARTED)
    assert started and started[-1].gesture == "warning"


def test_speak_emits_lipsync_events_and_viseme():
    controller, clock, renderer, _ = _make_controller()
    controller.start()
    clock.value += 1.0
    assert controller.speak("hello there") is True
    assert controller.state is AvatarState.SPEAKING
    assert controller.events.events_of_type(AvatarEventType.LIPSYNC_STARTED)
    frame = controller.last_frame
    assert frame is not None and frame.viseme is not None
    assert renderer._viseme is not None
    assert frame.viseme.accuracy.value == "approximate"
    timing = controller.lipsync.timing
    assert timing is not None and timing.duration_seconds > 0
    clock.value += timing.duration_seconds + 0.5
    controller.update()
    assert controller.events.events_of_type(AvatarEventType.LIPSYNC_FINISHED)


def test_interrupt_signal_cancels_lipsync():
    controller, clock, _, _ = _make_controller()
    controller.start()
    clock.value += 1.0
    controller.speak("long message here")
    assert controller.handle(AvatarSignal.INTERRUPTED) is True
    assert controller.state is AvatarState.INTERRUPTED
    assert controller.events.events_of_type(AvatarEventType.ANIMATION_INTERRUPTED)
    assert controller.events.events_of_type(AvatarEventType.LIPSYNC_FINISHED)
    assert controller.lipsync.active is False


def test_blink_started_and_finished_events():
    controller, clock, _, _ = _make_controller()
    controller.start()
    clock.value += 1.0
    controller.blink(duration=0.2)
    assert controller.events.events_of_type(AvatarEventType.BLINK)  # legacy
    clock.value += 0.1
    controller.update()
    assert controller.events.events_of_type(AvatarEventType.BLINK_STARTED)
    clock.value += 0.2
    controller.update()
    assert controller.events.events_of_type(AvatarEventType.BLINK_FINISHED)


def test_look_at_records_eye_target_event():
    from app.avatar.eyes import EyeTarget

    controller, _, _, _ = _make_controller()
    controller.start()
    assert controller.look_at(EyeTarget(x=0.5, y=-0.5)) is True
    assert controller.events.events_of_type(AvatarEventType.EYE_TARGET_CHANGED)
