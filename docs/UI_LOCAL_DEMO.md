# MISSMINUTES Local Demo Mode

## What Was Created

UI-02 created the first real local MISSMINUTES frontend shell. The interface is a dark, modern, character-first design with the clock-themed avatar as the main visual focus.

### Frontend Technology

**Vanilla HTML/CSS/JS + Jinja2 + SVG** — no framework, no build step.

### Frontend Location

```
app/api/
├── templates/
│   ├── base.html          # Base template (meta, CSS link)
│   ├── index.html         # Main UI (avatar, chat, sidebar)
│   ├── dashboard.html     # Dashboard page
│   └── settings.html      # Settings page
├── static/
│   ├── css/main.css       # Dark futuristic theme
│   └── js/
│       ├── api.js         # API client
│       ├── avatar.js      # SVG avatar renderer
│       ├── avatar-assets.js  # PNG expression overlay loader
│       ├── chat.js        # Chat flow
│       ├── sidebar.js     # System status panel
│       ├── task-viz.js    # Task pipeline visualization
│       └── dashboard.js   # Dashboard page logic
ui/avatar/assets/character/  # Avatar PNGs + character.json
```

## How to Start

```powershell
cd C:\MISSMINUTES

# Start in headless mode (all fakes, no API keys)
python main.py --headless

# Or start with default config
python main.py
```

### Local URL

```
http://127.0.0.1:8000
```

### Verify

```powershell
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" -d '{"message":"Hello Miss Minutes"}'
curl http://127.0.0.1:8000/api/avatar/state
curl http://127.0.0.1:8000/runtime/status
```

## How Demo Mode Works

- **No API keys required** — all AI responses use fake providers
- **No network access needed** — everything runs locally
- **Clear visual indicator** — "LOCAL DEMO MODE" badge displayed under avatar
- **Honest status labels** — services show "NOT CONNECTED" or "NOT CONFIGURED" when unavailable

## Architecture

```
Frontend (browser)
    |
    | fetch() JSON
    v
FastAPI endpoints (/api/chat, /runtime/status, /api/avatar/*)
    |
    v
MissMinutesRuntime (orchestrator + all subsystems)
    |
    v
AIModel ABC (isolates providers)
    |
    v
Concrete provider (OpenAI, Fake, Future)
```

The frontend never knows which AI provider is active.
