# MISSMINUTES

Personal intelligent AI computer agent.

## Concept

MISSMINUTES is a personal, intelligent, multilingual, multimodal AI computer agent. It understands natural human communication through voice and text, reasons about problems, plans multi-step tasks, uses tools, operates approved computer functions, maintains memory, and communicates through an animated virtual assistant interface.

MISSMINUTES behaves like an intelligent assistant rather than a simple chatbot.

## Main Capabilities

- **Multi-Agent Orchestration** — routes tasks to specialized agents (Research, Coding, Vision, System, Prediction, Critic, Verification)
- **Tool System** — Calculator, filesystem operations, terminal, screenshot, browser automation
- **Voice Pipeline** — STT → Language Detection → AI → TTS with barge-in and interrupt support
- **Avatar Animation** — clock-style virtual assistant with expressions, gestures, lip-sync, walking
- **Security Policy** — fail-closed permission layer with risk assessment, confirmation, and audit trail
- **Distributed Execution** — optional multi-worker task dispatch with heartbeats and retry
- **Memory** — SQLite-backed context store
- **Evaluation Framework** — 2023+ deterministic tests across 15 scenario groups

## Architecture

```
User Input (text/voice/image)
    │
    ▼
FastAPI Server (port 8000)
    │
    ▼
Orchestrator ──→ Agents ──→ Tools ──→ Result
    │                │           │
    │                │           ▼
    │                │     Security Policy (central gate)
    │                │
    ▼                ▼
Memory          Verification → Replanning
    │
    ▼
Response (text/voice/avatar)
```

**Core subsystems:**

| Subsystem | Purpose |
|-----------|---------|
| Orchestrator | Routes tasks to agents and tools |
| Agents | Research, Coding, Vision, Prediction, Critic, Verification, System |
| Tools | Calculator, filesystem, terminal, screenshot, browser |
| Voice | STT → Language Detection → AI → TTS |
| Avatar | Animated clock character driven by voice/AI events |
| Security | Fail-closed policy with risk assessment, confirmation, audit |
| Distributed | Optional multi-worker execution with heartbeats |
| Memory | SQLite-backed context and conversation store |
| Evaluation | Deterministic benchmark framework |

## Repository Structure

```
MISSMINUTES/
├── app/                    # Application source code
│   ├── agents/             # Specialized AI agents
│   ├── api/                # FastAPI server and routes
│   ├── avatar/             # Avatar animation engine
│   ├── browser/            # Browser automation
│   ├── config/             # Configuration schema and loading
│   ├── core/               # Orchestrator, planner, routing, AI
│   ├── distributed/        # Multi-worker coordination
│   ├── evaluation/         # Benchmark framework
│   ├── memory/             # SQLite memory backend
│   ├── providers/          # OpenAI provider implementations
│   ├── research/           # Research provider abstraction
│   ├── runtime/            # Application lifecycle
│   ├── security/           # Security policy and audit
│   ├── solver/             # Problem-solving engine
│   ├── tools/              # Tool implementations
│   ├── vision/             # Screen understanding
│   └── voice/              # Voice pipeline
├── config/                 # Configuration files
│   └── missminutes.toml    # Default configuration
├── data/                   # Runtime data (memory DB, evaluation)
├── docs/                   # Documentation
├── scripts/                # Utility scripts
├── tests/                  # Test suite
│   ├── unit/               # 155+ unit test files
│   └── integration/        # 14 integration test files
├── ui/                     # Avatar assets
├── main.py                 # Application entry point
├── pyproject.toml          # Package configuration
├── requirements.txt        # Runtime dependencies
└── .env.example            # Environment variable template
```

## Requirements

- Python 3.11 or later
- Optional: OpenAI API key (for real AI responses)
- Optional: Playwright (for browser automation)
- Optional: Display server (for avatar GUI)

## Installation

```bash
# Clone or copy the repository
cd MISSMINUTES

# Create virtual environment
python -m venv .venv

# Activate
# PowerShell:
.venv\Scripts\Activate.ps1
# Command Prompt:
.venv\Scripts\activate.bat

# Install with dev dependencies
pip install -e ".[dev]"
```

