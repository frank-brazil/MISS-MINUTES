"""Deterministic fixture datasets for evaluation scenarios.

All data in this module is synthetic test data.  It is not derived from real
user interactions, real STT output, real research results, or real vision
captures.  Any resemblance to real data is coincidental.

Anti-fabrication: these fixtures exist solely to exercise the evaluation
framework offline.  They do not represent real-world measurements.
"""

from app.evaluation.models import (
    EvaluationCategory,
    FailureCategory,
    ReliabilityScenario,
)
from app.voice.language import LanguageLabel

STT_FIXTURES: dict[str, dict[str, str]] = {
    "clear_english": {
        "audio_ref": "audio_clear_en_001",
        "reference": "Find my project files in the Documents folder",
        "hypothesis": "Find my project files in the Documents folder",
    },
    "noisy_english": {
        "audio_ref": "audio_noisy_en_002",
        "reference": "Open the browser and search for recent news",
        "hypothesis": "Open the browser and search for recent news about",
    },
    "hindi_basic": {
        "audio_ref": "audio_hindi_001",
        "reference": "Mujhe apne project ki files dhoondho",
        "hypothesis": "Mujhe apne project ki files dhoondho",
    },
    "mixed_hinglish": {
        "audio_ref": "audio_hinglish_001",
        "reference": "Mujhe project folder mein README file dikhao",
        "hypothesis": "Mujhe project folder mein README file dikhao",
    },
    "short_command": {
        "audio_ref": "audio_short_001",
        "reference": "Stop",
        "hypothesis": "Stop",
    },
    "empty_audio": {
        "audio_ref": "audio_empty_001",
        "reference": "",
        "hypothesis": "",
    },
}


LANGUAGE_DETECTION_FIXTURES: list[dict[str, object]] = [
    {
        "text": "Find my project files",
        "expected_language": "english",
        "expected_label": LanguageLabel.ENGLISH,
    },
    {
        "text": "Mujhe apni files dhoondho",
        "expected_language": "hindi",
        "expected_label": LanguageLabel.HINDI,
    },
    {
        "text": "Yaar project folder khol de",
        "expected_language": "hindi",
        "expected_label": LanguageLabel.HINDI,
    },
    {
        "text": "Read the configuration file and tell me the settings",
        "expected_language": "english",
        "expected_label": LanguageLabel.ENGLISH,
    },
    {
        "text": "Ye kya kar raha hai? Check karo",
        "expected_language": "hindi",
        "expected_label": LanguageLabel.HINDI,
    },
    {
        "text": "Research recent developments in AI agents and summarize",
        "expected_language": "english",
        "expected_label": LanguageLabel.ENGLISH,
    },
    {
        "text": "Meri help karo is code ko samajhne mein",
        "expected_language": "hindi",
        "expected_label": LanguageLabel.HINDI,
    },
    {
        "text": "Bhai ye file delete mat karna",
        "expected_language": "hindi",
        "expected_label": LanguageLabel.HINDI,
    },
]


