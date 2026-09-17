# MISSMINUTES Demo Guide

Step-by-step guide for demonstrating MISSMINUTES at a final-year project evaluation.

## Prerequisites

```powershell
cd C:\MISSMINUTES
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Demo Sequence

### Step 1: Start MISSMINUTES

```powershell
python main.py --headless
```

The server starts on `http://127.0.0.1:8000`. Headless mode uses all deterministic fakes — no API keys required.

### Step 2: Health / Readiness Check

```powershell
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status": "ok"}
```

Runtime status:

```powershell
curl http://127.0.0.1:8000/runtime/status
```

Shows ready state, uptime, request count, and all registered capabilities.

### Step 3: Submit a Text Request

```powershell
curl -X POST http://127.0.0.1:8000/tasks -H "Content-Type: application/json" -d "{\"description\": \"What is the capital of France?\"}"
```

Demonstrates: user input → orchestrator → agent routing → response generation.

### Step 4: Demonstrate Planning / Agent Routing

Submit requests that trigger different agent paths:

```powershell
# Research agent
curl -X POST http://127.0.0.1:8000/tasks -H "Content-Type: application/json" -d "{\"description\": \"Research Python async patterns\"}"

# System agent
curl -X POST http://127.0.0.1:8000/tasks -H "Content-Type: application/json" -d "{\"description\": \"Show system information\"}"
```

### Step 5: Demonstrate Safe Tool Operations

```powershell
# Calculator tool
curl -X POST http://127.0.0.1:8000/tasks -H "Content-Type: application/json" -d "{\"description\": \"Calculate 42 * 17 + 3\"}"

# File operations
curl -X POST http://127.0.0.1:8000/tasks -H "Content-Type: application/json" -d "{\"description\": \"List files in the current directory\"}"
```

### Step 6: Demonstrate Security Confirmation / Denial

High-risk operations trigger the security policy:

```powershell
# This will require confirmation or be denied depending on policy
curl -X POST http://127.0.0.1:8000/tasks -H "Content-Type: application/json" -d "{\"description\": \"Delete all files in temp directory\"}"
```

The security manager evaluates risk level and applies the configured policy.

### Step 7: Demonstrate Research (when configured)

With a research provider configured:

```powershell
curl -X POST http://127.0.0.1:8000/tasks -H "Content-Type: application/json" -d "{\"description\": \"What are the latest developments in AI?\"}"
```

### Step 8: Demonstrate Verification / Replanning

The orchestrator automatically verifies results and replans when verification fails. This is visible in the audit trail:

```python
import asyncio
from app.runtime.runtime import MissMinutesRuntime
from app.config.schema import MissMinutesConfig

runtime = MissMinutesRuntime.create_headless()
asyncio.run(runtime.startup())
response = asyncio.run(runtime.handle_text("Verify that 2+2 equals 4"))
print(response.audit_trail)  # Shows verification steps
asyncio.run(runtime.shutdown())
```

### Step 9: Demonstrate Voice Path (if enabled)

With voice enabled and OpenAI API key configured:

```powershell
# Send audio to voice endpoint
curl -X POST http://127.0.0.1:8000/voice/session -H "Content-Type: application/json" -d "{\"audio\": \"<base64-audio-data>\", \"format\": \"wav\"}"
```

### Step 10: Demonstrate Avatar Response (if enabled)

With avatar enabled and a display server available, the avatar responds to voice events through the `VoiceAvatarAdapter`.

### Step 11: Demonstrate Distributed Worker Execution

**Terminal 1 — Master:**
```powershell
$env:MISSMINUTES_DISTRIBUTED_ENABLED = "true"
$env:MISSMINUTES_AUTH_TOKEN = "demo-token"
python main.py --port 8000
```

**Terminal 2 — Worker:**
```powershell
$env:MISSMINUTES_AUTH_TOKEN = "demo-token"
# Start a worker process (see DEPLOYMENT.md for worker startup code)
```

Submit a task that routes through the distributed layer.

### Step 12: Demonstrate Worker Failure / Retry / Retry-Reroute

The deterministic distributed system supports:
- Worker failure detection via heartbeat timeout
- Automatic retry up to `max_retries`
- Reroute to different workers on failure

This is tested in `tests/unit/test_distributed_coordinator.py` and `tests/unit/test_distributed_scheduler.py`.

### Step 13: Show Evaluation Report

```powershell
python scripts/run_evaluation.py
cat data\evaluation\EVALUATION_REPORT.md
```

Shows all 15 scenario groups (A-K, V, AV, M, E2E, R) with pass/fail/not-measured results.

### Step 14: Explain Limitations

Clearly communicate what is implemented vs. what is future work:

**Implemented:**
- Multi-agent orchestration with tool routing
- Security policy enforcement with audit trail
- Deterministic evaluation framework (2023+ tests)
- Voice pipeline (STT → language detection → AI → TTS)
- Avatar animation engine (expressions, gestures, lip-sync)
- Distributed multi-worker execution
- Memory with SQLite backend
- File system, terminal, calculator, browser tools

**Future Work:**
- Real-time voice interaction with microphone
- Full GUI avatar with real-time rendering
- Production-grade distributed deployment
- Real-world AI model accuracy improvements
- Long-term memory persistence improvements

## Running the Full Test Suite

```powershell
pytest tests/ -v
```

Expected: All tests pass.

## Demo Mode Characteristics

- All providers are deterministic fakes
- Responses are pre-scripted for repeatability
- No network access required
- No API keys required
- Results are identical across runs
- Clearly labeled as demo/fake mode

## Scripted Demo Example

For a scripted presentation, run this Python snippet:

```python
import asyncio
from app.runtime.runtime import MissMinutesRuntime
from app.config.schema import MissMinutesConfig


async def demo():
    runtime = MissMinutesRuntime.create_headless()
    await runtime.startup()

    # Text request
    r1 = await runtime.handle_text("What is 2 + 2?")
    print(f"Text: {r1.text_response}")

    # System info
    r2 = await runtime.handle_text("Show system information")
    print(f"System: {r2.text_response}")

    # Research
    r3 = await runtime.handle_text("Research Python async patterns")
    print(f"Research: {r3.text_response}")

    await runtime.shutdown()


asyncio.run(demo())
```
