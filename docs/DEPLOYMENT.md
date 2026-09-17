# MISSMINUTES Deployment Guide

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    MISSMINUTES                          │
│                                                         │
│  User Input (text/voice)                                │
│       │                                                 │
│       ▼                                                 │
│  ┌─────────┐    ┌────────────┐    ┌──────────┐         │
│  │ FastAPI  │───▶│ Orchestrator│───▶│ Agents   │         │
│  │  (port   │    │             │    │          │         │
│  │  8000)   │    │  ┌───────┐ │    │ Research │         │
│  └─────────┘    │  │Planner│ │    │ Coding   │         │
│                  │  └───────┘ │    │ System   │         │
│                  └─────┬──────┘    │ Vision   │         │
│                        │           │ Critic   │         │
│                        ▼           │ Verif.   │         │
│                  ┌──────────┐      └──────────┘         │
│                  │  Tools   │                            │
│                  │ Calc     │                            │
│                  │ Files    │                            │
│                  │ Terminal │                            │
│                  │ Browser  │                            │
│                  └──────────┘                            │
│                        │                                 │
│                        ▼                                 │
│                  ┌──────────┐      ┌──────────┐         │
│                  │ Security │      │  Memory  │         │
│                  │  Manager │      │ (SQLite) │         │
│                  └──────────┘      └──────────┘         │
│                                                         │
│  Optional: Voice → TTS/STT → Avatar                     │
│  Optional: Distributed Coordinator → Workers            │
└─────────────────────────────────────────────────────────┘
```

## Local Windows Setup

### Prerequisites

- Python 3.11 or later
- Git (optional)
- 2 GB free disk space

### Installation

```powershell
# Clone or copy the repository
cd C:\MISSMINUTES

# Create virtual environment
python -m venv .venv

# Activate (PowerShell)
.venv\Scripts\Activate.ps1

# Activate (Command Prompt)
.venv\Scripts\activate.bat

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

### Configuration

```powershell
# Copy environment template
Copy-Item .env.example .env

# Edit .env with your API keys (optional for headless/demo mode)
notepad .env
```

### Startup

```powershell
# Default startup (port 8000)
python main.py

# Custom host/port
python main.py --host 0.0.0.0 --port 9000

# Headless mode (no API keys needed, all fakes)
python main.py --headless

# Custom config file
python main.py --config path/to/config.toml
```

### Shutdown

Press `Ctrl+C` in the terminal. The application handles SIGINT and SIGTERM for graceful shutdown.

## Environment Configuration

All configuration flows through `config/missminutes.toml` with environment variable overrides.

### Application Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `MISSMINUTES_HOST` | `127.0.0.1` | Server bind address |
| `MISSMINUTES_PORT` | `8000` | Server port |
| `MISSMINUTES_LOG_LEVEL` | `INFO` | Logging level |
| `MISSMINUTES_ENV` | `development` | Environment name |

### AI Provider

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (none) | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o-mini` | Default AI model |

### Memory

| Variable | Default | Description |
|----------|---------|-------------|
| `MISSMINUTES_MEMORY_DB` | `data/missminutes_memory.db` | SQLite database path |

### Voice

| Variable | Default | Description |
|----------|---------|-------------|
| `MISSMINUTES_VOICE_ENABLED` | `false` | Enable voice subsystem |
| `MISSMINUTES_STT_MODEL` | `whisper-1` | Speech-to-text model |
| `MISSMINUTES_TTS_MODEL` | `tts-1` | Text-to-speech model |
| `MISSMINUTES_TTS_VOICE` | `alloy` | TTS voice name |

### Distributed

| Variable | Default | Description |
|----------|---------|-------------|
| `MISSMINUTES_DISTRIBUTED_ENABLED` | `false` | Enable distributed execution |
| `MISSMINUTES_MASTER_HOST` | `127.0.0.1` | Master bind address |
| `MISSMINUTES_MASTER_PORT` | `8100` | Master port |
| `MISSMINUTES_AUTH_TOKEN` | (none) | Shared auth token |

## Headless / CI Mode

```powershell
python main.py --headless
```

Or programmatically:

```python
from app.runtime.runtime import MissMinutesRuntime
from app.config.schema import MissMinutesConfig

runtime = MissMinutesRuntime.create_headless()
await runtime.startup()
# All subsystems use deterministic fakes
```

## Distributed Worker Setup

### 1. Coordinator / Master

```powershell
# Terminal 1: Start the master
$env:MISSMINUTES_DISTRIBUTED_ENABLED = "true"
$env:MISSMINUTES_MASTER_HOST = "127.0.0.1"
$env:MISSMINUTES_MASTER_PORT = "8100"
$env:MISSMINUTES_AUTH_TOKEN = "your-secret-token"

