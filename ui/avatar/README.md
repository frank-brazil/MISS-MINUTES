# MISSMINUTES avatar asset layout

This folder keeps **data and configuration** separate from behaviour:

- `character/` — `AvatarConfig` JSON (body, colors, eyes, mouth, limbs, shoes,
  clock hands, markings). Mirrors the code defaults in
  `app/avatar/config.py`.
- `expressions/` — named expressions (`neutral`, `happy`, …). Mirrors
  `app/avatar/expression.py`.
- `ui/` — character-first window preferences (`AvatarWindowConfig`).

Behaviour (models, state machine, expression/eye/mouth controllers, animation,
clock face, renderer boundary, window boundary, controller, voice adapter)
lives in `app/avatar/`. Unit tests live in `tests/unit/test_avatar_*.py`.

> **Attribution notice (IMPORTANT):** the character design is inspired by a
> user-supplied visual reference (a large circular orange clock character).
> That reference is used **only** as a design guide — it is **not** a
> copyrighted source asset and it is **not** redistributed or embedded in this
> repository. All proportions/colors are approximate original targets.