# MISSMINUTES Integration Architecture

This document describes how the MISSMINUTES subsystems are integrated into a
coherent application as of CHUNK 34.

## Architecture Overview

```
                    USER
                     |
          +----------+----------+
          |                     |
        VOICE                  TEXT
          |                     |
          +----------+----------+
                     |
                INPUT LAYER
                     |
                     v
              ORCHESTRATOR
                     |
        +------------+-------------+
        |            |             |
      Memory      Planner       Context
        |            |             |
        +------------+-------------+
                     |
                Agent Router
                     |
       +------+------+------+------+------+
       |      |      |      |      |      |
    Research Coding Vision Prediction Critic
       |                              Verifier
       +--------------+------------------+
                      |
                Action Boundary
                      |
        +-------------+-------------+
        |             |             |
     Computer      Browser       Distributed
       Tools         Tools         Workers
        |             |             |
        +-------------+-------------+
                      |
                  Observation
                      |
                  Verification
                      |
              Final Result / Response
                      |
                +-----+------+
                |            |
              Voice       Avatar/UI
                |            |
                +-----+------+
                      |
                     USER
```

## Runtime Container

`MissMinutesRuntime` (`app/runtime/runtime.py`) is the central application
container. It owns all major services and coordinates lifecycle.

### Startup Sequence

```
startup()
  → load security policy
  → initialize memory (SQLite)
  → create Orchestrator (AI model, memory, security)
  → register agents (system, coding, research, prediction, critic, verification)
  → register tools (calculator, filesystem, terminal, browser if enabled)
  → initialize voice service (if enabled)
  → initialize avatar controller (if enabled)
  → take capability snapshot
  → ready
```

### Shutdown Sequence

```
shutdown()
  → stop voice sessions
  → stop avatar
  → stop browser sessions
  → stop distributed services
  → flush memory
  → not ready
```

Both startup and shutdown are **idempotent** — repeated calls are safe.

## Configuration

Configuration is loaded from `config/missminutes.toml` with environment
variable overrides. The `MissMinutesConfig` Pydantic model provides typed
access to all settings.

### Config Sections

| Section | Key Settings |
|---------|-------------|
| `ai` | provider, model, timeout |
| `voice` | enabled, stt/tts provider, language mode |
| `avatar` | enabled, theme, window behavior |
| `security` | policy_mode, confirmation_required, audit settings |
| `distributed` | enabled, master/worker config, auth token |
| `browser` | enabled, allowed domains |
| `filesystem` | allowed roots |
| `vision` | enabled, provider |

Secrets (API keys, auth tokens) are **never** stored in config files. They
are read from environment variables at provider construction time.

## Request Flow

### Text Request

```
handle_text("Find my DSA notes")
  → UnifiedRequest(source="text")
  → create Task
  → Orchestrator.execute(task)
  → AI tool-calling loop (or planner+agents, or problem-solving engine)
  → OrchestrationResult
  → UnifiedResponse
```

### Voice Request

```
handle_voice(audio_bytes)
  → UnifiedRequest(source="voice")
  → VoiceConversationService.handle(voice_request)
    → STT → Language Detection → AI Chat → TTS
  → Voice events → AvatarController (via VoiceAvatarAdapter)
  → UnifiedResponse (text + audio)
```

## Agent Registration

At startup, agents are registered based on available subsystems:

| Agent | Always Available | Requires |
|-------|-----------------|----------|
| SystemAgent | Yes | — |
| CodingAgent | Yes | — |
| ResearchAgent | Yes | ResearchProvider for full capability |
| PredictionAgent | Yes | — (uses FakePredictor) |
| CriticAgent | Yes | — (uses FakeCritic) |
| VerificationAgent | Yes | — (uses FakeVerifier) |
| VisionAgent | No | vision.enabled config |

No duplicate agent names are allowed (enforced by AgentRouter).

## Tool Registration

All tools retain their CHUNK 30 security metadata (`ToolPermission`).

| Tool | Always Available | Requires |
|------|-----------------|----------|
| CalculatorTool | Yes | — |
| SystemInfoTool | Yes | — |
| ApprovedTerminalTool | Yes | — |
| FileReadTool | Yes | filesystem.allowed_roots |
| FileCreateTool | Yes | filesystem.allowed_roots |
| FileEditTool | Yes | filesystem.allowed_roots |
| FileSearchTool | Yes | filesystem.allowed_roots |
| ScreenshotTool | No | vision.enabled |
| BrowserOpenTool | No | browser.enabled |
| BrowserReadTool | No | browser.enabled |
| BrowserClickTool | No | browser.enabled |
| BrowserTypeTool | No | browser.enabled |
| BrowserDownloadTool | No | browser.enabled |

## Security Boundary

Security is the central gate before all actions. The pipeline:

```
request → SecurityPolicy → ALLOW / DENY / CONFIRMATION_REQUIRED → Action
```

Every path (voice, text, browser, agent, worker) follows the same policy
model. No bypass routes exist.

## Voice → Avatar Integration

Voice events are mapped to avatar signals via `VoiceAvatarAdapter`:

| Voice Event | Avatar Signal |
|-------------|--------------|
| LISTENING_STARTED | LISTENING |
| TRANSCRIPTION_STARTED | THINKING |
| AI_STARTED | THINKING |
| SPEAKING_STARTED | SPEAKING |
| SPEAKING_STOPPED | IDLE |
| SPEAKING_INTERRUPTED | INTERRUPTED |
| TURN_COMPLETED | SUCCESS |
| TURN_ERROR | ERROR |

The adapter is a one-way mapping — the avatar never influences the voice
pipeline.

## Health / Readiness

`GET /runtime/status` returns:

```json
{
  "ready": true,
  "uptime_seconds": 123.4,
  "request_count": 42,
  "capabilities": {
    "text": true,
    "voice": false,
    "avatar": false,
    "browser": false,
    "vision": false,
    "distributed": false,
    "memory": true,
    "security": true,
    "agents": true
  }
}
```

## Headless Mode

`MissMinutesRuntime.create_headless(config)` creates a runtime with all fakes:

- FakeAIModel
- FakeSpeechToText / FakeTextToSpeech
- FakeLanguageDetector
- FakeResearchProvider
- FakeActionExecutor / FakeObservationProvider

No hardware, no network required. Suitable for CI/tests.

## Audit Trail

Every request is tracked through safe metadata stages:

```
accepted → planning_started → task_created → verification_completed → response_generated
```

Never logged: API keys, passwords, raw audio, raw screenshots, chain-of-thought.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Root info |
| GET | `/health` | Health check |
| POST | `/tasks` | Submit a task (legacy) |
| GET | `/runtime/status` | Runtime status + capabilities |
| POST | `/voice/session` | Voice request |
| POST | `/tasks/{id}/cancel` | Cancel task (stub) |

## Limitations

- Task cancellation is not yet implemented (stub endpoint)
- Hot-reload of configuration requires restart
- Voice interruption is handled at the avatar level only
- Distributed rerouting depends on the coordinator's staleness detection
- Browser tools require Playwright (optional dependency)
