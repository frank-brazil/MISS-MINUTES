"""Core integration boundary: the avatar controller.

``AvatarController`` receives high-level signals (LISTENING, THINKING, WORKING,
SPEAKING, SUCCESS, ERROR, …) and translates them into state + expression +
pose + animation. It is the *only* component the voice adapter and future AI
integrations talk to — detailed AI internals never reach the renderer.
"""

import logging
import time
from enum import StrEnum
from typing import Callable, Mapping

from app.avatar import models as _m
from app.avatar.animation import AnimationConfig, AnimationController, AnimationMode
from app.avatar.clockface import ClockFace
from app.avatar.config import AvatarConfig
from app.avatar.events import AvatarEventLog, AvatarEventType
from app.avatar.expression import AvatarExpression, ExpressionController, ExpressionSet
from app.avatar.eyes import EyeConfig, EyeController, EyeTarget, EyeTrackingInput
from app.avatar.gestures import GestureController, GestureKind
from app.avatar.limbs import ArmsAndLegs
from app.avatar.lipsync import LipSyncController, LipSyncTiming
from app.avatar.mouth import MouthController, MouthShape
from app.avatar.movement import AvatarMovementController
from app.avatar.renderer import AvatarRenderer, RenderFrame
from app.avatar.state_machine import AvatarStateMachine
from app.avatar.tts_adapter import TTSLipSyncAdapter
from app.avatar.walking import WalkingController, WalkState
from app.avatar.window import AvatarWindow