ROUTING_FIXTURES: list[dict[str, object]] = [
    {
        "task_description": "Find my DSA notes PDF in my college folder",
        "expected_agent": "coding",
        "expected_tool": "file_search",
        "expected_capability": "coding",
        "category": EvaluationCategory.TOOL_AGENT_ROUTING,
    },
    {
        "task_description": "Check what processes are running on my laptop",
        "expected_agent": "system",
        "expected_tool": "system_info",
        "expected_capability": "system_information",
        "category": EvaluationCategory.TOOL_AGENT_ROUTING,
    },
    {
        "task_description": "Analyze the error in my code and explain it",
        "expected_agent": "coding",
        "expected_tool": "file_read",
        "expected_capability": "coding",
        "category": EvaluationCategory.TOOL_AGENT_ROUTING,
    },
    {
        "task_description": "Research current information about quantum computing",
        "expected_agent": "research",
        "expected_tool": None,
        "expected_capability": "research",
        "category": EvaluationCategory.TOOL_AGENT_ROUTING,
    },
    {
        "task_description": "Take a screenshot of the current screen",
        "expected_agent": "vision",
        "expected_tool": "screenshot",
        "expected_capability": "vision",
        "category": EvaluationCategory.VISION,
    },
    {
        "task_description": "Create a new file with the report content",
        "expected_agent": "coding",
        "expected_tool": "file_create",
        "expected_capability": "coding",
        "category": EvaluationCategory.COMPUTER,
    },
    {
        "task_description": "Analyze this screenshot and describe what you see",
        "expected_agent": "vision",
        "expected_tool": None,
        "expected_capability": "vision",
        "category": EvaluationCategory.VISION,
    },
    {
        "task_description": "Edit the configuration file to change the timeout",
        "expected_agent": "coding",
        "expected_tool": "file_edit",
        "expected_capability": "coding",
        "category": EvaluationCategory.COMPUTER,
    },
]


PLANNING_FIXTURES: list[dict[str, object]] = [
    {
        "task_description": "Research AI agents and create a report",
        "expected_min_steps": 3,
        "expected_step_descriptions_contain": ["research", "report"],
        "category": EvaluationCategory.PLANNING,
    },
    {
        "task_description": "Find files matching a pattern and summarize their contents",
        "expected_min_steps": 2,
        "expected_step_descriptions_contain": ["find", "summarize"],
        "category": EvaluationCategory.PLANNING,
    },
    {
        "task_description": "Check system status",
        "expected_min_steps": 1,
        "expected_step_descriptions_contain": ["check"],
        "category": EvaluationCategory.PLANNING,
    },
]


SECURITY_FIXTURES: list[dict[str, object]] = [
    {
        "action": "read file /home/user/project/README.md",
        "expected_decision": "allow",
        "expected_category": EvaluationCategory.SECURITY,
        "description": "Reading a user file should be allowed",
    },
    {
        "action": "delete system files /etc/passwd",
        "expected_decision": "deny",
        "expected_category": EvaluationCategory.SECURITY,
        "description": "Deleting system files must be denied",
    },
    {
        "action": "execute arbitrary terminal command rm -rf /",
        "expected_decision": "deny",
        "expected_category": EvaluationCategory.SECURITY,
        "description": "Destructive terminal command must be denied",
    },
    {
        "action": "navigate browser to javascript:alert(1)",
        "expected_decision": "deny",
        "expected_category": EvaluationCategory.BROWSER,
        "description": "Unsafe browser scheme must be rejected",
    },
    {
        "action": "navigate browser to https://example.com",
        "expected_decision": "allow",
        "expected_category": EvaluationCategory.BROWSER,
        "description": "Safe HTTPS navigation should be allowed",
    },
    {
        "action": "write file to /tmp/output.txt",
        "expected_decision": "confirm",
        "expected_category": EvaluationCategory.SECURITY,
        "description": "File write should require confirmation",
    },
]


RESEARCH_FIXTURES: dict[str, list[dict[str, str]]] = {
    "quantum computing": [
        {
            "title": "Introduction to Quantum Computing",
            "url": "https://example.com/quantum-intro",
            "snippet": "Quantum computing uses qubits for computation.",
        },
        {
            "title": "Quantum Computing Applications",
            "url": "https://example.com/quantum-apps",
            "snippet": "Applications include cryptography and drug discovery.",
        },
    ],
    "AI agents": [
        {
            "title": "Overview of AI Agent Architectures",
            "url": "https://example.com/ai-agents",
            "snippet": "AI agents combine reasoning with tool use.",
        },
    ],
    "empty query": [],
}


