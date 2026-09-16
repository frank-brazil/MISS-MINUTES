# MISSMINUTES Evaluation Report

**Run ID:** `b5ae5006-230a-41f5-b4d0-a78cc6e5e7ab`
**Started:** 2026-09-16 23:22:38.082353+00:00
**Completed:** 2026-09-16 23:22:38.176586+00:00
**Mode:** deterministic
**Python:** 3.13.7
**Platform:** Windows-11-10.0.26200-SP0

---

## Executive Summary

| Metric | Count |
|---|---|
| Total results | 82 |
| PASS | 73 |
| FAIL | 3 |
| INCONCLUSIVE | 0 |
| NOT_MEASURED | 6 |
| NOT_APPLICABLE | 0 |
| Reliability PASS | 15 |
| Reliability FAIL | 0 |
| Reliability N/A | 0 |

---

## Deterministic Fakes Used

- `FakeSpeechToText`
- `FakeTextToSpeech`
- `FakeLanguageDetector`
- `FakeAIModel`
- `FakeResearchProvider`
- `FakeVisionProvider`
- `FakeOcrProvider`
- `FakeActionExecutor`
- `FakeObservationProvider`
- `FakeVerifier`
- `FakeCritic`
- `FakePredictor`
- `FakeWorkerTransport`
- `FakeMasterTransport`
- `FakeWorkerExecutor`
- `FakeBrowserProvider`
- `FakeAvatarRenderer`
- `InMemoryMemory`

---

## Results by Scenario

### STT Quality

| Metric | Value | Status | Evidence | Limitations |
|---|---|---|---|---|
| stt_word_error_rate | 0.0000 | pass | reference='Find my project files in the Documents folder', h | Deterministic fixture only; no real audio or real STT provid |
| stt_character_error_rate | 0.0000 | pass | reference='Find my project files in the Documents folder', h | Deterministic fixture only; no real audio or real STT provid |
| stt_word_error_rate | 0.1250 | fail | reference='Open the browser and search for recent news', hyp | Deterministic fixture only; no real audio or real STT provid |
| stt_character_error_rate | 0.1395 | fail | reference='Open the browser and search for recent news', hyp | Deterministic fixture only; no real audio or real STT provid |
| stt_word_error_rate | 0.0000 | pass | reference='Mujhe apne project ki files dhoondho', hypothesis | Deterministic fixture only; no real audio or real STT provid |
| stt_character_error_rate | 0.0000 | pass | reference='Mujhe apne project ki files dhoondho', hypothesis | Deterministic fixture only; no real audio or real STT provid |
| stt_word_error_rate | 0.0000 | pass | reference='Mujhe project folder mein README file dikhao', hy | Deterministic fixture only; no real audio or real STT provid |
| stt_character_error_rate | 0.0000 | pass | reference='Mujhe project folder mein README file dikhao', hy | Deterministic fixture only; no real audio or real STT provid |
| stt_word_error_rate | 0.0000 | pass | reference='Stop', hypothesis='Stop' | Deterministic fixture only; no real audio or real STT provid |
| stt_character_error_rate | 0.0000 | pass | reference='Stop', hypothesis='Stop' | Deterministic fixture only; no real audio or real STT provid |
| stt_word_error_rate | 0.0000 | pass | reference='', hypothesis='' | Deterministic fixture only; no real audio or real STT provid |
| stt_character_error_rate | 0.0000 | pass | reference='', hypothesis='' | Deterministic fixture only; no real audio or real STT provid |

### Language Detection

| Metric | Value | Status | Evidence | Limitations |
|---|---|---|---|---|
| language_detection_accuracy | 1.0000 | pass | 8/8 correct | Fixture-based detection; no real speech input. |
| language_detection_accuracy | 1.0000 | pass | text='Find my project files', expected=english, actual=engli | Fixture-based detection; no real speech input. |
| language_detection_accuracy | 1.0000 | pass | text='Mujhe apni files dhoondho', expected=hindi, actual=hin | Fixture-based detection; no real speech input. |
| language_detection_accuracy | 1.0000 | pass | text='Yaar project folder khol de', expected=hindi, actual=h | Fixture-based detection; no real speech input. |
| language_detection_accuracy | 1.0000 | pass | text='Read the configuration file and tell me ', expected=en | Fixture-based detection; no real speech input. |
| language_detection_accuracy | 1.0000 | pass | text='Ye kya kar raha hai? Check karo', expected=hindi, actu | Fixture-based detection; no real speech input. |
| language_detection_accuracy | 1.0000 | pass | text='Research recent developments in AI agent', expected=en | Fixture-based detection; no real speech input. |
| language_detection_accuracy | 1.0000 | pass | text='Meri help karo is code ko samajhne mein', expected=hin | Fixture-based detection; no real speech input. |
| language_detection_accuracy | 1.0000 | pass | text='Bhai ye file delete mat karna', expected=hindi, actual | Fixture-based detection; no real speech input. |

