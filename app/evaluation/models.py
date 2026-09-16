"""Evaluation and reliability framework data models.

All models are intentionally standalone: they depend on neither the runtime,
the orchestrator, nor any model provider.  They carry only structured metadata
suitable for deterministic offline evaluation.

Anti-fabrication note: a metric is never claimed to have been measured when the
required real test data or provider was unavailable.  ``NOT_MEASURED`` is used
explicitly in that case.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(UTC)


class EvaluationCategory(StrEnum):
    STT = "stt"
    LANGUAGE_DETECTION = "language_detection"
    TOOL_AGENT_ROUTING = "tool_agent_routing"
    PLANNING = "planning"
    PROBLEM_SOLVING = "problem_solving"
    RESEARCH = "research"
    COMPUTER = "computer"
    BROWSER = "browser"
    VISION = "vision"
    DISTRIBUTED = "distributed"
    PREDICTION = "prediction"
    VERIFICATION = "verification"
    VOICE = "voice"
    AVATAR = "avatar"
    MEMORY = "memory"
    END_TO_END = "end_to_end"
    SECURITY = "security"
    RELIABILITY = "reliability"


class ResultClassification(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    NOT_MEASURED = "not_measured"
    NOT_APPLICABLE = "not_applicable"


class EvaluationMode(StrEnum):
    DETERMINISTIC = "deterministic"
    LIVE = "live"


class RoutingDecision(StrEnum):
    CORRECT = "correct"
    INCORRECT_AGENT = "incorrect_agent"
    INCORRECT_TOOL = "incorrect_tool"
    NO_MATCH = "no_match"
    SECURITY_DENIED = "security_denied"


class FailureCategory(StrEnum):
    PROVIDER_ERROR = "provider_error"
    TOOL_ERROR = "tool_error"
    AGENT_ERROR = "agent_error"
    PLANNER_ERROR = "planner_error"
    TIMEOUT = "timeout"
    CANCELLATION = "cancellation"
    VERIFICATION_FAILURE = "verification_failure"
    SECURITY_DENIED = "security_denied"
    WORKER_ERROR = "worker_error"
    DUPLICATE_RESULT = "duplicate_result"


class EvaluationScenario(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    scenario_id: UUID = Field(default_factory=uuid4)
    name: str
    category: EvaluationCategory
    description: str
    tags: frozenset[str] = Field(default_factory=frozenset)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be blank")
        return v

    @field_validator("description")
    @classmethod
    def _description_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must not be blank")
        return v


class RoutingMetadata(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    expected_agent: str
    expected_tool: str | None = None
    actual_agent: str | None = None
    actual_tool: str | None = None
    decision: RoutingDecision = RoutingDecision.CORRECT
    reason: str | None = None


class EvaluationCase(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    case_id: UUID = Field(default_factory=uuid4)
    scenario_id: UUID
    input: dict[str, Any] = Field(default_factory=dict)
    expected_behavior: str
    expected_result: dict[str, Any] | None = None
    expected_routing: RoutingMetadata | None = None

    @field_validator("expected_behavior")
    @classmethod
    def _behavior_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("expected_behavior must not be blank")
        return v


class EvaluationMetric(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    name: str
    category: EvaluationCategory
    definition: str
    unit: str | None = None
    target: float | None = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be blank")
        return v

    @field_validator("definition")
    @classmethod
    def _definition_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("definition must not be blank")
        return v


class EvaluationResult(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    metric: str
    scenario: str
    case_id: UUID | None = None
    value: float | None = None
    status: ResultClassification
    evidence: str | None = None
    limitations: str | None = None
    mode: EvaluationMode = EvaluationMode.DETERMINISTIC


class EnvironmentInfo(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    mode: EvaluationMode = EvaluationMode.DETERMINISTIC
    python_version: str = ""
    platform: str = ""
    deterministic_fakes_used: list[str] = Field(default_factory=list)
    live_providers_used: list[str] = Field(default_factory=list)


class EvaluationSummary(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    total_metrics: int = 0
    pass_count: int = 0
    fail_count: int = 0
    inconclusive_count: int = 0
    not_measured_count: int = 0
    not_applicable_count: int = 0
    duration_seconds: float | None = None
    reliability_pass: int = 0
    reliability_fail: int = 0
    reliability_not_applicable: int = 0


class ReliabilityScenario(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    scenario_id: UUID = Field(default_factory=uuid4)
    name: str
    description: str
    failure_type: FailureCategory
    expected_behavior: str

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be blank")
        return v


class ReliabilityResult(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    scenario_id: UUID
    scenario_name: str
    status: ResultClassification
    details: str | None = None
    evidence: str | None = None
    mode: EvaluationMode = EvaluationMode.DETERMINISTIC


class EvaluationRun(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    run_id: UUID = Field(default_factory=uuid4)
    started_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = None
    environment: EnvironmentInfo = Field(default_factory=EnvironmentInfo)
    results: list[EvaluationResult] = Field(default_factory=list)
    reliability_results: list[ReliabilityResult] = Field(default_factory=list)
    summary: EvaluationSummary | None = None


class RegressionGate(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    name: str
    description: str
    metric_name: str
    required_status: ResultClassification = ResultClassification.PASS
    enabled: bool = True


REGRESSION_GATES: list[RegressionGate] = [
    RegressionGate(
        name="zero_security_bypasses",
        description="Security metrics must all pass",
        metric_name="security_*",
        required_status=ResultClassification.PASS,
    ),
    RegressionGate(
        name="zero_infinite_loops",
        description="Bounded loop tests must pass",
        metric_name="reliability_no_infinite_loops",
        required_status=ResultClassification.PASS,
    ),
    RegressionGate(
        name="zero_unhandled_deterministic_failures",
        description="No FAIL in deterministic mode",
        metric_name="*",
        required_status=ResultClassification.PASS,
    ),
    RegressionGate(
        name="verification_inconclusive_not_verified",
        description="INCONCLUSIVE must not be converted to PASS",
        metric_name="verification_*",
        required_status=ResultClassification.INCONCLUSIVE,
    ),
    RegressionGate(
        name="duplicate_result_not_applied",
        description="Duplicate results must not be applied",
        metric_name="distributed_duplicate_prevention",
        required_status=ResultClassification.PASS,
    ),
    RegressionGate(
        name="unsafe_terminal_denied",
        description="Unsafe terminal commands must be denied",
        metric_name="security_unsafe_terminal_denied",
        required_status=ResultClassification.PASS,
    ),
    RegressionGate(
        name="unsafe_browser_denied",
        description="Unsafe browser schemes must be denied",
        metric_name="security_unsafe_browser_denied",
        required_status=ResultClassification.PASS,
    ),
]
