# MISSMINUTES

Personal intelligent AI computer agent.

## Architecture

```
USER → VOICE/TEXT → Orchestrator → Agents → Tools → Result → Voice/Avatar
                         ↓
               Security Policy (central gate)
```

**Core subsystems:**
- **Orchestrator** — routes tasks to agents/tools
- **Agents** — Research, Coding, Vision, Prediction, Critic, Verification, System
- **Tools** — Calculator, filesystem, terminal, screenshot, browser
- **Voice** — STT → Language Detection → AI → TTS
- **Avatar** — animated character driven by voice events
- **Security** — fail-closed policy with audit trail
- **Distributed** — optional multi-worker execution
- **Memory** — SQLite-backed context store

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Configure (optional — defaults work for local dev)
cp .env.example .env
# Edit .env with your API keys

# Run
python main.py

# Or with custom config
python -c "
from app.config.settings import load_config
from app.runtime.runtime import MissMinutesRuntime
import asyncio

config = load_config()
runtime = MissMinutesRuntime(config)
asyncio.run(runtime.startup())
print('Ready!')
"
```

## Configuration

Configuration is loaded from `config/missminutes.toml` with environment
variable overrides. See `config/missminutes.toml` for all options.

Secrets (API keys, auth tokens) go in `.env`, never in config files.

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Root info |
| GET | `/health` | Health check |
| POST | `/tasks` | Submit a task |
| GET | `/runtime/status` | Runtime capabilities |
| POST | `/voice/session` | Voice request |

## Testing

```bash
# Run all tests
pytest tests/

# Run specific test files
pytest tests/integration/test_runtime_lifecycle.py -v
pytest tests/integration/test_unified_requests.py -v
pytest tests/integration/test_end_to_end.py -v
pytest tests/integration/test_headless_mode.py -v
```

## Headless Mode

For CI/testing without external dependencies:

```python
from app.runtime.runtime import MissMinutesRuntime
from app.config.schema import MissMinutesConfig

runtime = MissMinutesRuntime.create_headless()
# All subsystems use deterministic fakes
```

## Documentation

- [Integration Architecture](docs/INTEGRATION.md)