python main.py --port 8000
```

The master exposes distributed endpoints at `/distributed/*`:
- `POST /distributed/workers/register` — register a worker
- `POST /distributed/workers/heartbeat` — worker heartbeat
- `GET /distributed/workers` — list registered workers
- `POST /distributed/tasks` — submit a task
- `GET /distributed/tasks` — list tasks
- `DELETE /distributed/tasks/{task_id}` — cancel a task
- `GET /distributed/health` — distributed health check

### 2. Worker

```powershell
# Terminal 2: Start a worker
$env:MISSMINUTES_WORKER_HOST = "127.0.0.1"
$env:MISSMINUTES_WORKER_PORT = "8200"
$env:MISSMINUTES_AUTH_TOKEN = "your-secret-token"

python -c "
import asyncio
from app.distributed.config import DistributedConfig
from app.distributed.models import WorkerInfo, WorkerCapability
from app.distributed.service import WorkerService
from app.distributed.fakes import FakeWorkerExecutor, FakeMasterTransport

config = DistributedConfig.from_env()
worker = WorkerInfo(
    worker_name='worker-1',
    capabilities=[WorkerCapability(task_type='computation', priority=1)],
)
executor = FakeWorkerExecutor()
transport = FakeMasterTransport(master_url=f'http://127.0.0.1:{config.master_bind_port}')
service = WorkerService(worker_info=worker, executor=executor, config=config, master_transport=transport)
asyncio.run(service.register_with_master())
asyncio.run(service.heartbeat_loop())
"
```

### 3. Multiple Workers

Start additional workers with different `worker_name`, `worker_bind_port`, and capabilities.

### Worker Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MISSMINUTES_WORKER_HOST` | `127.0.0.1` | Worker bind address |
| `MISSMINUTES_WORKER_PORT` | `8200` | Worker port |
| `MISSMINUTES_HEARTBEAT_INTERVAL` | `15` | Heartbeat interval (seconds) |
| `MISSMINUTES_HEARTBEAT_TIMEOUT` | `30` | Heartbeat timeout (seconds) |
| `MISSMINUTES_MAX_RETRIES` | `2` | Max task retries |
| `MISSMINUTES_MAX_CONCURRENT_DISPATCH` | `4` | Max parallel dispatches |

## Health / Readiness Checks

```powershell
# Health check
curl http://127.0.0.1:8000/health
# Response: {"status": "ok"}

# Runtime status
curl http://127.0.0.1:8000/runtime/status
# Response: {"ready": true, "uptime_seconds": 1.23, "request_count": 0, "capabilities": {...}}

# Distributed health (when enabled)
curl http://127.0.0.1:8100/distributed/health
# Response: {"role": "master", "status": "ready", "workers": "0", "queued": "0"}
```

## Logging

Configure via `MISSMINUTES_LOG_LEVEL`:

- `DEBUG` — verbose diagnostic output
- `INFO` — normal operations (default)
- `WARNING` — degradation warnings only
- `ERROR` — errors only

Logs are structured with timestamps: `YYYY-MM-DD HH:MM:SS [LEVEL] logger: message`

### Security-Safe Logging

The logging system automatically redacts:
- API keys and tokens
- Authentication credentials
- Sensitive user content (transcripts stored as character counts only)

## Data / Storage Directories

| Directory | Purpose |
|-----------|---------|
| `data/memory/` | SQLite memory database |
| `data/documents/` | User document storage |
| `data/evaluation/` | Evaluation reports |
| `logs/` | Application logs |

Startup does NOT automatically delete existing data. Missing directories are created on first use.

## Security Checklist

- [ ] No API keys in source code
- [ ] `.env` is in `.gitignore`
- [ ] Auth token configured for networked workers
- [ ] Browser downloads restricted to allowed domains
- [ ] Filesystem access restricted to allowed roots
- [ ] Terminal commands go through security policy
- [ ] Audit logging enabled in production
- [ ] Confirmation required for high-risk actions

## Production Considerations

- **Never** expose MISSMINUTES with unrestricted terminal control to untrusted networks
- Set `MISSMINUTES_AUTH_TOKEN` for any distributed deployment
- Use `ConservativePolicy` or `DenyAllPolicy` in production
- Monitor audit logs for unusual activity
- Limit `audit_max_events` to prevent memory growth
- Use process managers (systemd, supervisord) for automatic restart

## Known Deployment Limitations

- Avatar/GUI features require a display server (not suitable for headless servers)
- Browser automation requires Playwright installation (`pip install playwright`)
- Voice features require microphone/speaker hardware
- SQLite memory is single-process only
- In-memory audit store does not persist across restarts

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: app` | Run `pip install -e .` from project root |
| `Port already in use` | Change port: `--port 9001` or set `MISSMINUTES_PORT` |
| `OPENAI_API_KEY not set` | Use `--headless` or set the key in `.env` |
| Browser tools fail | Install Playwright: `pip install playwright && playwright install` |
| Distributed worker won't connect | Verify `MISSMINUTES_AUTH_TOKEN` matches on both ends |