## Configuration

Configuration flows through `config/missminutes.toml` with environment variable overrides.

```bash
# Copy environment template
cp .env.example .env    # Linux/macOS
Copy-Item .env.example .env    # Windows PowerShell

# Edit with your API keys
nano .env    # or notepad .env
```

See `docs/DEPLOYMENT.md` for all configuration options.

## Development Startup

```powershell
python main.py
```

Server starts on `http://127.0.0.1:8000`.

## Headless Startup (No API Keys)

```powershell
python main.py --headless
```

All subsystems use deterministic fake providers. No network access required.

## Custom Port

```powershell
python main.py --port 9000
python main.py --host 0.0.0.0 --port 9000
```

## Distributed Worker Setup

See `docs/DEPLOYMENT.md` for complete distributed setup instructions.

```powershell
# Master
$env:MISSMINUTES_DISTRIBUTED_ENABLED = "true"
$env:MISSMINUTES_AUTH_TOKEN = "your-secret-token"
python main.py

# Worker (separate terminal)
$env:MISSMINUTES_AUTH_TOKEN = "your-secret-token"
# Start worker process
```

## Testing

```bash
# Run all tests
pytest tests/

# Run with verbose output
pytest tests/ -v

# Run specific test file
pytest tests/unit/test_orchestrator.py -v

# Run integration tests
pytest tests/integration/ -v
```

## Evaluation

```bash
# Run full evaluation suite
python scripts/run_evaluation.py

# View report
cat data/evaluation/EVALUATION_REPORT.md
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Root info (name, version, status) |
| GET | `/health` | Health check |
| POST | `/tasks` | Submit a task |
| GET | `/runtime/status` | Runtime capabilities and uptime |
| POST | `/voice/session` | Voice request |
| POST | `/tasks/{task_id}/cancel` | Task cancellation |

## Security

- Fail-closed security policy by default
- Risk assessment with automatic classification
- Human confirmation for high-risk actions
- Redacted audit trail (no secrets in logs)
- Tool permission mapping
- Distributed worker authentication

See `docs/SECURITY.md` for detailed security documentation.

## Demo

See `docs/DEMO.md` for a step-by-step demonstration guide.

```powershell
# Quick demo
python main.py --headless
# In another terminal:
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/tasks -H "Content-Type: application/json" -d "{\"description\": \"What is 2+2?\"}"
```

## Docker (Optional)

```bash
docker build -t missminutes .
docker run -p 8000:8000 -e OPENAI_API_KEY=your-key missminutes
```

**Note:** Avatar/GUI features require a display server and are NOT supported in containers.

## Documentation

- [Deployment Guide](docs/DEPLOYMENT.md)
- [Demo Guide](docs/DEMO.md)
- [Operations Checklist](docs/OPERATIONS_CHECKLIST.md)
- [Security](docs/SECURITY.md)
- [Voice Experience](docs/VOICE_EXPERIENCE.md)
- [Avatar Animation](docs/AVATAR_ANIMATION.md)
- [Evaluation](docs/EVALUATION.md)
- [Integration Architecture](docs/INTEGRATION.md)

## Known Limitations

- Avatar/GUI requires a display server (not headless)
- Voice requires microphone/speaker hardware
- SQLite memory is single-process only
- In-memory audit store does not persist across restarts
- Real AI quality depends on configured provider
- Browser automation requires Playwright installation
- Distributed mode uses shared-token authentication only

## Project Status

| Chunk | Status |
|-------|--------|
| CHUNK 1-29 | Core architecture, agents, tools, distributed |
| CHUNK 30 | Security system |
| CHUNK 31 | Voice experience |
| CHUNK 32 | Avatar foundation |
| CHUNK 33 | Avatar animation |
| CHUNK 34 | Integration |
| CHUNK 35 | Evaluation framework (248/248 tests passed) |
| CHUNK 36 | Packaging, deployment, demo readiness |

**Test suite:** 2061+ tests passing

## License

Internal academic project.
