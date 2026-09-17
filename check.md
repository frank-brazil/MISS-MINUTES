# MISSMINUTES CURRENT INTERFACE REPORT

## What Actually Exists

**API Server (FastAPI/uvicorn)** - Fully functional REST API on port 8000
- `/health` - health check
- `/` - root info
- `/runtime/status` - runtime capabilities and readiness
- `/tasks` - submit text tasks for orchestration
- `/voice/session` - voice pipeline endpoint (requires voice enabled)
- `/tasks/{task_id}/cancel` - task cancellation (not implemented)

**Avatar Engine (Backend Only)** - Complete animation/state engine in `app/avatar/`
- State machine with 11 states (idle, listening, thinking, working, speaking, success, error, concerned, warning, walking, hidden)
- Expression system with 11 predefined expressions
- Eye controller (blink, look, tracking boundary)
- Mouth controller (shapes: closed, smile, open, concerned, surprised)
- Lip-sync controller (approximate, viseme-driven)
- Gesture controller (explain, celebrate, warning, thinking_pose)
- Walking controller (forward/backward)
- Animation controller (idle, listening, thinking, working, success)
- Clock face (hands, markings, pivot)
- Event logging system

**Fake/Testing Infrastructure**
- `FakeAvatarRenderer` - deterministic primitive composer (circle/line/ellipse)
- `FakeAvatarWindow` - in-memory operation recorder
- `FakeEyeTracker` - scripted eye input for tests

**Configuration Assets** (data only, no rendering code)
- `ui/avatar/assets/character/character.json` - AvatarConfig JSON
- `ui/avatar/assets/expressions/expressions.json` - 11 expressions
- `ui/avatar/assets/ui/window.json` - window preferences

## UI Technology

| Layer | Technology | Status |
|-------|------------|--------|
| API | FastAPI + uvicorn | **FUNCTIONAL** |
| Web UI (HTML/CSS/JS) | None | **NOT IMPLEMENTED** |
| Desktop GUI (PySide/PyQt/Tkinter/Pygame) | None | **NOT IMPLEMENTED** |
| Avatar Renderer | Abstract base class only | **INTERFACE ONLY** |
| Avatar Window | Abstract base class only | **INTERFACE ONLY** |
| Actual Rendering Backend | None | **NOT IMPLEMENTED** |

## Avatar UI Status

| Feature | Implementation | Visual Output |
|---------|---------------|---------------|
| Real desktop window | ❌ No | N/A |
| Real renderer (GPU/CPU) | ❌ No | N/A |
| Avatar visible on screen | ❌ No | N/A |
| FakeAvatarRenderer | ✅ Yes | Structured primitives (JSON-like) |
| Expressions | ✅ Backend only | State changes only |
| Eyes (blink, look) | ✅ Backend only | State changes only |
| Mouth animation | ✅ Backend only | State changes only |
| Lip-sync | ✅ Approximate backend | Viseme state only |
| Gestures | ✅ Backend only | GestureFrame state only |
| Walking | ✅ Backend only | WalkingFrame state only |
| Voice-avatar integration | ✅ VoiceAvatarAdapter | Signal mapping only |

**REAL DISPLAY**: ❌ NONE
**SIMULATED/FAKE RENDERING**: ✅ `FakeAvatarRenderer` produces `RenderFrame` with `RenderPrimitive` tuples
**BACKEND STATE ONLY**: ✅ All animation state works, but no pixels on screen

## Dashboard Status

| Dashboard | Status |
|-----------|--------|
| Web dashboard | **NOT IMPLEMENTED** |
| Desktop dashboard | **NOT IMPLEMENTED** |
| Admin UI | **NOT IMPLEMENTED** |
| Monitoring UI | **NOT IMPLEMENTED** |

## API Status

| Endpoint | Status | Notes |
|----------|--------|-------|
| `GET /health` | ✅ WORKING | Returns `{"status":"ok"}` |
| `GET /` | ✅ WORKING | Returns name, version, status |
| `GET /runtime/status` | ✅ WORKING | Shows capabilities, uptime, request count |
| `POST /tasks` | ✅ WORKING | Text task orchestration (fake AI in headless) |
| `POST /voice/session` | ✅ EXISTS | Requires voice.enabled=true |
| `POST /tasks/{id}/cancel` | ⚠️ STUB | Returns "not yet supported" |

**Host**: 127.0.0.1 (configurable)
**Port**: 8000 (configurable)

## Available Launch Commands

| Command | Mode | Description |
|---------|------|-------------|
| `python main.py` | Normal | Starts API server with config (needs API keys for real AI) |
| `python main.py --headless` | Headless | Starts API server with ALL FAKES (no API keys needed) |
| `python main.py --port 9000` | Custom port | Override port |
| `python main.py --host 0.0.0.0` | Custom host | Override bind address |
| `python main.py --config path.toml` | Custom config | Load alternate TOML config |

**Entry point**: `missminutes` (via `pip install -e .`)

## Exact Steps To Open The Interface

### API Server (only working interface)

```powershell
cd C:\MISSMINUTES
.venv\Scripts\Activate.ps1
python main.py --headless
```

Server starts at `http://127.0.0.1:8000`

