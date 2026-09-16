# MISSMINUTES avatar engine (CHUNK 32)

The character-first desktop assistant interface: a **cute, compact cartoon
clock**. This document describes the character structure, visual design,
states, expressions, renderer/UI boundaries, asset organization, limitations
and the CHUNK 33 roadmap.

> **Design provenance:** the character is *inspired by* a user-supplied visual
> reference (a large circular orange clock character). The reference is used
> **only** as a design guide; it is **not** a copyrighted source asset and is
> **not** redistributed here. All proportions and colors are approximate
> original targets, fully adjustable via `AvatarConfig`.

---

## 1. Character structure

The character is composed of a mix of a clock and a person:

- **Clock body** — 1 large circular orange body that dominates the figure.
- **Clock face** — inner face disc with simple clock markings.
- **Clock hands** — hour hand, minute hand, center pivot (independent of
  expression rendering).
- **Arms** — 2 thin arms; **hands** — 2 round hands.
- **Legs** — 2 thin, short legs; **shoes/feet** — 2 orange shoes, larger than
  the legs.
- **Face** — 2 large expressive eyes with dark pupils, 1 small mouth, dark
  outlines.

Typed models live in `app/avatar/models.py`:

- `AvatarState` — idle, listening, thinking, working, speaking, happy,
  concerned, warning, success, error, sleeping, hidden.
- `AvatarPart` — named body parts (`CLOCK_BODY`, `LEFT_ARM`, `LEFT_SHOE`, …).
- `AvatarTransform` — validated per-part offset/rotation/scale.
- `AvatarPose` — posture snapshot (body bob/tilt, lean, arm swing, leg raise).

### Reference proportions

`AvatarProportions.from_config(config)` derives the following approximate
targets (documented, not measurements of a copyrighted asset):

| Ratio | Default | Design intent |
|---|---|---|
| body dominance | `body_width / (body_width + max(arm,leg) + shoe)` | the clock body dominates |
| arm thinness | `arm_thickness / body_width` | arms are thin relative to the body |
| leg thinness | `leg_thickness / body_width` | legs are thin |
| leg shortness | `leg_length / body_height` | legs are short |
| shoe to leg | `shoe_width / leg_length` | shoes are larger than legs |
| eye to body | `eye_size / body_width` | eyes are large |
| pupil to eye | `pupil_size / eye_size` | dark pupils fit the eyes |
| mouth to body | `mouth_size / body_width` | the mouth is small |

---

## 2. Visual design (AvatarConfig)

All appearance lives in `app/avatar/config.py` — nothing is hard-coded in the
state machine or controllers. Defaults implement the reference look:

- Solid orange body (`#FF8C2A`), dark outline (`#2A1A0F`), 6 px outline.
- Large white eyes with dark pupils; small dark mouth.
- Thin orange arms + round orange hands.
- Thin short orange legs + larger orange shoes (`#FFB84C`).
- Dark hour/minute hands and 12 simple clock markings, dark center pivot.

`AvatarConfig` validates everything: positive dimensions, hex colors,
pupil ≤ eye, hands fit inside the body radius, markings 1–72. Customization is
just a new `AvatarConfig`.

Data lives separately under `ui/avatar/assets/` (see §8).

---

## 3. State machine

`app/avatar/state_machine.py` — `AvatarStateMachine`

- Typed transitions via an explicit adjacency table.
- Required flows work: `idle → listening → thinking → working → speaking →
  success → idle` and `thinking → concerned → error`.
- Safe handling of invalid transitions: `try_transition()` returns `False`;
  `transition()` raises `AvatarTransitionError`.
- Tracks `previous` state; stores **no hidden global state**.
- Restrictive by design: `hidden` only returns to `idle`, `sleeping` wakes to
  `idle`/`hidden`, `success`/`error` are safe-rest states.

---

## 4. Expressions

`app/avatar/expression.py` — `AvatarExpression` + `ExpressionController`

Each expression controls:

- **eye openness** (0–1), **pupil position** (−1..1),
- **eyebrow lift** (0–1),
- **mouth shape** + **mouth openness**,
- **face tilt** / **body tilt** (degrees).

Predefined, data-driven expressions:

`neutral`, `happy`, `sad`, `concerned`, `surprised`, `thinking`, `focused`,
`warning`, `success`, `confused`.

They are mirrored as JSON in `ui/avatar/assets/expressions/expressions.json`
so the set can be edited without touching code.

---

## 5. Eyes and mouth

**Eyes** (`app/avatar/eyes.py`, `EyeController`):
- left/right look and up/down look (clamped to bounds),
- blink with configurable duration + periodic auto-blink,
- deterministic idle eye drift via an injected clock,
- provider-independent `EyeTrackingInput` boundary for future camera eye
  tracking — not required now; `FakeEyeTracker` is scripted for tests.

**Mouth** (`app/avatar/mouth.py`, `MouthController`):
- shapes: `closed`, `smile`, `open`, `concerned`, `surprised`,
- openness override hook for later lip motion.
- **No phoneme-level lip-sync yet (CHUNK 33).**

---

## 6. Body movement, limbs, clock face

