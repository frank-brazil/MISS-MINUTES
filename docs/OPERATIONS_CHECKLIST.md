# MISSMINUTES Operations Checklist

Pre-flight, startup, demo, and shutdown checklists for reliable operation.

## Pre-Start Checklist

- [ ] Python 3.11+ installed
- [ ] Virtual environment created: `python -m venv .venv`
- [ ] Virtual environment activated: `.venv\Scripts\Activate.ps1`
- [ ] Package installed: `pip install -e ".[dev]"`
- [ ] All tests pass: `pytest tests/ -q`
- [ ] Configuration file exists: `config/missminutes.toml`
- [ ] `.env` file created (if using real providers): `Copy-Item .env.example .env`

## Configuration Checklist

- [ ] AI provider configured (or headless mode)
- [ ] Memory database path accessible
- [ ] Voice settings correct (disabled if no microphone)
- [ ] Avatar settings correct (disabled if no display)
- [ ] Security policy set appropriately
- [ ] Distributed settings correct (disabled for single-machine)
- [ ] Browser settings correct (disabled if Playwright not installed)
- [ ] Filesystem allowed roots configured
- [ ] Logging level set

## Security Checklist

- [ ] No real API keys in source code or config files
- [ ] `.env` is in `.gitignore`
- [ ] Auth token set for distributed workers (if networked)
- [ ] Security policy not set to `allow_all` in production
- [ ] Audit logging enabled
- [ ] Confirmation required for high-risk actions
- [ ] Browser downloads restricted to allowed domains
- [ ] Filesystem access restricted to allowed roots
- [ ] Terminal commands go through security policy

## Startup Checklist

- [ ] Run `python main.py` (or `python main.py --headless`)
- [ ] Verify server starts without errors
- [ ] Check health endpoint: `curl http://127.0.0.1:8000/health`
- [ ] Verify response: `{"status": "ok"}`
- [ ] Check runtime status: `curl http://127.0.0.1:8000/runtime/status`
- [ ] Verify ready state: `"ready": true`

## Health Check

```powershell
# Basic health
curl http://127.0.0.1:8000/health

# Runtime capabilities
curl http://127.0.0.1:8000/runtime/status

# Distributed health (if enabled)
curl http://127.0.0.1:8100/distributed/health
```

Expected responses:
- Health: `{"status": "ok"}`
- Runtime: `{"ready": true, "uptime_seconds": ..., "request_count": 0, "capabilities": {...}}`
- Distributed: `{"role": "master", "status": "ready", "workers": "0", "queued": "0"}`

## Worker Checklist (Distributed Mode)

- [ ] Master is running and accessible
- [ ] `MISSMINUTES_AUTH_TOKEN` matches on master and worker
- [ ] Worker bind host/port are correct
- [ ] Worker registers successfully with master
- [ ] Heartbeats are being received
- [ ] Worker capabilities match task types

## Demo Checklist

- [ ] Headless mode working (`python main.py --headless`)
- [ ] Text requests produce responses
- [ ] Tool operations work (calculator, files, system info)
- [ ] Security policy triggers correctly
- [ ] Evaluation report runs: `python scripts/run_evaluation.py`
- [ ] All 2023+ tests pass

## Shutdown Checklist

- [ ] Press `Ctrl+C` or send SIGTERM
- [ ] Server shuts down gracefully
- [ ] No orphan processes remain
- [ ] Database file is intact
- [ ] Logs are written correctly
- [ ] Browser resources are released (if used)

## Troubleshooting Checklist

| Symptom | Check |
|---------|-------|
| `ModuleNotFoundError: app` | `pip install -e .` from project root |
| `Port already in use` | Change port or kill existing process |
| `OPENAI_API_KEY not set` | Use `--headless` or set key in `.env` |
| Browser fails | `pip install playwright && playwright install` |
| Worker won't connect | Verify `MISSMINUTES_AUTH_TOKEN` matches |
| Tests fail | `pip install -e ".[dev]"` then `pytest tests/ -q` |
| Import errors | Ensure virtual environment is activated |
| Config not loading | Check `config/missminutes.toml` exists |
| Memory errors | Check `data/` directory permissions |
| Voice not working | Verify `MISSMINUTES_VOICE_ENABLED=true` and API key |
