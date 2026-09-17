# MISSMINUTES External API Integration Map

This document catalogs every location in the codebase where an external API, API key, provider credential, or external service is required or could be integrated.

---

## Integration Table

| Component | Provider | API/Credential | Required? | Code Location | Status |
|---|---|---|---|---|---|
| **LLM / Chat** | OpenAI | `OPENAI_API_KEY` | Yes* | `app/providers/openai_provider.py:17` | REAL PROVIDER EXISTS |
| **LLM / Chat** | OpenAI | `OPENAI_MODEL` | No (default: gpt-4o-mini) | `app/providers/openai_provider.py:18` | REAL PROVIDER EXISTS |
| **LLM / Chat** | OpenRouter (optional) | `OPENROUTER_API_KEY` | No | Not implemented (architecture supports) | OPTIONAL EXTERNAL API |
| **LLM / Chat** | OpenRouter (optional) | `OPENROUTER_MODEL` | No | Not implemented | OPTIONAL EXTERNAL API |
| **LLM / Chat** | OpenRouter (optional) | `OPENROUTER_BASE_URL` | No | Not implemented | OPTIONAL EXTERNAL API |
| **STT** | OpenAI Whisper | `OPENAI_API_KEY` | Yes* | `app/providers/openai_speech_to_text.py:8` | REAL PROVIDER EXISTS |
| **STT** | OpenAI Whisper | `MISSMINUTES_STT_MODEL` | No (default: whisper-1) | `app/providers/openai_speech_to_text.py:9` | REAL PROVIDER EXISTS |
| **STT** | OpenAI Whisper | `MISSMINUTES_STT_LANGUAGE` | No (auto-detect) | `app/providers/openai_speech_to_text.py:10` | REAL PROVIDER EXISTS |
| **TTS** | OpenAI TTS | `OPENAI_API_KEY` | Yes* | `app/providers/openai_text_to_speech.py:13` | REAL PROVIDER EXISTS |
| **TTS** | OpenAI TTS | `MISSMINUTES_TTS_MODEL` | No (default: tts-1) | `app/providers/openai_text_to_speech.py:14` | REAL PROVIDER EXISTS |
| **TTS** | OpenAI TTS | `MISSMINUTES_TTS_VOICE` | No (default: alloy) | `app/providers/openai_text_to_speech.py:15` | REAL PROVIDER EXISTS |
| **TTS** | OpenAI TTS | `MISSMINUTES_TTS_FORMAT` | No (default: mp3) | `app/providers/openai_text_to_speech.py:16` | REAL PROVIDER EXISTS |
| **Research** | Generic HTTP Search | `MISSMINUTES_SEARCH_URL` | Yes* | `app/research/http_provider.py:27` | REAL PROVIDER EXISTS |
| **Research** | Generic HTTP Search | `MISSMINUTES_SEARCH_API_KEY` | No (optional Bearer) | `app/research/http_provider.py:28` | REAL PROVIDER EXISTS |
| **Distributed Auth** | Internal (master↔worker) | `MISSMINUTES_AUTH_TOKEN` | Yes* | `app/distributed/auth.py:13`, `app/config/schema.py:65` | REQUIRED EXTERNAL AUTH |
| **Vision** | None implemented | — | No | `app/vision/provider.py:31` (ABC boundary) | NOT REQUIRED |
| **OCR** | None implemented | — | No | `app/vision/ocr.py:66` (UnsupportedOcrProvider) | NOT REQUIRED |
| **Browser** | Local Playwright | None | No | `app/browser/playwright_provider.py:46` | LOCAL SERVICE |
| **Memory** | Local SQLite | None | No | `app/memory/sqlite_memory.py:19` | LOCAL SERVICE |
| **Language Detection** | Local heuristic | None | No | `app/voice/local_detector.py` | LOCAL SERVICE |
| **Screenshot** | Local (unsupported) | None | No | `app/tools/screenshot.py:47` | LOCAL SERVICE |

\* Required only when the corresponding feature is enabled via config (e.g., `MISSMINUTES_VOICE_ENABLED=true`, `MISSMINUTES_BROWSER_ENABLED=true`, `MISSMINUTES_DISTRIBUTED_ENABLED=true`).

---

## Fake Providers (Deterministic, Offline Tests)

| Provider | File | Purpose |
|---|---|---|
| `FakeSpeechToText` | `app/voice/fakes.py:18` | STT fake for tests |
| `FakeTextToSpeech` | `app/voice/fakes.py:101` | TTS fake for tests |
| `FakeLanguageDetector` | `app/voice/fakes.py:172` | Language detection fake |
| `FakeAIModel` | `app/voice/fakes.py:215` | LLM fake for tests |
| `FakeResearchProvider` | `app/research/fakes.py:16` | Research fake for tests |
| `FakeBrowserProvider` | `app/browser/fakes.py:47` | Browser fake for tests |
| `FakeVisionProvider` | `app/vision/fakes.py:19` | Vision fake for tests |
| `FakeOcrProvider` | `app/vision/fakes.py:94` | OCR fake for tests |
| `FakeAvatarRenderer` | `app/avatar/renderer.py` | Avatar renderer fake |