**Animation** (`app/avatar/animation.py`): deterministic, configurable poses
for `idle` (bob + subtle tilt), `listening`, `thinking`, `working`, and a
single-shot `success` hop that emits an `ANIMATION_COMPLETED` event. All time
comes from an injected `now_fn`.

**Arms/legs** (`app/avatar/limbs.py`): typed `LimbState` for the left/right
arms and legs with safe hooks (`swing`, `raise_leg`, `reset`) and derived
`AvatarTransform`s from a pose. No walk cycle or detailed gestures yet.

**Clock face** (`app/avatar/clockface.py`): markings, hour/minute hand angles
from wall-clock time (`hand_angles`), and hand/pivot transforms — fully
independent of the facial expression system.

---

## 7. Renderer boundary

`app/avatar/renderer.py` — `AvatarRenderer` (ABC) + `FakeAvatarRenderer`

- The engine drives a renderer with `update_pose`, `update_expression`,
  `update_eyes`, `update_mouth`, `update_transform`, `set_clock_time` and
  `render_scene()`.
- Every real backend (SVG, Tkinter, Qt, HTML canvas, …) plugs in behind this
  boundary; nothing in the avatar logic knows about GUI frameworks.
- `FakeAvatarRenderer` deterministically composes the character as typed
  `RenderPrimitive`s (`circle`/`line`/`ellipse`) for offline tests and layout
  validation.
- `render_scene()` returns a typed `RenderFrame` (state, expression, pose,
  primitives, timestamp) and `close()` releases resources.

---

## 8. Window / UI boundary

`app/avatar/window.py` — `AvatarWindow` (ABC) + `FakeAvatarWindow`

Character-first presentation:

- `AvatarWindowConfig`: size, position, **always-on-top**,
  **transparent background**, visibility, `character_first` (minimal chrome —
  technical status stays secondary or hidden).
- Operations: `show`/`hide`, `set_position`/`set_size`, `set_always_on_top`,
  `paint`, `close`.
- `FakeAvatarWindow` records every operation and paints the renderer's most
  recent frame without re-rendering.

`AvatarController` shows the window on `start()` and hides/closes it on
`stop()`.

---

## 9. Character-first design

The avatar is the primary visible element. The interaction model:

```
User speaks → character listens → character thinks
            → character works/searches → character speaks
```

High-level `AvatarSignal`s (`LISTENING`, `THINKING`, `WORKING`, `SPEAKING`,
`SUCCESS`, `ERROR`, `CONCERNED`, `HIDE`) are translated by `AvatarController`
into state + expression + pose. Detailed AI internals never reach rendering.

---

## 10. Events

`app/avatar/events.py` — `AvatarEvent`, `AvatarEventType`, `AvatarEventLog`

- `avatar_started`, `avatar_stopped`, `state_changed`, `expression_changed`,
  `blink`, `look_changed`, `animation_started`, `animation_completed`.
- Bounded, sequentially numbered, timestamped, and **message-redacted** with
  the shared security redaction helpers (e.g. `password=hunter2` →
  `password=[REDACTED]`).

---

## 11. Controller & voice adapter

**`AvatarController`** (`app/avatar/controller.py`) is the single core
integration boundary. It owns the state machine, expression controller,
animation, eyes, mouth, clock, limbs, renderer, window and event log; exposes
`start`/`stop`, `handle(signal)`, `blink`, `look`, `set_clock_time`, `update`.

**`VoiceAvatarAdapter`** (`app/avatar/voice_adapter.py`) is the only place the
avatar layer reads voice types. It maps existing voice events
(`LISTENING_STARTED → listen`, `AI_STARTED → think`,
`SPEAKING_STARTED → speak`, `TURN_COMPLETED → success`,
`SPEAKING_INTERRUPTED → concerned`, `SESSION_CANCELLED → hide`, …) and voice
session states onto avatar signals. It never performs lip-sync and never
writes back to the voice pipeline.

---

## 12. Asset organization

Data/config and behaviour are separated:

```
ui/avatar/
├── assets/
│   ├── character/character.json   # AvatarConfig JSON (mirror of defaults)
│   ├── expressions/expressions.json# predefined expressions
│   └── ui/window.json             # window preferences
├── tests/README.md                # points to tests/unit
└── README.md                      # layout + attribution note
```

The runtime engine lives under `app/avatar/`; unit tests under
`tests/unit/test_avatar_*.py`. No copyrighted external assets are embedded;
the reference is documented as a design guide only.

---

## 13. Current limitations

- No phoneme-level lip-sync (mouth shapes are discrete).
- No walking cycle or detailed gesture animation (basic idle + swings only).
- No real GUI backend yet — the renderer/window boundaries ship with
  deterministic fakes.
- Eye tracking model exists but no camera integration.
- No AV-sync for spoken audio.

## 14. CHUNK 33 roadmap

- Detailed speech synchronization (phoneme/lip-sync driving mouth shapes).
- Advanced gestures and a walking cycle for arms/legs.
- Final voice↔avatar synchronization and streaming integration.
- A concrete desktop renderer/window backend behind the existing boundaries.

No CHUNK 33+ functionality was implemented in CHUNK 32.