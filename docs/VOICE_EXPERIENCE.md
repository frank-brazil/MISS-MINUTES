# Advanced voice experience (CHUNK 31)

A continuous, always-on voice assistant layer built on top of the existing
voice foundation. `VoiceAssistantService` coordinates an end-to-end loop —

```
capture -> wake word -> VAD -> STT -> language/style ->
     turn management -> response generation (brain) -> TTS -> playback
```

— with barge-in, interrupt/cancel, structured events, privacy enforcement,
timeouts, and the CHUNK 30 security seam. Every provider is injected, so the
core is provider-independent and fully deterministic offline.

## Scope

Implemented:

- `VoiceAssistantService` orchestration loop with wake-word gating (optional),
  VAD-segmented utterances, idle/max-utterance/max-response/max-speaking
  timeouts, and a `max_turns` bound.
- Provider-independent boundaries with deterministic fakes:
  - Microphone capture (`app/voice/audio.py`)
  - Voice activity detection (`app/voice/vad.py`)
  - Wake-word detection (`app/voice/wakeword.py`)
  - Audio output / playback with barge-in readiness (`app/voice/output.py`)
  - Streaming STT / TTS boundaries (`app/voice/streaming.py`)
- Response generation boundary (`app/voice/brain.py`):
  - `ConversationalVoiceBrain` — AI-model chat with bounded history and
    response-style guidance.
  - `OrchestratorVoiceBrain` — routes task-oriented speech through the
    existing `Orchestrator`, so tool/agent actions go through the CHUNK 30
    security seam (audited with origin `voice`).
- Conversation turn management (`app/voice/turns.py`) — first/follow-up/
  continuation classification, per-session history, audio references.
- Spoken response policy (`app/voice/response_policy.py`) — language, voice
  and speaking pace from the detected style.
- Structured voice events (`app/voice/events.py`) — bounded, redacted,
  content-free (transcriptions/responses are recorded as character counts).
- Privacy boundary (`app/voice/privacy.py`) — `local_only` by default; audio
  is tracked buffer-by-buffer and released after processing.
- Session state machine (`app/voice/session.py`).

Explicitly **not** implemented (later chunks / out of scope):

- No avatar engine, lip-sync or gesture animation.
- No actual microphone/speaker device libraries; no remote/external audio
  capture unless a provider is explicitly configured.
- No streaming wiring inside `VoiceAssistantService` (the streaming boundary
  is provided but the one-shot providers remain the active path).
- Voice input is **never** authorization by itself; permission evaluation and
  confirmation always go through `app/security`.

## Architecture

The service owns session state, events, privacy, timeouts and the
interrupt/cancel boundary. It never talks to hardware or external services
directly.

```
VoiceAssistantService
  ├─ AudioCaptureProvider        read() -> frame / None (poll)
  ├─ WakeWordDetector            detect(frame)
  ├─ VoiceActivityDetector       feed(frame) -> started/ended/speech
  ├─ SpeechToText                transcribe(utterance)
  ├─ LanguageDetector            detect(text)  -> style
  ├─ ConversationLanguage        tracks current style
  ├─ ConversationTurnManager     classification + history
  ├─ VoiceBrain                  respond(request)
  │    ├─ ConversationalVoiceBrain  (AIModel chat)
  │    └─ OrchestratorVoiceBrain    (Orchestrator.execute + security)
  ├─ TextToSpeech                synthesize(response, profile)
  ├─ AudioOutputProvider         play/stop/is_speaking
  ├─ VoiceResponsePolicy         profile_for(...)
  ├─ VoicePrivacyGuard           retain/release audio buffers
  └─ VoiceEventLog               bounded redacted events
```

## Boundaries

### Wake word

When `wake_required` is set, the session listens for the configured phrase
(default `MissMinutes`) before any utterance is processed. On timeouts without
a wake word the session records `SESSION_IDLE_TIMEOUT` and stops cleanly.

### VAD segmentation

`_capture_utterance` appends **only voiced frames** to the utterance buffer
(the VAD `ended`/silence frame is consumed for segmentation but never added),
so leading and trailing silence never leaks into transcription. A VAD reset
happens between utterances; barge-in seeds feed the VAD before the current
capture re-reads the microphone.

### Barge-in, interrupt and cancel

- **Barge-in**: while speaking, the service keeps polling the capture. A frame
  during playback becomes the seed of the next utterance and ends the current
  playback.
- **Interrupt**: `interrupt()` sets the interrupt event and stops active
  playback; the in-flight turn completes as `INTERRUPTED`.
- **Cancel**: `cancel()` stops the session and releases capture/output
  resources; cancelled sessions cannot silently resume (`VoiceSession` guards
  post-cancel transitions).

### Streaming boundaries

`app/voice/streaming.py` defines optional incremental STT (`push_audio` /
`finalize`) and streaming TTS (chunk cursors). Existing one-shot providers are
**not** subclasses of these interfaces, so nothing is forced to stream. The
service currently drives the one-shot path.

### Security boundary

`OrchestratorVoiceBrain` wraps the transcribed request in a `Task` and hands
it to the `Orchestrator`. Every tool call is evaluated by the configured
policy at the normal execution boundary (`_check_tool_security`, CHUNK 30) —
a denied tool is simply never executed. Each dispatch is recorded in the
security audit trail with `action="voice:dispatch_task"` and `origin="voice"`
(metadata only, no transcript). A brain result marked `denied` surfaces as a
`DENIED` turn outcome, distinct from ordinary failures.

### Privacy boundary

Local-only by default: raw microphone audio is never persisted or uploaded.
Buffers are tracked (`retain_audio`/`release_audio`) and released after STT;
events store only character counts (or redacted `<N chars>` metadata) unless
`log_transcripts` is explicitly enabled. Upload is possible only in
`CONFIGURED_UPLOAD` mode with upload enabled and the provider allow-listed.

## Configuration

`VoiceAssistantConfig`:

- `wake_required` (default `True`)
- `idle_listening_timeout_seconds` (default `30.0`) — also the wake window
- `max_utterance_duration_seconds` (default `60.0`)
- `max_response_seconds` (default `30.0`)
- `max_speaking_seconds` (default `120.0`)
- `max_turns` (default `100`)

All timeout values are positive; structured errors and events are recorded for
every failure mode (STT, language, brain, TTS, playback, capture, timeouts).

## Offline determinism

Time is injected (`now_fn`); every fake is scripted (`FakeAudioCaptureProvider`
frame queue, `FakeVoiceActivityDetector` per-frame script, `FakeWakeWordDetector`
detection script, `FakeSpeechToText`/`FakeTextToSpeech` fixture maps,
`FakeVoiceBrain` scripted results, `FakeAudioOutputProvider` auto-stop). The
service loop, barge-in and interrupt orchestration tests run entirely offline
in `tests/unit/test_voice_assistant.py` plus the per-module suites
(`test_voice_audio.py` … `test_voice_brain.py`).

No CHUNK 32+ work was performed as part of this chunk.