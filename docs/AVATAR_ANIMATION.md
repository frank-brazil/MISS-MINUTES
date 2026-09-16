# Avatar Animation System

> CHUNK 33 — lip-sync abstraction, blinking, eye movement, expressions, mouth animation,
> arm gestures, walking, movement controller, idle/reaction animations, timeline, and speaking
> synchronization with voice + interruption behavior.

---

## Overview

`app/avatar/` now provides a **complete deterministic animation engine** for the MISSMINUTES
clock avatar. Every subsystem is clock-driven (`now_fn` injected at construction) so
replay is exact and no async timers are used. The controller (`controller.py`) orchestrates
all subsystems: expressions, eyes, mouth, gestures, lip-sync, walking, and movement.

### Design Principles

| Principle | How it's enforced |
|---|---|
| **Determinism** | Every clock-dependent class accepts `now_fn: Callable[[], float]`. No `time.time()`. |
| **Off-line compatibility** | No GUI, no async, no real-time dependencies. All state is inspectable. |
| **Abstraction first** | ABCs for lip-sync providers, eye tracking, voice adapters. Concrete impls are swappable. |
| **Priority preemption** | Gestures and lip-sync compete for the "talking" slot via priority values. |
| **Deterministic replay** | `FakeAvatarRenderer`, `FakeEyeTracker`, `FakeInputDevice` all accept scripted inputs. |

---

## Architecture

```
AvatarController
├── AvatarState (15 states: IDLE, LISTENING, WORKING, THINKING, SUCCESS, ERROR,
│                 WARNING, CONFUSED, EXPLAINING, WALKING, SPEAKING, INTERRUPTED,
│                 HIDDEN, LOOKING, LOOKING_UP)
├── ExpressionController        ← expression name → AvatarExpression
├── EyeController               ← blink scheduling, direction, interpolation
├── MouthController             ← mouth shapes, animate(), openness
├── LipSyncController           ← speech-unit based viseme timing
├── GestureController           ← priority-queued arm gesture sequencing
├── WalkingController           ← sinusoidal leg/arm/bob cycles
├── AvatarMovementController    ← linear position interpolation
└── AnimationTimeline           ← keyframe animation playback
```

---

## Modules

### `models.py` — State & Config

- **`AvatarState`** — 15 values: `IDLE`, `LISTENING`, `WORKING`, `THINKING`, `SUCCESS`,
  `ERROR`, `WARNING`, `CONFUSED`, `EXPLAINING`, `WALKING`, `SPEAKING`, `INTERRUPTED`,
  `HIDDEN`, `LOOKING`, `LOOKING_UP`.
- **`AvatarPose`**, **`AvatarRendererState`**, **`AvatarConfig`**, **`Theme`** — unchanged from CHUNK 32.

### `state_machine.py` — Transitions

Full transition matrix for all 15 states. Key CHUNK 33 additions:
- `SPEAKING → INTERRUPTED` (voice cancellation)
- `WALKING → WARNING` (alert while walking)
- `IDLE → {EXPLAINING, WALKING, INTERRUPTED}` (new entry points)
- Invalid paths preserved: `HIDDEN → {IDLE}`, `SUCCESS → ERROR`

### `expression.py` — Expressions

- **`DEFAULT_EXPRESSIONS`** — "neutral", "listening", "thinking", "success", "error",
  "warning", "confused", "excited" (CHUNK 33 addition).
- Expressions apply offsets to eye openness, brow, mouth, head tilt, and pupil.
- `apply(state)` combines expression overlay with base eye/mouth state.

### `eyes.py` — Eye System

- **`EyeConfig`** — adds `interpolation_speed` (default 8.0) and `blink_jitter_seconds`
  (default 0.0). Auto-blink scheduled with interval + jitter.
- **`EyeController`** — manages auto-blink scheduling, manual blink curve (close 0–25%,
  hold 25–55%, reopen 55–100%), exponential interpolation toward target pupil, and
  direction shortcuts (`look_center/up/down/left/right/up_left/up_right`).
- **`look_at(target)`** — sets manual tracking target; interpolation runs toward it.
- **`cancel_blink()`** — snaps eyes open mid-blink.
- **`dynamic_pupil(now)`** — returns interpolated pupil position with exponential approach.
- **`blinking`** property — `True` when `openness < 0.98`.

### `mouth.py` — Mouth Animation

- **`MouthShape`** — 7 values: `NEUTRAL`, `OPEN`, `WIDE`, `NARROW`, `SMILE`,
  `SMALL_OPEN`, `SPEAKING`.
- **`MouthController`** — `animate(now)` oscillates openness for `SPEAKING` shape
  (`speaking_period_seconds=0.35`, range [0.15, 0.85]).

### `lipsync.py` — Lip-Sync Engine