All existing tests use these fakes — no network calls, no real API keys required.

---

## Local Hardware Requirements

| Hardware | Required When | Code Location |
|---|---|---|
| Microphone | `MISSMINUTES_VOICE_ENABLED=true` | `app/voice/base.py:38` (SpeechInput) |
| Speaker | `MISSMINUTES_VOICE_ENABLED=true` | `app/voice/base.py:102` (TextToSpeechRequest) |
| Display (GUI) | `MISSMINUTES_AVATAR_ENABLED=true` | `app/avatar/window.py` (Tkinter) |

---

## Local Services (No API Key)

| Service | Description | Code Location |
|---|---|---|
| Playwright + Chromium | Browser automation | `app/browser/playwright_provider.py` |
| SQLite | Persistent memory | `app/memory/sqlite_memory.py` |
| Local Language Detector | Offline EN/HI/UR detection | `app/voice/local_detector.py` |

---

## API Setup Order (Recommended)

1. **Copy `.env.example` to `.env`**
   ```bash
   cp .env.example .env
   ```

2. **Add `OPENAI_API_KEY`** — Enables LLM, STT, and TTS (single key for all three)
   - Get from https://platform.openai.com/api-keys

3. **Add `MISSMINUTES_SEARCH_URL`** — Enables Research Agent
   - Point to a JSON REST endpoint implementing the MISSMINUTES search contract:
     - POST `{"query": "...", "max_results": 5}`
     - Returns `{"results": [{"title": "...", "url": "...", "snippet": "..."}]}`
   - Optional: Add `MISSMINUTES_SEARCH_API_KEY` for Bearer auth

4. **Add `MISSMINUTES_AUTH_TOKEN`** — Enables Distributed Workers
   - Shared secret between master and workers
   - Generate: `openssl rand -hex 32`
   - Required when `MISSMINUTES_DISTRIBUTED_ENABLED=true` and binding to non-loopback

5. **Install Playwright** (optional — enables browser tools)
   ```bash
   pip install playwright
   playwright install chromium
   ```
   - Set `MISSMINUTES_BROWSER_ENABLED=true` in config

6. **Enable features in config** (or via env vars):
   - `MISSMINUTES_VOICE_ENABLED=true` — Voice pipeline
   - `MISSMINUTES_AVATAR_ENABLED=true` — Avatar GUI (requires display)
   - `MISSMINUTES_DISTRIBUTED_ENABLED=true` — Multi-machine

7. **Restart MISSMINUTES** and verify:
   - `GET /health` — Overall health
   - `GET /runtime/status` — Capability registry shows enabled subsystems

---

## Where to Add API Keys

1. **Copy `.env.example` to `.env`** in the project root.
2. **Edit `.env`** and fill in your credentials:
   - `OPENAI_API_KEY=sk-...`
   - `MISSMINUTES_SEARCH_URL=https://your-search-endpoint/api`
   - `MISSMINUTES_AUTH_TOKEN=your-generated-token`
3. **Never commit `.env`** — it's in `.gitignore`.
4. **Restart the application** to pick up changes.
5. **Verify** via the health endpoint or `MISSMINUTES_LOG_LEVEL=DEBUG` logs.

---

## Security Notes

- All credentials are read from environment variables at runtime — never stored in config objects.
- `.env` is gitignored (see `.gitignore`).
- The distributed auth token (`MISSMINUTES_AUTH_TOKEN`) is an **internal shared secret**, not a third-party API key.
- No hardcoded secrets exist in the source code.
- Fake providers are used by default in tests and headless mode (`--headless` flag).

---

## Vision / OCR — Future Integration

The vision system exposes a clean provider abstraction (`VisionProvider` in `app/vision/provider.py` and `OcrProvider` in `app/vision/ocr.py`). To add a real vision/OCR provider:

1. Implement the `VisionProvider.analyze()` or `OcrProvider.extract_text()` abstract method.
2. Register your implementation in the runtime configuration.
3. Add any required API keys to `.env` and read them in your provider's `__init__`.

Currently only deterministic fakes exist — no external vision/OCR API is required.

---

## OpenRouter Integration Point

The architecture supports multiple LLM providers via the `AIModel` abstraction (`app/core/ai.py`). To add OpenRouter:

1. Create `app/providers/openrouter_provider.py` implementing `AIModel`.
2. Read `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_BASE_URL` from environment.
3. Register in runtime based on `MISSMINUTES_AI_PROVIDER=openrouter` config.

No OpenRouter provider exists yet — the integration point is the `AIModel` ABC and the provider factory logic (to be added).