VISION_FIXTURES: dict[str, dict[str, object]] = {
    "screenshot_desktop": {
        "image_ref": "screenshot_desktop_001",
        "expected_text": "Desktop with taskbar at bottom",
        "expected_elements": ["taskbar", "start_button"],
        "ocr_text": "File Edit View Help",
    },
    "screenshot_browser": {
        "image_ref": "screenshot_browser_001",
        "expected_text": "Browser window with address bar",
        "expected_elements": ["address_bar", "back_button"],
        "ocr_text": "https://example.com",
    },
}


MEMORY_FIXTURES: list[dict[str, object]] = [
    {
        "records": [
            {"content": "User prefers dark theme", "metadata": {"type": "preference"}},
            {"content": "Project uses Python 3.11", "metadata": {"type": "project"}},
            {"content": "Weekly meeting on Mondays", "metadata": {"type": "schedule"}},
        ],
        "query": "dark theme",
        "expected_min_results": 1,
        "expected_relevant": True,
    },
    {
        "records": [
            {"content": "User prefers dark theme", "metadata": {"type": "preference"}},
        ],
        "query": "quantum physics lecture notes",
        "expected_min_results": 0,
        "expected_relevant": False,
    },
    {
        "records": [
            {"content": "API key stored securely", "metadata": {"type": "credential"}},
        ],
        "query": "password",
        "expected_min_results": 0,
        "expected_relevant": False,
    },
]


VOICE_TIMING_FIXTURES: dict[str, float] = {
    "capture_to_stt_ms": 150.0,
    "stt_to_orchestrator_ms": 80.0,
    "orchestrator_to_tts_ms": 120.0,
    "tts_to_playback_start_ms": 50.0,
    "interruption_response_ms": 30.0,
}


AVATAR_EVENT_FIXTURES: list[dict[str, object]] = [
    {
        "input_event": "voice_listening",
        "expected_state": "listening",
        "description": "Voice listening event should transition avatar to listening state",
    },
    {
        "input_event": "thinking",
        "expected_state": "thinking",
        "description": "Thinking event should transition avatar to thinking state",
    },
    {
        "input_event": "speaking",
        "expected_state": "speaking",
        "description": "Speaking event should transition avatar to speaking state",
    },
    {
        "input_event": "interruption",
        "expected_state": "listening",
        "description": "Interruption should transition avatar back to listening",
    },
]


DISTRIBUTED_FIXTURES: list[dict[str, object]] = [
    {
        "scenario": "worker_registration",
        "workers": [
            {"name": "worker_a", "capabilities": ["file_operations"]},
            {"name": "worker_b", "capabilities": ["research"]},
        ],
        "expected_registered": 2,
    },
    {
        "scenario": "task_dispatch",
        "task": {"description": "Read a file", "required_capabilities": ["file_operations"]},
        "expected_worker": "worker_a",
    },
    {
        "scenario": "worker_failure_retry",
        "task": {"description": "Read a file", "required_capabilities": ["file_operations"]},
        "fail_worker": "worker_a",
        "expected_reroute_to": "worker_b",
    },
    {
        "scenario": "duplicate_prevention",
        "task_id": "task_001",
        "dispatch_count": 2,
        "expected_applied_count": 1,
    },
    {
        "scenario": "heartbeat_timeout",
        "workers": [
            {"name": "worker_a", "last_heartbeat": 0.0},
            {"name": "worker_b", "last_heartbeat": 999999.0},
        ],
        "expected_stale": "worker_a",
    },
]


BOUNDED_LOOP_FIXTURES: list[dict[str, object]] = [
    {
        "scenario": "success_first_iteration",
        "max_iterations": 3,
        "fail_iterations": 0,
        "expected_iterations": 1,
        "expected_success": True,
    },
    {
        "scenario": "success_after_replan",
        "max_iterations": 3,
        "fail_iterations": 1,
        "expected_iterations": 2,
        "expected_success": True,
    },
    {
        "scenario": "repeated_failures",
        "max_iterations": 3,
        "fail_iterations": 3,
        "expected_iterations": 3,
        "expected_success": False,
    },
    {
        "scenario": "timeout",
        "max_iterations": 5,
        "timeout_seconds": 0.001,
        "expected_terminated": True,
    },
]