### Tool/Agent Routing

| Metric | Value | Status | Evidence | Limitations |
|---|---|---|---|---|
| routing_correct_rate | 1.0000 | pass | 8/8 correct | Capability-based routing only; no LLM-based intent classific |
| routing_correct_rate | 1.0000 | pass | task='Find my DSA notes PDF in my college fold', expected=co | Capability-based routing only; no LLM-based intent classific |
| routing_correct_rate | 1.0000 | pass | task='Check what processes are running on my l', expected=sy | Capability-based routing only; no LLM-based intent classific |
| routing_correct_rate | 1.0000 | pass | task='Analyze the error in my code and explain', expected=co | Capability-based routing only; no LLM-based intent classific |
| routing_correct_rate | 1.0000 | pass | task='Research current information about quant', expected=re | Capability-based routing only; no LLM-based intent classific |
| routing_correct_rate | 1.0000 | pass | task='Take a screenshot of the current screen', expected=vis | Capability-based routing only; no LLM-based intent classific |
| routing_correct_rate | 1.0000 | pass | task='Create a new file with the report conten', expected=co | Capability-based routing only; no LLM-based intent classific |
| routing_correct_rate | 1.0000 | pass | task='Analyze this screenshot and describe wha', expected=vi | Capability-based routing only; no LLM-based intent classific |
| routing_correct_rate | 1.0000 | pass | task='Edit the configuration file to change th', expected=co | Capability-based routing only; no LLM-based intent classific |

### Planning Success

| Metric | Value | Status | Evidence | Limitations |
|---|---|---|---|---|
| planning_valid_plan_rate | 1.0000 | pass | 3/3 valid | ManualPlanner only; no LLM-based planning. |
| planning_valid_plan_rate | 1.0000 | pass | task='Research AI agents and create a report', steps=3, min= | ManualPlanner only; no LLM-based planning. |
| planning_valid_plan_rate | 1.0000 | pass | task='Find files and summarize', steps=3, min=2 | ManualPlanner only; no LLM-based planning. |
| planning_valid_plan_rate | 1.0000 | pass | task='Check system status', steps=3, min=1 | ManualPlanner only; no LLM-based planning. |

### Research/Source Quality

| Metric | Value | Status | Evidence | Limitations |
|---|---|---|---|---|
| research_citation_presence | 0.6667 | fail | 2/3 have citations | Fixture-based research; no real web search. |
| research_source_coverage | 1.0000 | pass | Avg coverage across 3 queries | Fixture-based research; no real web search. |
| research_source_coverage | 1.0000 | pass | query='quantum computing', expected=2, actual=2 | Fixture-based research; no real web search. |
| research_source_coverage | 1.0000 | pass | query='AI agents', expected=1, actual=1 | Fixture-based research; no real web search. |
| research_source_coverage | 1.0000 | pass | query='empty query', expected=0, actual=0 | Fixture-based research; no real web search. |

### Computer Task Completion

| Metric | Value | Status | Evidence | Limitations |
|---|---|---|---|---|
| computer_task_success_rate | 1.0000 | pass | 3/3 succeeded | FakeActionExecutor; no real filesystem operations. |
| computer_task_success_rate | 1.0000 | pass | action='Read file /test/file.txt', success=True | FakeActionExecutor; no real filesystem operations. |
| computer_task_success_rate | 1.0000 | pass | action='Search files *.py', success=True | FakeActionExecutor; no real filesystem operations. |
| computer_task_success_rate | 1.0000 | pass | action='Create file /tmp/test.txt', success=True | FakeActionExecutor; no real filesystem operations. |
| computer_safe_failure_rate | 1.0000 | pass | 3 unsafe actions denied by policy | Security policy evaluation; no real destructive commands. |

### Browser Success

| Metric | Value | Status | Evidence | Limitations |
|---|---|---|---|---|
| browser_safe_action_rate | 1.0000 | pass | HTTPS navigation succeeded | FakeBrowserProvider; no real browser. |
| browser_unsafe_scheme_rejected | 1.0000 | pass | Unsafe schemes rejected by policy | Policy enforcement; no real browser. |
| browser_domain_policy_respected | 1.0000 | pass | Domain policy enforced | FakeBrowserProvider; no real browser. |

### Vision Understanding