- **`SpeechUnit`** — `symbol`, `start_time`, `duration`, computed `end_time`.
- **`TimingAccuracy`** — `EXACT` (with per-unit data) or `APPROXIMATE` (scaled).
- **`LipSyncTiming`** — list of `SpeechUnit`s + total `duration_seconds` + `accuracy`.
- **`VisemeState`** — current mouth shape: `symbol`, `openness`, `accuracy`, `timestamp`.
- **`LipSyncProvider`** — ABC: `timing_for(text, result?) → LipSyncTiming`.
- **`ApproximateLipSyncProvider`** — per-character unit generation, configurable `speaking_rate_wpm` (default 150).
- **`LipSyncController`** — `start(text, at?, timing?)`, `current(now)`, `stop()`, `interrupt()`.
  Consumable events: `"started"`, `"finished"`, `"interrupted"`.

### `tts_adapter.py` — Voice Bridge

- **`TTSLipSyncAdapter`** — `timing_for(text, result?)` scales units to match
  `result.duration.total_seconds()`. Always returns `APPROXIMATE` accuracy.
- Imports `app.voice.base.TextToSpeechResult` (fields: `success`, `audio`, `audio_ref`,
  `duration: timedelta | None`, `error`).
- `controller(text, result?, now_fn?)` — factory that returns a ready `LipSyncController`.

### `gestures.py` — Arm Gesture System

- **`GestureKind`** — 9 values: `WAVE`, `OPEN_HANDS`, `THINKING_POSE`, `SHRUG`,
  `POINT`, `CELEBRATE`, `STOP`, `WARNING`, `EXPLAIN`.
- **`GestureSpec`** — duration, priority (higher preempts lower), loop flag, interruptible,
  left/right arm start/end angles, body tilt, lean.
- **`GestureFrame`** — evaluated state: swing, lean, tilt, progress, repeat.
- **`GestureController`** — priority preemption, FIFO queue for lower-priority gestures,
  `consume_finished()` returns completed kind.
- **`GESTURE_SPECS`** — default specs for all 9 kinds.

### `timeline.py` — Keyframe Animation

- **`Easing`** — `LINEAR`, `EASE_IN`, `EASE_OUT`, `EASE_IN_OUT`.
- **`AnimationTimeline`** — play/pause/cancel, evaluates keyframe interpolation.
  Consumable completion events: `"timeline"`.
- Keyframes can be added dynamically with `add(keyframe)`.

### `walking.py` — Walking System

- **`WalkState`** — `STANDING`, `WALKING_FORWARD`, `WALKING_BACKWARD`, `TURNING`.
- **`WalkConfig`** — `step_period_seconds` (1.0), `leg_amplitude_deg` (35),
  `arm_amplitude_deg` (20), `bob_amplitude` (3.0).
- **`WalkingController`** — sinusoidal leg/arm/bob cycles, `walked_steps` accumulator,
  `walked_distance(step_length)` helper.

### `movement.py` — Position Controller

- **`MovementConfig`** — `speed` (10.0 units/sec).
- **`AvatarMovementController`** — linear interpolation toward target, `stop()` freezes,
  `reset()` returns to origin.

### `events.py` — Event System

10 new event types added in CHUNK 33:
`EYE_TARGET_CHANGED`, `BLINK_STARTED`, `BLINK_FINISHED`,
`GESTURE_STARTED`, `GESTURE_FINISHED`, `WALKING_STARTED`, `WALKING_STOPPED`,
`LIPSYNC_STARTED`, `LIPSYNC_FINISHED`, `ANIMATION_INTERRUPTED`.

`AvatarEvent` gains optional fields: `gesture`, `walking`, `accuracy`.

### `renderer.py` — Rendering Interface

New ABC methods: `update_viseme(viseme)`, `update_gesture(gesture)`,
`update_walking(walking)`. `FakeAvatarRenderer` implements all.
`RenderFrame` gains: `viseme`, `gesture`, `walking` optional fields.

### `controller.py` — Orchestrator

- **`AvatarSignal`** — 13 values: `START`, `IDLE`, `LISTENING`, `WORKING`, `THINKING`,
  `SUCCESS`, `ERROR`, `WARNING`, `CONFUSED`, `CANCEL`, `EXPLAINING`, `WALKING`,
  `INTERRUPTED`.
- `speak(text, result?, timing?)` — uses `TTSLipSyncAdapter` to generate timing, starts
  lip-sync.
- `interrupt()` → `handle(INTERRUPTED)`, cancels lipsync + gestures + walking + movement.
- `look_at(target)` → records `EYE_TARGET_CHANGED` event.
- Reaction gestures: `SUCCESS → celebrate`, `WARNING → warning`, `THINKING → thinking_pose`.
- Walking: `WALKING → start_forward()`, `IDLE → stop()`.
- Explaining: `EXPLAINING → start(explain gesture)`.
- Event consumption: blink lifecycle, gesture lifecycle, lipsync lifecycle all tracked.

