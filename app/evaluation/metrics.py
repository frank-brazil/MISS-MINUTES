"""Metric definitions and computation functions for evaluation.

Every metric has an explicit definition, optional unit, and optional target.
Computation functions are pure and deterministic: they never depend on
external services, randomness, or time-varying state.

Anti-fabrication: metrics are only computed when corresponding real or fixture
data exists.  NOT_MEASURED is returned when data is unavailable.
"""

from app.evaluation.models import EvaluationCategory, EvaluationMetric


def compute_wer(reference: str, hypothesis: str) -> float:
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    n = len(ref_words)
    m = len(hyp_words)
    if n == 0 and m == 0:
        return 0.0
    if n == 0:
        return 1.0
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[n][m] / n


def compute_cer(reference: str, hypothesis: str) -> float:
    n = len(reference)
    m = len(hypothesis)
    if n == 0 and m == 0:
        return 0.0
    if n == 0:
        return 1.0
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if reference[i - 1] == hypothesis[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[n][m] / n


def compute_accuracy(correct: int, total: int) -> float:
    if total <= 0:
        raise ValueError("total must be positive")
    if correct < 0:
        raise ValueError("correct must be non-negative")
    return correct / total


def compute_pass_rate(passed: int, total: int) -> float:
    return compute_accuracy(passed, total)


def safe_divide(numerator: int, denominator: int) -> float:
    if denominator == 0:
        raise ValueError("denominator must not be zero")
    return numerator / denominator


METRICS: list[EvaluationMetric] = [
    EvaluationMetric(
        name="stt_word_error_rate",
        category=EvaluationCategory.STT,
        definition="Levenshtein word-level word error rate against reference transcript.",
        unit="ratio",
        target=0.0,
    ),
    EvaluationMetric(
        name="stt_character_error_rate",
        category=EvaluationCategory.STT,
        definition="Character-level character error rate against reference transcript.",
        unit="ratio",
        target=0.0,
    ),
    EvaluationMetric(
        name="language_detection_accuracy",
        category=EvaluationCategory.LANGUAGE_DETECTION,
        definition="Fraction of inputs where language or style was correctly detected.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="language_detection_confusion_count",
        category=EvaluationCategory.LANGUAGE_DETECTION,
        definition="Number of incorrect language/style detections.",
        unit="count",
    ),
    EvaluationMetric(
        name="routing_correct_rate",
        category=EvaluationCategory.TOOL_AGENT_ROUTING,
        definition="Fraction of cases where the correct agent and tool were selected.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="routing_failure_categories",
        category=EvaluationCategory.TOOL_AGENT_ROUTING,
        definition="Distribution of routing failure categories.",
        unit=None,
    ),
    EvaluationMetric(
        name="planning_valid_plan_rate",
        category=EvaluationCategory.PLANNING,
        definition="Fraction of plans that pass structural validation.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="planning_completion_rate",
        category=EvaluationCategory.PLANNING,
        definition="Fraction of plans that reach completion state.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="problem_solving_completion_rate",
        category=EvaluationCategory.PROBLEM_SOLVING,
        definition="Fraction of problem-solving sessions completing successfully.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="problem_solving_bounded_failure_rate",
        category=EvaluationCategory.PROBLEM_SOLVING,
        definition="Fraction of failures that terminate within the iteration budget.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="research_source_coverage",
        category=EvaluationCategory.RESEARCH,
        definition="Ratio of expected sources returned to expected sources.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="research_citation_presence",
        category=EvaluationCategory.RESEARCH,
        definition="Fraction of research cases where evidence or citations are present.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="research_result_limits_respected",
        category=EvaluationCategory.RESEARCH,
        definition="Fraction of research cases where max_results limit was respected.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="computer_task_success_rate",
        category=EvaluationCategory.COMPUTER,
        definition="Fraction of computer tool operations completing successfully.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="computer_safe_failure_rate",
        category=EvaluationCategory.COMPUTER,
        definition="Fraction of dangerous commands that are correctly denied.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="browser_safe_action_rate",
        category=EvaluationCategory.BROWSER,
        definition="Fraction of safe browser actions completing successfully.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="browser_unsafe_scheme_rejected",
        category=EvaluationCategory.BROWSER,
        definition="Fraction of unsafe URL schemes correctly rejected.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="browser_domain_policy_respected",
        category=EvaluationCategory.BROWSER,
        definition="Fraction of cases where domain policy is enforced.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="vision_observation_accuracy",
        category=EvaluationCategory.VISION,
        definition="Fraction of structured visual observations matching expected output.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="vision_untrusted_text_handling",
        category=EvaluationCategory.VISION,
        definition="Whether untrusted screen text remains observation data only.",
        unit="bool",
    ),
    EvaluationMetric(
        name="distributed_dispatch_success",
        category=EvaluationCategory.DISTRIBUTED,
        definition="Fraction of tasks dispatched successfully to workers.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="distributed_retry_success",
        category=EvaluationCategory.DISTRIBUTED,
        definition="Fraction of retries succeeding after initial failure.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="distributed_reroute_success",
        category=EvaluationCategory.DISTRIBUTED,
        definition="Fraction of reroutes to alternate worker succeeding.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="distributed_duplicate_prevention",
        category=EvaluationCategory.DISTRIBUTED,
        definition="Whether duplicate results are prevented from being applied.",
        unit="bool",
    ),
    EvaluationMetric(
        name="verification_accuracy",
        category=EvaluationCategory.VERIFICATION,
        definition="Fraction of verified results matching ground truth.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="verification_false_rate",
        category=EvaluationCategory.VERIFICATION,
        definition="Fraction of verifications that are false positives.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="verification_inconclusive_handling",
        category=EvaluationCategory.VERIFICATION,
        definition="Fraction of inconclusive cases handled with correct classification.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="voice_latency_capture_to_stt",
        category=EvaluationCategory.VOICE,
        definition="Fixture timing from audio capture to STT result. Not real latency.",
        unit="ms_fixture",
    ),
    EvaluationMetric(
        name="voice_latency_stt_to_orchestrator",
        category=EvaluationCategory.VOICE,
        definition="Fixture timing from STT result to orchestrator response. Not real latency.",
        unit="ms_fixture",
    ),
    EvaluationMetric(
        name="voice_latency_orchestrator_to_tts",
        category=EvaluationCategory.VOICE,
        definition="Fixture timing from orchestrator response to TTS result. Not real latency.",
        unit="ms_fixture",
    ),
    EvaluationMetric(
        name="voice_interruption_response",
        category=EvaluationCategory.VOICE,
        definition="Whether interruption stops playback and transitions to listening.",
        unit="bool",
    ),
    EvaluationMetric(
        name="avatar_event_propagation",
        category=EvaluationCategory.AVATAR,
        definition="Whether avatar state changes propagate correctly via events.",
        unit="bool",
    ),
    EvaluationMetric(
        name="avatar_voice_avatar_sync",
        category=EvaluationCategory.AVATAR,
        definition="Whether voice events trigger corresponding avatar state changes.",
        unit="bool",
    ),
    EvaluationMetric(
        name="memory_retrieval_success",
        category=EvaluationCategory.MEMORY,
        definition="Fraction of known records successfully retrieved.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="memory_relevant_retrieval",
        category=EvaluationCategory.MEMORY,
        definition="Fraction of retrieved records that are relevant to the query.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="memory_irrelevant_rejection",
        category=EvaluationCategory.MEMORY,
        definition="Fraction of irrelevant queries correctly returning empty results.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="e2e_task_completion_rate",
        category=EvaluationCategory.END_TO_END,
        definition="Fraction of full-pipeline tasks completing successfully.",
        unit="ratio",
    ),
    EvaluationMetric(
        name="e2e_failure_category",
        category=EvaluationCategory.END_TO_END,
        definition="Distribution of end-to-end failure categories.",
        unit=None,
    ),
    EvaluationMetric(
        name="security_unauthorized_path_denied",
        category=EvaluationCategory.SECURITY,
        definition="Whether unauthorized file paths are blocked before action.",
        unit="bool",
    ),
    EvaluationMetric(
        name="security_unsafe_terminal_denied",
        category=EvaluationCategory.SECURITY,
        definition="Whether unsafe terminal commands are blocked before action.",
        unit="bool",
    ),
    EvaluationMetric(
        name="security_unsafe_browser_denied",
        category=EvaluationCategory.SECURITY,
        definition="Whether unsafe browser URL schemes are blocked before action.",
        unit="bool",
    ),
    EvaluationMetric(
        name="security_forbidden_action_denied",
        category=EvaluationCategory.SECURITY,
        definition="Whether forbidden actions are blocked before action.",
        unit="bool",
    ),
    EvaluationMetric(
        name="security_missing_confirmation",
        category=EvaluationCategory.SECURITY,
        definition="Whether actions requiring confirmation prompt before execution.",
        unit="bool",
    ),
    EvaluationMetric(
        name="security_expired_confirmation",
        category=EvaluationCategory.SECURITY,
        definition="Whether expired confirmations are rejected.",
        unit="bool",
    ),
    EvaluationMetric(
        name="security_untrusted_vision_text",
        category=EvaluationCategory.SECURITY,
        definition="Whether untrusted screen text remains observation data only.",
        unit="bool",
    ),
    EvaluationMetric(
        name="reliability_provider_failure",
        category=EvaluationCategory.RELIABILITY,
        definition="Whether provider failures are handled safely with structured errors.",
        unit="bool",
    ),
    EvaluationMetric(
        name="reliability_tool_failure",
        category=EvaluationCategory.RELIABILITY,
        definition="Whether tool failures are handled safely with structured errors.",
        unit="bool",
    ),
    EvaluationMetric(
        name="reliability_no_infinite_loops",
        category=EvaluationCategory.RELIABILITY,
        definition="Whether all autonomous loops terminate within budget.",
        unit="bool",
    ),
    EvaluationMetric(
        name="reliability_respects_timeout",
        category=EvaluationCategory.RELIABILITY,
        definition="Whether timeouts are enforced and execution stops.",
        unit="bool",
    ),
    EvaluationMetric(
        name="reliability_respects_cancellation",
        category=EvaluationCategory.RELIABILITY,
        definition="Whether cancellation is respected at the next safe boundary.",
        unit="bool",
    ),
    EvaluationMetric(
        name="reliability_security_not_bypassed",
        category=EvaluationCategory.RELIABILITY,
        definition="Whether security checks are never bypassed under failure conditions.",
        unit="bool",
    ),
]