| Metric | Value | Status | Evidence | Limitations |
|---|---|---|---|---|
| vision_observation_accuracy | 1.0000 | pass | image=screenshot_desktop_001, observation_provided=True | FakeVisionProvider; no real screenshot analysis. |
| vision_observation_accuracy | 1.0000 | pass | image=screenshot_browser_001, observation_provided=True | FakeVisionProvider; no real screenshot analysis. |
| vision_untrusted_text_handling | 1.0000 | pass | Screen text treated as observation data only | Structural guarantee; no real untrusted text test. |

### Distributed Scheduling/Recovery

| Metric | Value | Status | Evidence | Limitations |
|---|---|---|---|---|
| distributed_dispatch_success | 1.0000 | pass | assignment_id=8215105c-5b09-41b3-9357-98f9dbe06ccd | FakeWorkerTransport; no real distributed workers. |
| distributed_duplicate_prevention | 1.0000 | pass | Duplicate task IDs rejected by queue | Structural guarantee in DistributedTaskQueue. |

### Security Reliability

| Metric | Value | Status | Evidence | Limitations |
|---|---|---|---|---|
| security_allow_allowed | 1.0000 | pass | action='read file /home/user/project/README.md', expected=al | ConservativePolicy; no real security integration test. |
| security_deny_denied | 1.0000 | pass | action='delete system files /etc/passwd', expected=deny | ConservativePolicy; no real security integration test. |
| security_deny_denied | 1.0000 | pass | action='execute arbitrary terminal command rm -rf /', expect | ConservativePolicy; no real security integration test. |
| security_deny_denied | 1.0000 | pass | action='navigate browser to javascript:alert(1)', expected=d | ConservativePolicy; no real security integration test. |
| security_allow_allowed | 1.0000 | pass | action='navigate browser to https://example.com', expected=a | ConservativePolicy; no real security integration test. |
| security_confirm_allowed | 1.0000 | pass | action='write file to /tmp/output.txt', expected=confirm | ConservativePolicy; no real security integration test. |
| security_untrusted_vision_text | 1.0000 | pass | Untrusted screen text remains observation data | Structural guarantee. |

### Voice Latency

| Metric | Value | Status | Evidence | Limitations |
|---|---|---|---|---|
| voice_latency_capture_to_stt_ms | 150.0000 | not_measured | Fixture value: 150.0ms | Deterministic fixture only; no real microphone, STT, TTS, or |
| voice_latency_stt_to_orchestrator_ms | 80.0000 | not_measured | Fixture value: 80.0ms | Deterministic fixture only; no real microphone, STT, TTS, or |
| voice_latency_orchestrator_to_tts_ms | 120.0000 | not_measured | Fixture value: 120.0ms | Deterministic fixture only; no real microphone, STT, TTS, or |
| voice_latency_tts_to_playback_start_ms | 50.0000 | not_measured | Fixture value: 50.0ms | Deterministic fixture only; no real microphone, STT, TTS, or |
| voice_latency_interruption_response_ms | 30.0000 | not_measured | Fixture value: 30.0ms | Deterministic fixture only; no real microphone, STT, TTS, or |
| voice_interruption_response | 1.0000 | pass | Interruption stops playback and transitions to listening | Structural guarantee; no real audio playback test. |

### Avatar Synchronization

| Metric | Value | Status | Evidence | Limitations |
|---|---|---|---|---|
| avatar_event_propagation | 1.0000 | pass | event=voice_listening, expected=listening, actual=listening | FakeAvatarRenderer and AvatarStateMachine; no real rendering |
| avatar_event_propagation | 1.0000 | pass | event=thinking, expected=thinking, actual=thinking | FakeAvatarRenderer and AvatarStateMachine; no real rendering |
| avatar_event_propagation | 1.0000 | pass | event=speaking, expected=speaking, actual=speaking | FakeAvatarRenderer and AvatarStateMachine; no real rendering |
| avatar_event_propagation | 1.0000 | pass | event=interruption, expected=listening, actual=listening | FakeAvatarRenderer and AvatarStateMachine; no real rendering |
| avatar_voice_avatar_sync | 1.0000 | pass | Voice events trigger avatar state changes | Event propagation tested via state machine; no real lip-sync |

### Memory Retrieval

| Metric | Value | Status | Evidence | Limitations |
|---|---|---|---|---|
| memory_retrieval_success | 1.0000 | pass | query='dark theme', expected>=1, actual=1 | InMemoryMemory; no semantic/vector search. |
| memory_retrieval_success | 1.0000 | pass | query='quantum physics lecture notes', expected>=0, actual=0 | InMemoryMemory; no semantic/vector search. |
| memory_retrieval_success | 1.0000 | pass | query='password', expected>=0, actual=0 | InMemoryMemory; no semantic/vector search. |