---

## Integration Points

### Voice → Avatar

`voice_adapter.py` maps voice events to avatar signals:
- `SPEAKING_INTERRUPTED → AvatarSignal.INTERRUPTED` (voice cancelled mid-speech).
- `SESSION_STATE_MAP[INTERRUPTED] → AvatarState.INTERRUPTED`.

### Voice → LipSync

`TTSLipSyncAdapter` bridges `TextToSpeechResult` → `LipSyncTiming`. If the result has no
duration, a fallback timing is generated from character count and `speaking_rate_wpm`.

---

## Test Coverage

| Module | File | Tests |
|---|---|---|
| `lipsync.py` | `test_avatar_lipsync.py` | 12 |
| `tts_adapter.py` | `test_avatar_tts_adapter.py` | 6 |
| `gestures.py` | `test_avatar_gestures.py` | 11 |
| `walking.py` | `test_avatar_walking.py` | 12 |
| `movement.py` | `test_avatar_movement.py` | 7 |
| `timeline.py` | `test_avatar_timeline.py` | 13 |
| Controller integration | `test_avatar_controller.py` | 25 |

Full unit suite: **2231 collected, EXIT=0**.

---

## Non-Goals (CHUNK 33)

- No full system integration test across voice + avatar + GUI.
- No GUI redesign or deployment/packaging changes.
- No distributed architecture or message queue integration.
- No lip-sync accuracy claims beyond "APPROXIMATE" without real timing data.
- No pathfinding or obstacle avoidance.

---

## File Inventory

### New Files (CHUNK 33)

| File | Purpose |
|---|---|
| `app/avatar/lipsync.py` | Lip-sync timing, controller, provider ABC |
| `app/avatar/tts_adapter.py` | TTS result → lip-sync timing bridge |
| `app/avatar/gestures.py` | Arm gesture specs, controller, FIFO queue |
| `app/avatar/timeline.py` | Keyframe animation playback |
| `app/avatar/walking.py` | Walking state machine + sinusoidal cycles |
| `app/avatar/movement.py` | Linear position controller |
| `tests/unit/test_avatar_lipsync.py` | Lip-sync unit tests |
| `tests/unit/test_avatar_tts_adapter.py` | TTS adapter unit tests |
| `tests/unit/test_avatar_gestures.py` | Gesture unit tests |
| `tests/unit/test_avatar_walking.py` | Walking unit tests |
| `tests/unit/test_avatar_movement.py` | Movement unit tests |
| `tests/unit/test_avatar_timeline.py` | Timeline unit tests |
| `docs/AVATAR_ANIMATION.md` | This document |

### Modified Files (CHUNK 33)

| File | Changes |
|---|---|
| `app/avatar/models.py` | +3 states: WALKING, EXPLAINING, INTERRUPTED |
| `app/avatar/state_machine.py` | Transitions for 3 new states, INTERRUPTED on SPEAKING, WARNING on WORKING |
| `app/avatar/expression.py` | "excited" in DEFAULT_EXPRESSIONS |
| `app/avatar/mouth.py` | +2 shapes: SMALL_OPEN, SPEAKING; animate() oscillation |
| `app/avatar/eyes.py` | Full rewrite: interpolation, blink scheduling, direction methods, look_at, cancel_blink |
| `app/avatar/events.py` | +10 event types; gesture/walking/accuracy fields on AvatarEvent |
| `app/avatar/renderer.py` | +3 ABC methods; fake impls; RenderFrame gains viseme/gesture/walking |
| `app/avatar/controller.py` | Full rewrite: 13 signals, speak(), interrupt(), look_at(), full integration |
| `app/avatar/voice_adapter.py` | SPEAKING_INTERRUPTED→INTERRUPTED; SESSION_STATE_MAP INTERRUPTED→INTERRUPTED |
| `app/avatar/__init__.py` | ~72 exports |
| `ui/avatar/assets/expressions/expressions.json` | "excited" entry |

### Updated Test Files (CHUNK 33)

| File | Changes |
|---|---|
| `tests/unit/test_avatar_models.py` | +3 states |
| `tests/unit/test_avatar_expressions.py` | +excited expression, +2 mouth shapes, animate tests |
| `tests/unit/test_avatar_events.py` | +10 event types |
| `tests/unit/test_avatar_voice_adapter.py` | INTERRUPTED mapping |
| `tests/unit/test_avatar_eyes.py` | Auto-blink new semantics, direction/look_at/cancel_blink/interpolation |
| `tests/unit/test_avatar_controller.py` | Clock advance fixes + 7 new integration tests |
| `tests/unit/test_avatar_safety.py` | tts_adapter.py whitelisted |