Test:
```powershell
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/tasks -H "Content-Type: application/json" -d "{\"description\": \"What is 2+2?\"}"
```

### Avatar Engine (programmatic only, no visual output)

```python
from app.avatar.controller import AvatarController, AvatarSignal
from app.avatar.renderer import FakeAvatarRenderer
from app.avatar.window import FakeAvatarWindow
from app.avatar.config import AvatarConfig

controller = AvatarController(
    renderer=FakeAvatarRenderer(AvatarConfig()),
    window=FakeAvatarWindow(),
    config=AvatarConfig()
)
controller.start()
controller.handle(AvatarSignal.LISTENING)
frame = controller.update()  # Returns RenderFrame with primitives
controller.stop()
```

## What I Should See On Screen

**API Server**: Terminal output showing uvicorn startup logs

**Avatar**: **NOTHING VISUAL** - No window opens, no pixels rendered. The `FakeAvatarWindow.visible` becomes `True` but it's an in-memory flag only. The `FakeAvatarRenderer.render_scene()` returns a `RenderFrame` dataclass containing `RenderPrimitive` tuples (circles, lines, ellipses) - this is structured data, not a displayed image.

## What Is Fake/Simulated

| Component | Reality |
|-----------|---------|
| Avatar window on desktop | **FAKE** - `FakeAvatarWindow` only records ops in memory |
| Avatar rendering | **FAKE** - `FakeAvatarRenderer` composes `RenderPrimitive` data structures |
| AI responses (headless) | **FAKE** - Returns "Headless response." |
| Voice STT/TTS | **FAKE** - `FakeSpeechToText` / `FakeTextToSpeech` |
| Research provider | **FAKE** - `FakeResearchProvider` |
| Language detection | **FAKE** - `FakeLanguageDetector` |
| Browser automation | **FAKE** unless `browser.enabled=true` + playwright |
| Distributed workers | **FAKE** unless `distributed.enabled=true` |

## What Is Actually Functional

- ✅ FastAPI REST API with lifespan management
- ✅ Runtime startup/shutdown with capability registry
- ✅ Orchestrator with agent routing (system, coding, prediction, critic, verification, research)
- ✅ Tool execution (calculator, system_info, terminal, filesystem)
- ✅ Security policy engine with audit trail
- ✅ SQLite memory persistence
- ✅ Avatar **backend engine** (state machine, expressions, eyes, mouth, gestures, walking, lip-sync, clock)
- ✅ Voice pipeline architecture (STT → AI → TTS with events)
- ✅ Voice→Avatar adapter (maps voice events to avatar signals)
- ✅ Deterministic test infrastructure (all fakes)
- ✅ Evaluation framework (15 scenario groups)

## What Is Not Implemented

| Missing Feature | Details |
|-----------------|---------|
| **Real GUI window** | No PySide/PyQt/Tkinter/Pygame/webview backend for `AvatarWindow` |
| **Real renderer** | No SVG/Canvas/WebGL/Skia backend for `AvatarRenderer` |
| **Web UI / Dashboard** | No HTML/CSS/JS frontend at all |
| **Phoneme-level lip-sync** | Only approximate viseme timing (CHUNK 33 roadmap) |
| **Walking cycle** | Basic forward/backward only, no full cycle |
| **Advanced gestures** | Only 4 gesture kinds implemented |
| **Eye tracking camera** | `EyeTrackingInput` boundary exists, no camera integration |
| **AV-sync for speech** | No audio↔animation synchronization |
| **Real AI providers** | Only fake AI in headless; OpenAI needs API key |
| **Real voice** | Requires OpenAI API keys for STT/TTS |
| **Persistent avatar process** | Avatar controller not auto-started by runtime (missing renderer/window injection) |

## Problems Preventing UI Launch

1. **No concrete `AvatarRenderer` implementation** - Only abstract base class + `FakeAvatarRenderer`
2. **No concrete `AvatarWindow` implementation** - Only abstract base class + `FakeAvatarWindow`
3. **Runtime doesn't inject renderer/window** - `_initialize_avatar()` creates `AvatarController(config=...)` without required `renderer` and `window` args → silently fails
4. **No GUI framework dependency** - pyproject.toml has no GUI dependencies (PySide6, PyQt6, tkinter, pygame, etc.)
5. **No web frontend assets** - No HTML/CSS/JS in repository
6. **Avatar disabled by default** - `config.avatar.enabled = false` in default TOML

## Recommended Next Step

To get a **visible avatar on screen**, implement a concrete renderer + window backend. Minimal path:

1. **Choose a GUI framework** (recommend: PySide6 for desktop, or web-based with FastAPI + WebSocket + HTML Canvas)
2. **Implement `AvatarRenderer` subclass** that draws `RenderPrimitive` tuples to a canvas
3. **Implement `AvatarWindow` subclass** that creates a real OS window with transparent background, always-on-top
4. **Wire into runtime** - Modify `_initialize_avatar()` to instantiate and inject the real renderer/window
5. **Enable in config** - Set `avatar.enabled = true`

**Estimated effort**: 2-3 days for basic PySide6 backend rendering the clock character with expressions/eyes/mouth animation.

---

**VISUAL INSPECTION NOT AVAILABLE** - No graphical interface exists to screenshot. The only runnable interface is the headless API server.