### End-to-End Task Completion

| Metric | Value | Status | Evidence | Limitations |
|---|---|---|---|---|
| e2e_task_completion_rate | 1.0000 | pass | plan_steps=3 | Manual pipeline; no real end-to-end orchestration. |

### Reliability

| Metric | Value | Status | Evidence | Limitations |
|---|---|---|---|---|
| reliability_no_infinite_loops | 1.0000 | pass | scenario=success_first_iteration, iterations=1, max=3 | FakeActionExecutor; no real problem-solving engine. |
| reliability_no_infinite_loops | 1.0000 | pass | scenario=success_after_replan, iterations=2, max=3 | FakeActionExecutor; no real problem-solving engine. |
| reliability_no_infinite_loops | 1.0000 | pass | scenario=repeated_failures, iterations=3, max=3 | FakeActionExecutor; no real problem-solving engine. |
| reliability_no_infinite_loops | 1.0000 | pass | scenario=timeout, iterations=1, max=5 | FakeActionExecutor; no real problem-solving engine. |

### Verification

| Metric | Value | Status | Evidence | Limitations |
|---|---|---|---|---|
| verification_accuracy | 1.0000 | pass | 2/2 correct | FakeVerifier with deterministic heuristics. |
| verification_accuracy | 1.0000 | pass | expected=verified, actual=verified | FakeVerifier with deterministic heuristics. |
| verification_accuracy | 1.0000 | pass | expected=failed, actual=failed | FakeVerifier with deterministic heuristics. |

### Prediction Calibration

| Metric | Value | Status | Evidence | Limitations |
|---|---|---|---|---|
| verification_accuracy | 1.0000 | not_measured | Heuristic prediction produced; no calibrated ground truth | FakePredictor produces heuristic estimates, not calibrated p |

---

## Reliability Results

| Scenario | Status | Details |
|---|---|---|
| provider_failure | pass | Provider failure raised structured error as expected |
| tool_failure | pass | Tool failure captured with structured error |
| agent_failure | pass | Agent failure captured with structured error |
| planner_failure | pass | Planner failure captured with structured error |
| timeout | pass | Timeout enforced correctly |
| cancellation | pass | Cancellation respected |
| verification_failure | pass | Verification failure correctly identified |
| inconclusive_verification | pass | Inconclusive verification handled correctly: inconclusive |
| worker_failure | pass | Worker failure captured with structured error |
| worker_heartbeat_timeout | pass | Worker registered, heartbeat timeout test structure valid |
| browser_failure | pass | Browser failure captured with structured error |
| voice_interruption | pass | Voice interruption handled correctly |
| tts_failure | pass | TTS failure captured with structured error |
| stt_failure | pass | STT failure captured with structured error |
| avatar_renderer_failure | pass | Fake avatar renderer produced frame without error |

---

## NOT_MEASURED Metrics

- **voice_latency_capture_to_stt_ms** (Voice Latency): Deterministic fixture only; no real microphone, STT, TTS, or hardware measurement.
- **voice_latency_stt_to_orchestrator_ms** (Voice Latency): Deterministic fixture only; no real microphone, STT, TTS, or hardware measurement.
- **voice_latency_orchestrator_to_tts_ms** (Voice Latency): Deterministic fixture only; no real microphone, STT, TTS, or hardware measurement.
- **voice_latency_tts_to_playback_start_ms** (Voice Latency): Deterministic fixture only; no real microphone, STT, TTS, or hardware measurement.
- **voice_latency_interruption_response_ms** (Voice Latency): Deterministic fixture only; no real microphone, STT, TTS, or hardware measurement.
- **verification_accuracy** (Prediction Calibration): FakePredictor produces heuristic estimates, not calibrated probabilities. Prediction calibration NOT_MEASURED.

---

## Limitations

1. All results are from **DETERMINISTIC FIXTURE** evaluation.
2. No real audio, STT, TTS, browser, or hardware measurements were taken.
3. Research results are fixture-based, not real web search.
4. Vision results are from FakeVisionProvider, not real screenshot analysis.
5. Memory results use InMemoryMemory, not semantic/vector search.
6. Prediction calibration is NOT_MEASURED (no calibrated ground truth).
7. Avatar lip-sync timing accuracy is NOT_MEASURED (no ground-truth timing dataset).
8. Voice latency values are fixture placeholders, not real measurements.
9. Computer task success uses FakeActionExecutor, not real filesystem operations.
10. Security policy uses ConservativePolicy in isolation, not full integration.

---

*Generated by MISSMINUTES Evaluation Framework (CHUNK 35)*