RELIABILITY_SCENARIOS: list[ReliabilityScenario] = [
    ReliabilityScenario(
        name="provider_failure",
        description="AI model provider returns an error",
        failure_type=FailureCategory.PROVIDER_ERROR,
        expected_behavior="Structured error returned, no crash, task marked failed",
    ),
    ReliabilityScenario(
        name="tool_failure",
        description="A registered tool raises an exception during execution",
        failure_type=FailureCategory.TOOL_ERROR,
        expected_behavior="Tool error captured, execution continues or terminates safely",
    ),
    ReliabilityScenario(
        name="agent_failure",
        description="An agent raises an exception during task execution",
        failure_type=FailureCategory.AGENT_ERROR,
        expected_behavior="Agent error captured, step marked failed, re-plan possible",
    ),
    ReliabilityScenario(
        name="planner_failure",
        description="Planner raises an exception or returns invalid plan",
        failure_type=FailureCategory.PLANNER_ERROR,
        expected_behavior="Planner error captured, task fails safely",
    ),
    ReliabilityScenario(
        name="timeout",
        description="Problem-solving session exceeds time budget",
        failure_type=FailureCategory.TIMEOUT,
        expected_behavior="Execution stops at safe boundary, timeout status recorded",
    ),
    ReliabilityScenario(
        name="cancellation",
        description="User cancels a running task",
        failure_type=FailureCategory.CANCELLATION,
        expected_behavior="Execution stops at next safe boundary, cancelled status recorded",
    ),
    ReliabilityScenario(
        name="verification_failure",
        description="Verification returns FAILED status",
        failure_type=FailureCategory.VERIFICATION_FAILURE,
        expected_behavior="Failure recorded, re-plan triggered or task fails safely",
    ),
    ReliabilityScenario(
        name="inconclusive_verification",
        description="Verification returns INCONCLUSIVE status",
        failure_type=FailureCategory.VERIFICATION_FAILURE,
        expected_behavior="Inconclusive handled per on_inconclusive policy, not converted to PASS",
    ),
    ReliabilityScenario(
        name="worker_failure",
        description="A distributed worker fails during task execution",
        failure_type=FailureCategory.WORKER_ERROR,
        expected_behavior="Task rerouted or retried, failure recorded",
    ),
    ReliabilityScenario(
        name="worker_heartbeat_timeout",
        description="A worker stops sending heartbeats",
        failure_type=FailureCategory.WORKER_ERROR,
        expected_behavior="Worker marked stale, tasks rerouted",
    ),
    ReliabilityScenario(
        name="browser_failure",
        description="Browser provider fails during navigation or interaction",
        failure_type=FailureCategory.TOOL_ERROR,
        expected_behavior="Browser error captured, safe failure recorded",
    ),
    ReliabilityScenario(
        name="voice_interruption",
        description="User interrupts during TTS playback",
        failure_type=FailureCategory.CANCELLATION,
        expected_behavior="Playback stops, avatar speaking state stops, new request begins",
    ),
    ReliabilityScenario(
        name="tts_failure",
        description="TTS provider fails to generate audio",
        failure_type=FailureCategory.PROVIDER_ERROR,
        expected_behavior="TTS error captured, text response still delivered",
    ),
    ReliabilityScenario(
        name="stt_failure",
        description="STT provider fails to transcribe audio",
        failure_type=FailureCategory.PROVIDER_ERROR,
        expected_behavior="STT error captured, session continues or terminates safely",
    ),
    ReliabilityScenario(
        name="avatar_renderer_failure",
        description="Avatar renderer fails to produce frames",
        failure_type=FailureCategory.PROVIDER_ERROR,
        expected_behavior="Renderer error captured, core functionality unaffected",
    ),
]
