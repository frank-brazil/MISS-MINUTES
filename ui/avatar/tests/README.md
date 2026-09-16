# CHUNK 32 avatar tests

The avatar engine is tested from `tests/unit/`:

- `test_avatar_config.py` — defaults, validation, customization, proportions
- `test_avatar_models.py` — states, parts, transforms, poses
- `test_avatar_state_machine.py` — valid/invalid transitions, history
- `test_avatar_expressions.py` — expressions + mouth
- `test_avatar_eyes.py` — look, blink, bounds, idle drift
- `test_avatar_animation.py` — deterministic poses + success hop
- `test_avatar_limbs.py` — limb transforms + hooks
- `test_avatar_clockface.py` — markings, hands, angles
- `test_avatar_renderer.py` — primitive composition + cleanup
- `test_avatar_window.py` — character-first window boundary
- `test_avatar_events.py` — avatar event log
- `test_avatar_controller.py` — signals, lifecycle, events
- `test_avatar_voice_adapter.py` — voice event mapping
- `test_avatar_assets.py` — JSON asset loaders/fallbacks
- `test_avatar_safety.py` — offline determinism, no foreign imports