class AvatarSignal(StrEnum):
    """High-level behaviour signals the controller accepts."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    WORKING = "working"
    SPEAKING = "speaking"
    SUCCESS = "success"
    ERROR = "error"
    CONCERNED = "concerned"
    WARNING = "warning"
    EXPLAINING = "explaining"
    WALKING = "walking"
    INTERRUPTED = "interrupted"
    HIDE = "hide"


SIGNAL_MAP: Mapping[AvatarSignal, tuple[_m.AvatarState, str]] = {
    AvatarSignal.IDLE: (_m.AvatarState.IDLE, "neutral"),
    AvatarSignal.LISTENING: (_m.AvatarState.LISTENING, "focused"),
    AvatarSignal.THINKING: (_m.AvatarState.THINKING, "thinking"),
    AvatarSignal.WORKING: (_m.AvatarState.WORKING, "focused"),
    AvatarSignal.SPEAKING: (_m.AvatarState.SPEAKING, "happy"),
    AvatarSignal.SUCCESS: (_m.AvatarState.SUCCESS, "success"),
    AvatarSignal.ERROR: (_m.AvatarState.ERROR, "concerned"),
    AvatarSignal.CONCERNED: (_m.AvatarState.CONCERNED, "concerned"),
    AvatarSignal.WARNING: (_m.AvatarState.WARNING, "warning"),
    AvatarSignal.EXPLAINING: (_m.AvatarState.EXPLAINING, "focused"),
    AvatarSignal.WALKING: (_m.AvatarState.WALKING, "neutral"),
    AvatarSignal.INTERRUPTED: (_m.AvatarState.INTERRUPTED, "concerned"),
    AvatarSignal.HIDE: (_m.AvatarState.HIDDEN, "neutral"),
}


class AvatarController:
    """Coordinates the full avatar engine from high-level signals."""

    def __init__(
        self,
        renderer: AvatarRenderer,
        *,
        window: AvatarWindow | None = None,
        config: AvatarConfig | None = None,
        expressions: Mapping[str, AvatarExpression] | None = None,
        events: AvatarEventLog | None = None,
        now_fn: Callable[[], float] | None = None,
        eye_input: EyeTrackingInput | None = None,
    ) -> None:
        self._logger = logging.getLogger(__name__)
        self._config = config or AvatarConfig()
        self._renderer = renderer
        self._window = window
        self._now_fn = now_fn or time.time
        self._events = events or AvatarEventLog(now_fn=self._now_fn)

        self._state_machine = AvatarStateMachine()
        self._expressions = ExpressionController(
            ExpressionSet(expressions) if expressions else None
        )
        self._animation = AnimationController(AnimationConfig(), now_fn=self._now_fn)
        self._eyes = EyeController(
            self._config, eye_config=EyeConfig(), now_fn=self._now_fn, tracking=eye_input
        )
        self._mouth = MouthController(mouth_size=self._config.mouth_size)
        self._clock = ClockFace(self._config)
        self._limbs = ArmsAndLegs(self._config)
        self._lipsync = LipSyncController(now_fn=self._now_fn)
        self._tts = TTSLipSyncAdapter(now_fn=self._now_fn)
        self._gestures = GestureController(now_fn=self._now_fn)
        self._walking = WalkingController(now_fn=self._now_fn)
        self._movement = AvatarMovementController(now_fn=self._now_fn)
        self._running = False
        self._applied_state: _m.AvatarState | None = None
        self._last_frame: RenderFrame | None = None
        self._last_gesture_kind: GestureKind | None = None
        self._was_blinking: bool = False
        self._lipsync_accuracy: str | None = None
        if window is not None:
            window.attach_renderer(renderer)
        self._push_limb_transforms()

    # -- lifecycle ---------------------------------------------------------

    @property
    def events(self) -> AvatarEventLog:
        return self._events

    @property
    def running(self) -> bool:
        return self._running

    @property
    def state(self) -> _m.AvatarState:
        return self._state_machine.state

    @property
    def previous_state(self) -> _m.AvatarState | None:
        return self._state_machine.previous

    @property
    def expression(self) -> str:
        return self._expressions.current

    @property
    def renderer(self) -> AvatarRenderer:
        return self._renderer

    @property
    def window(self) -> AvatarWindow | None:
        return self._window

    @property
    def last_frame(self) -> RenderFrame | None:
        return self._last_frame

    @property
    def clock(self) -> ClockFace:
        return self._clock

    @property
    def mouth(self) -> MouthController:
        return self._mouth

    @property
    def eyes(self) -> EyeController:
        return self._eyes

    @property
    def lipsync(self) -> LipSyncController:
        return self._lipsync

    @property
    def gestures(self) -> GestureController:
        return self._gestures

    @property
    def walking(self) -> WalkingController:
        return self._walking

    @property
    def movement(self) -> AvatarMovementController:
        return self._movement

    def start(self) -> bool:
        """Bring the character up. Returns ``False`` when already started."""
        if self._running:
            return False
        self._running = True
        self._animation.reset()
        self._state_machine.reset()
        self._events.record(AvatarEventType.AVATAR_STARTED, state=self.state)
        if self._window is not None:
            self._window.show()
        self._apply_expression("neutral")
        self._events.record(
            AvatarEventType.ANIMATION_STARTED,
            state=self.state,
            animation=AnimationMode.IDLE.value,
        )
        self.update()
        return True

    def stop(self) -> bool:
        """Take the character down. Returns ``False`` when not running."""
        if not self._running:
            return False
        self._running = False
        self._lipsync.stop()
        self._gestures.cancel_all()
        self._stop_walking()
        self._movement.stop()
        self._events.record(AvatarEventType.AVATAR_STOPPED, state=self.state)
        if self._window is not None:
            self._window.hide()
            self._window.close()
        self._renderer.close()
        return True

    # -- signals -----------------------------------------------------------

    def handle(self, signal: AvatarSignal) -> bool:
        """Translate a high-level signal into state + expression + pose.

        Returns ``False`` (safely, without raising) when the character is not
        started or the state transition is not allowed.
        """
        if not self._running:
            return False
        if signal not in SIGNAL_MAP:
            return False
        target_state, expression_name = SIGNAL_MAP[signal]
        if not self._state_machine.can_transition(target_state):
            self._logger.info("Avatar ignores signal %s from %s", signal.value, self.state.value)
            return False
        previous = self._state_machine.state
        self._state_machine.transition(target_state)
        self._events.record(
            AvatarEventType.STATE_CHANGED,
            state=self.state,
            previous_state=previous,
            message=f"signal={signal.value}",
        )
        self._apply_expression(expression_name)
        if signal is AvatarSignal.HIDE and self._window is not None:
            self._window.hide()
        mode = self._animation_mode_for(self.state)
        if mode is not None and self._animation.mode is not mode:
            self._animation.set_mode(mode)
            self._events.record(
                AvatarEventType.ANIMATION_STARTED,
                state=self.state,
                animation=mode.value,
            )
        if signal is AvatarSignal.WALKING:
            self._start_walking()
        elif previous is _m.AvatarState.WALKING:
            self._stop_walking()
        if signal is AvatarSignal.EXPLAINING:
            self._start_gesture(GestureKind.EXPLAIN)
        elif signal is AvatarSignal.SUCCESS:
            self._start_gesture(GestureKind.CELEBRATE)
        elif signal is AvatarSignal.WARNING:
            self._start_gesture(GestureKind.WARNING)
        elif signal is AvatarSignal.THINKING and not self._gestures.is_active():
            self._start_gesture(GestureKind.THINKING_POSE)
        elif previous is _m.AvatarState.THINKING and signal is not AvatarSignal.THINKING:
            self._stop_gesture(GestureKind.THINKING_POSE)
        if signal is AvatarSignal.INTERRUPTED:
            self._interrupt_animations()
        self.update()
        return True

    def interrupt(self) -> bool:
        """Interrupt animations/lip-sync and switch to the INTERRUPTED state."""
        if not self._running:
            return False
        return self.handle(AvatarSignal.INTERRUPTED)

    def _interrupt_animations(self) -> None:
        if self._lipsync.interrupt():
            self._logger.info("Avatar lip-sync interrupted")
        self._gestures.cancel_all()
        self._consume_finished_gesture_events()
        self._stop_walking()
        self._movement.stop()
        self._events.record(
            AvatarEventType.ANIMATION_INTERRUPTED,
            state=self.state,
        )
        self._set_mouth_from_expression(self._expressions.params())
        self._renderer.update_mouth(self._mouth.state())

    def _start_walking(self) -> None:
        if self._walking.start_forward():
            self._events.record(
                AvatarEventType.WALKING_STARTED,
                state=self.state,
                walking=WalkState.WALKING_FORWARD.value,
            )

    def _stop_walking(self) -> None:
        if self._walking.stop():
            self._events.record(
                AvatarEventType.WALKING_STOPPED,
                state=self.state,
                walking=WalkState.STANDING.value,
            )

    def _start_gesture(self, kind: GestureKind) -> None:
        self._gestures.start(kind)

    def _stop_gesture(self, kind: GestureKind) -> None:
        if self._gestures.cancel(kind):
            self._events.record(
                AvatarEventType.GESTURE_FINISHED, state=self.state, gesture=kind.value
            )

    def _consume_finished_gesture_events(self) -> None:
        while (finished := self._gestures.consume_finished()) is not None:
            self._events.record(
                AvatarEventType.GESTURE_FINISHED,
                state=self.state,
                gesture=finished.value,
            )

    def _animation_mode_for(self, state: _m.AvatarState) -> AnimationMode:
        mapping = {
            _m.AvatarState.LISTENING: AnimationMode.LISTENING,
            _m.AvatarState.THINKING: AnimationMode.THINKING,
            _m.AvatarState.WORKING: AnimationMode.WORKING,
            _m.AvatarState.SPEAKING: AnimationMode.IDLE,
            _m.AvatarState.SUCCESS: AnimationMode.SUCCESS,
            _m.AvatarState.IDLE: AnimationMode.IDLE,
        }
        return mapping.get(state, AnimationMode.IDLE)

    # -- direct controls ----------------------------------------------------

    def blink(self, duration: float | None = None) -> bool:
        """Trigger a character blink."""
        if not self._running:
            return False
        self._eyes.blink(duration)
        self._events.record(AvatarEventType.BLINK, state=self.state)
        return True

    def look(self, x: float, y: float) -> bool:
        """Set gaze direction (clamped)."""
        if not self._running:
            return False
        self._eyes.look(x, y)
        self._events.record(
            AvatarEventType.LOOK_CHANGED,
            state=self.state,
            message=f"look=({x:.2f},{y:.2f})",
        )
        return True

    def look_at(self, target: EyeTarget) -> bool:
        """Set gaze from a typed eye target."""
        if not self._running:
            return False
        self._eyes.look_at(target)
        self._events.record(AvatarEventType.EYE_TARGET_CHANGED, state=self.state)
        return True

    def walk_to(self, x: float, y: float) -> bool:
        """Request movement toward a point (requires the WALKING state)."""
        if not self._running:
            return False
        return self._movement.move_to(x, y)

    def speak(
        self,
        text: str,
        *,
        result: object | None = None,
        timing: LipSyncTiming | None = None,
    ) -> bool:
        """Speak ``text`` with lip-sync.

        ``result`` (a ``TextToSpeechResult`` or any object exposing
        ``success``/``duration``) anchors the timing; otherwise a deterministic
        text estimate is used. The controller never imports the voice layer.
        """
        if not self._running:
            return False
        cleaned = " ".join(str(text).split())
        if not cleaned:
            return False
        if self.state is not _m.AvatarState.SPEAKING:
            if not self.handle(AvatarSignal.SPEAKING):
                return False
        lip_timing = timing if timing is not None else self._tts.timing_for(cleaned, result)
        self._lipsync_accuracy = lip_timing.accuracy.value
        self._lipsync.start(cleaned, timing=lip_timing)
        self.update()
        return True

    def set_clock_time(self, hour: int, minute: int, second: int = 0) -> bool:
        """Point the clock hands at a wall-clock time."""
        if not (0 <= hour < 24 and 0 <= minute < 60 and 0 <= second <= 60):
            return False
        self._renderer.set_clock_time(hour, minute, second)
        return True

    def _set_mouth_from_expression(self, params: AvatarExpression) -> None:
        self._mouth.set(params.mouth_shape)
        if params.mouth_openness > 0:
            self._mouth.open(params.mouth_openness)

    def _apply_expression(self, name: str) -> None:
        params = self._expressions.apply(name)
        self._renderer.update_expression(name, params)
        self._set_mouth_from_expression(params)
        self._events.record(
            AvatarEventType.EXPRESSION_CHANGED,
            state=self.state,
            expression=name,
        )
        self._renderer.update_mouth(self._mouth.state())

    def _push_limb_transforms(self) -> None:
        for transform in self._limbs.transforms():
            self._renderer.update_transform(transform.part, transform)

    # -- frame ticking ------------------------------------------------------

    def _tick_lipsync(self, tick: float) -> None:
        viseme = self._lipsync.current(tick)
        self._renderer.update_viseme(viseme)
        if viseme is not None:
            self._mouth.set(MouthShape.SPEAKING)
            self._mouth.open(viseme.openness)
            self._renderer.update_mouth(self._mouth.state())
        event = self._lipsync.consume_event()
        if event is None:
            return
        if event == "started":
            self._events.record(
                AvatarEventType.LIPSYNC_STARTED,
                state=self.state,
                accuracy=self._lipsync_accuracy,
            )
        else:
            self._events.record(
                AvatarEventType.LIPSYNC_FINISHED,
                state=self.state,
                accuracy=self._lipsync_accuracy,
            )
            self._set_mouth_from_expression(self._expressions.params())
            self._renderer.update_mouth(self._mouth.state())

    def update(self, now: float | None = None) -> RenderFrame:
        """Advance animation/eyes/lip-sync/gestures/walking and render one frame."""
        tick = self._now_fn() if now is None else now
        pose = self._animation.update() if now is None else self._animation.pose(tick)

        walking_frame = self._walking.update(tick)
        if walking_frame is not None:
            pose = pose.model_copy(
                update={
                    "left_leg_raise": walking_frame.left_leg_raise,
                    "right_leg_raise": walking_frame.right_leg_raise,
                    "left_arm_swing": walking_frame.left_arm_swing,
                    "right_arm_swing": walking_frame.right_arm_swing,
                    "body_bob": pose.body_bob + walking_frame.bob,
                }
            )
        self._renderer.update_walking(walking_frame)

        gesture_frame = self._gestures.current(tick)
        if gesture_frame is not None:
            pose = pose.model_copy(
                update={
                    "left_arm_swing": gesture_frame.left_arm_swing,
                    "right_arm_swing": gesture_frame.right_arm_swing,
                    "body_tilt_deg": pose.body_tilt_deg + gesture_frame.body_tilt_deg,
                    "lean": pose.lean + gesture_frame.lean,
                }
            )
        active_kind = self._gestures.active.kind if self._gestures.active is not None else None
        if active_kind != self._last_gesture_kind:
            if active_kind is not None:
                self._events.record(
                    AvatarEventType.GESTURE_STARTED,
                    state=self.state,
                    gesture=active_kind.value,
                )
            self._last_gesture_kind = active_kind
        self._consume_finished_gesture_events()
        self._renderer.update_gesture(gesture_frame)

        self._movement.update(tick)
        self._renderer.update_pose(pose)
        for transform in self._limbs.transforms(pose):
            self._renderer.update_transform(transform.part, transform)
        eye_state = self._eyes.combine(self._eyes.state(tick), self._expressions.params())
        self._renderer.update_eyes(eye_state)
        if eye_state.blinking and not self._was_blinking:
            self._events.record(AvatarEventType.BLINK_STARTED, state=self.state)
        elif not eye_state.blinking and self._was_blinking:
            self._events.record(AvatarEventType.BLINK_FINISHED, state=self.state)
        self._was_blinking = eye_state.blinking

        completed = self._animation.consume_completion()
        if completed is not None:
            self._events.record(
                AvatarEventType.ANIMATION_COMPLETED,
                state=self.state,
                animation=completed,
            )
        self._tick_lipsync(tick)
        frame = self._renderer.render_scene()
        self._last_frame = frame
        if self._window is not None:
            self._window.paint()
        return frame

    def frame(self) -> RenderFrame | None:
        return self._last_frame
