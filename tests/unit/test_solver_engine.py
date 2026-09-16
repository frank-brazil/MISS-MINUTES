import asyncio
from uuid import UUID

import pytest

from app.agents.base import Agent, AgentResult
from app.core.critic import (
    Critic,
    Critique,
    CritiqueAspect,
    CritiquePoint,
    CritiqueRequest,
    FakeCritic,
    Severity,
)
from app.core.planner import Plan, Planner, PlanStep
from app.core.prediction import FakePredictor
from app.core.problem_solver import (
    Hypothesis,
    Problem,
    ProblemAnalysis,
    ProblemSolver,
    RiskLevel,
    Solution,
)
from app.core.routing import AgentRouter
from app.core.task import Task
from app.core.verification import (
    FakeVerifier,
    VerificationResult,
    VerificationStatus,
    Verifier,
)
from app.memory.base import Memory, MemoryQueryResult, MemoryRecord
from app.research.fakes import FakeResearchProvider
from app.solver.actions import ActionExecutor, ActionRequest, ActionResult
from app.solver.engine import ProblemSolvingEngine
from app.solver.events import ExecutionEventType
from app.solver.fakes import FakeActionExecutor, FakeObservationProvider
from app.solver.observation import (
    ObservationProvider,
    ObservationRequest,
    ObservationResult,
)
from app.solver.session import ProblemSolvingStatus


def _run(coro):
    return asyncio.run(coro)


# ----------------------------------------------------------------------
# Test-local deterministic components
# ----------------------------------------------------------------------


class SolverStub(ProblemSolver):
    name = "solver-stub"
    description = "Deterministic solver stub for engine tests."

    def __init__(
        self,
        *,
        expected_outcome: str | None = None,
        unresolved_questions: list[str] | None = None,
        raise_error: Exception | None = None,
    ) -> None:
        self._expected_outcome = expected_outcome
        self._unresolved_questions = list(
            unresolved_questions
            if unresolved_questions is not None
            else ["Which evidence is strongest?"]
        )
        self._raise_error = raise_error
        self.requests: list[Problem] = []

    async def solve(self, problem: Problem) -> ProblemAnalysis:
        self.requests.append(problem)
        if self._raise_error is not None:
            raise self._raise_error
        solution = Solution(
            description="apply the tested fix",
            expected_outcome=self._expected_outcome,
            risk=RiskLevel.LOW,
        )
        return ProblemAnalysis(
            problem=problem,
            hypotheses=[Hypothesis(description="possible cause")],
            candidate_solutions=[solution],
            recommended_solution_id=solution.solution_id,
            unresolved_questions=list(self._unresolved_questions),
        )


class AgentStub(Agent):
    name = "stub-agent"
    description = "Stub agent for solver tests."
    capabilities = frozenset()

    def __init__(self, error: str | None = None) -> None:
        self._error = error
        self.calls: list[Task] = []

    async def execute(self, task: Task) -> AgentResult:
        self.calls.append(task)
        if self._error is not None:
            return AgentResult.fail(error=self._error)
        return AgentResult.ok(output="done")


class ScriptedAgent(Agent):
    name = "scripted-agent"
    description = "Agent that follows a scripted outcome list."
    capabilities = frozenset()

    def __init__(
        self,
        outcomes: list[bool],
        error: str = "simulated agent failure",
    ) -> None:
        self._outcomes = list(outcomes)
        self._error = error
        self.calls: list[str] = []

    async def execute(self, task: Task) -> AgentResult:
        self.calls.append(task.description)
        ok = self._outcomes.pop(0) if self._outcomes else True
        if ok:
            return AgentResult.ok(output="done")
        return AgentResult.fail(error=self._error)


class SlowAgent(Agent):
    name = "slow-agent"
    description = "Agent that sleeps briefly so cancellation can be polled."
    capabilities = frozenset()

    async def execute(self, task: Task) -> AgentResult:
        await asyncio.sleep(0.05)
        return AgentResult.ok(output="done")


class RecordingPlanner(Planner):
    name = "recording-planner"
    description = "Planner that records the tasks it plans for."

    def __init__(self, step_descriptions: list[str]) -> None:
        self._step_descriptions = list(step_descriptions)
        self.calls: list[Task] = []

    async def plan(self, task: Task) -> Plan:
        self.calls.append(task)
        steps = [PlanStep(description=d) for d in self._step_descriptions]
        return Plan(task_id=task.task_id, goal=task.description, steps=steps)


class FailingPlanner(Planner):
    name = "failing-planner"
    description = "Planner that always raises a runtime error."

    async def plan(self, task: Task) -> Plan:
        raise RuntimeError("planner is down")


class ScriptedVerifier(Verifier):
    name = "scripted-verifier"
    description = "Verifier that follows a scripted status list."

    def __init__(self, statuses: list[VerificationStatus]) -> None:
        self._statuses = list(statuses)
        self.requests: list[tuple[object, object]] = []

    async def verify(
        self, expectation, observation
    ) -> VerificationResult:
        self.requests.append((expectation, observation))
        status = (
            self._statuses.pop(0)
            if self._statuses
            else VerificationStatus.INCONCLUSIVE
        )
        return VerificationResult(
            status=status,
            expectation=expectation,
            observed_outcome=observation.description,
            discrepancy=(
                None
                if status is VerificationStatus.VERIFIED
                else "simulated discrepancy."
            ),
            error=None,
            confidence=None
            if status is VerificationStatus.NOT_RUN
            else 0.5,
        )


class ScriptedCritic(Critic):
    name = "scripted-critic"
    description = "Critic that follows a scripted highest-severity list."

    def __init__(self, severities: list[Severity]) -> None:
        self._severities = list(severities)
        self.requests: list[CritiqueRequest] = []

    async def critique(self, request: CritiqueRequest) -> Critique:
        self.requests.append(request)
        severity = (
            self._severities.pop(0)
            if self._severities
            else Severity.LOW
        )
        point = CritiquePoint(
            aspect=CritiqueAspect.RISK,
            description="scripted severity point",
            severity=severity,
            confidence=0.5,
        )
        return Critique(
            target=request.target,
            points=[point],
            overall_severity=severity,
            confidence=0.5,
        )


class ScriptedActionExecutor(ActionExecutor):
    name = "scripted-action-executor"
    description = "Action executor that follows a scripted outcome list."

    def __init__(
        self,
        outcomes: list[bool],
        output: str = "done",
        error: str = "simulated action failure",
    ) -> None:
        self._outcomes = list(outcomes)
        self._output = output
        self._error = error
        self.requests: list[ActionRequest] = []

    async def execute(self, request: ActionRequest) -> ActionResult:
        self.requests.append(request)
        ok = self._outcomes.pop(0) if self._outcomes else True
        if ok:
            return ActionResult.ok(request.action_id, output=self._output)
        return ActionResult.fail(request.action_id, error=self._error)


class RaiseOnceActionExecutor(ActionExecutor):
    name = "raise-once-action-executor"
    description = "Raises once, then succeeds (engine tests)."

    def __init__(self) -> None:
        self._raised = False
        self.calls = 0

    async def execute(self, request: ActionRequest) -> ActionResult:
        self.calls += 1
        if not self._raised:
            self._raised = True
            raise RuntimeError("boom")
        return ActionResult.ok(request.action_id, output="done")


class AlwaysRaiseActionExecutor(ActionExecutor):
    name = "always-raise-action-executor"
    description = "Always raises (engine tests)."

    async def execute(self, request: ActionRequest) -> ActionResult:
        raise RuntimeError("boom")


class SlowActionExecutor(ActionExecutor):
    name = "slow-action-executor"
    description = "Sleeps for a long time so timeout tests can fire."

    async def execute(self, request: ActionRequest) -> ActionResult:
        await asyncio.sleep(60)
        return ActionResult.ok(request.action_id, output="slow")


class RecordingMemory(Memory):
    name = "recording-memory"
    description = "Recording memory for engine tests."

    def __init__(self, fail: bool = False) -> None:
        self._fail = fail
        self.records: list[MemoryRecord] = []

    async def store(self, record: MemoryRecord) -> MemoryRecord:
        if self._fail:
            raise RuntimeError("db down")
        self.records.append(record)
        return record

    async def retrieve(
        self, query: str, *, limit: int = 10
    ) -> MemoryQueryResult:
        return MemoryQueryResult.ok([])

    async def delete(self, memory_id: UUID) -> bool:
        return False


# ----------------------------------------------------------------------
# Engine factory
# ----------------------------------------------------------------------


def make_engine(
    *,
    solver: ProblemSolver | None = None,
    planner: Planner | None = None,
    agents: list[Agent] | None = None,
    research: FakeResearchProvider | None = None,
    predictor=None,
    critic=None,
    verifier=None,
    action: ActionExecutor | None = None,
    observation: ObservationProvider | None = None,
    memory: Memory | None = None,
    include_predictor: bool = True,
    include_critic: bool = True,
    include_verifier: bool = True,
    include_observation: bool = True,
    **kwargs,
) -> ProblemSolvingEngine:
    return ProblemSolvingEngine(
        problem_solver=solver or SolverStub(expected_outcome="expected sign"),
        planner=planner or RecordingPlanner(["step one"]),
        agent_router=AgentRouter(
            agents if agents is not None else [AgentStub()]
        ),
        research_provider=research,
        predictor=predictor or (FakePredictor() if include_predictor else None),
        critic=critic or (FakeCritic() if include_critic else None),
        verifier=verifier or (FakeVerifier() if include_verifier else None),
        action_executor=action if action is not None else FakeActionExecutor(),
        observation_provider=(
            observation
            if observation is not None
            else (
                FakeObservationProvider(
                    observations=["expected sign observed"],
                    action_succeeded=True,
                )
                if include_observation
                else None
            )
        ),
        memory=memory,
        **kwargs,
    )


# ----------------------------------------------------------------------
# Construction / accessors
# ----------------------------------------------------------------------


def test_engine_requires_core_components() -> None:
    with pytest.raises(TypeError):
        ProblemSolvingEngine()  # type: ignore[call-arg]


def test_engine_defaults_use_safe_fakes() -> None:
    engine = make_engine()
    assert isinstance(engine.action_executor, FakeActionExecutor)
    assert isinstance(engine.observation_provider, FakeObservationProvider)
    assert engine.max_iterations == 3
    assert engine.timeout_seconds is None
    assert engine.memory is None
    assert engine.verifier is not None
    assert engine.critic is not None
    assert engine.predictor is not None


def test_engine_exposes_components() -> None:
    solver = SolverStub()
    planner = RecordingPlanner(["a"])
    agent = AgentStub()
    verifier = ScriptedVerifier([VerificationStatus.VERIFIED])
    action = FakeActionExecutor()
    observation = FakeObservationProvider()
    engine = ProblemSolvingEngine(
        problem_solver=solver,
        planner=planner,
        agent_router=AgentRouter([agent]),
        verifier=verifier,
        action_executor=action,
        observation_provider=observation,
    )
    assert engine.problem_solver is solver
    assert engine.planner is planner
    assert engine.agent_router.agents() == (agent,)
    assert engine.verifier is verifier
    assert engine.action_executor is action
    assert engine.observation_provider is observation


def test_engine_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="max_iterations"):
        make_engine(max_iterations=0)
    with pytest.raises(ValueError, match="timeout_seconds"):
        make_engine(timeout_seconds=0)
    with pytest.raises(ValueError, match="timeout_seconds"):
        make_engine(timeout_seconds=-1)
    with pytest.raises(ValueError, match="on_inconclusive"):
        make_engine(on_inconclusive="accept")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="max_research_queries"):
        make_engine(max_research_queries=0)


def test_create_session_and_registry() -> None:
    engine = make_engine()
    task = Task(description="registry")
    session = engine.create_session(task)
    assert session.task_id == task.task_id
    assert session.max_iterations == engine.max_iterations
    assert engine.get_session(session.session_id) is session
    assert len(engine.sessions()) == 1


def test_cancel_unknown_session_returns_false() -> None:
    engine = make_engine()
    assert engine.cancel(UUID(int=999)) is False


def test_cancel_known_session_requests_stop() -> None:
    engine = make_engine()
    task = Task(description="cancel")
    session = engine.create_session(task)
    assert engine.cancel(session.session_id) is True
    assert engine.cancel(session.session_id) is False


# ----------------------------------------------------------------------
# Happy paths
# ----------------------------------------------------------------------


def test_minimal_engine_completes_unverified() -> None:
    engine = ProblemSolvingEngine(
        problem_solver=SolverStub(),
        planner=RecordingPlanner(["step one"]),
        agent_router=AgentRouter([AgentStub()]),
    )
    task = Task(description="minimal")
    result = _run(engine.solve(task))
    assert result.success is True
    assert result.status is ProblemSolvingStatus.COMPLETED
    assert result.verification_status is VerificationStatus.NOT_RUN
    assert result.iterations_used == 1
    assert result.completed_steps == ["step one"]
    assert any(
        event.event_type is ExecutionEventType.NOTICE for event in result.events
    )


def test_happy_path_verified() -> None:
    engine = make_engine()
    task = Task(description="happy")
    result = _run(engine.solve(task))
    assert result.success is True
    assert result.status is ProblemSolvingStatus.COMPLETED
    assert result.verification_status is VerificationStatus.VERIFIED
    assert result.iterations_used == 1
    assert result.completed_steps == ["step one"]
    assert result.final_output is not None
    types = {event.event_type for event in result.events}
    assert ExecutionEventType.UNDERSTANDING in types
    assert ExecutionEventType.PLAN in types
    assert ExecutionEventType.DELEGATION in types
    assert ExecutionEventType.PREDICTION in types
    assert ExecutionEventType.CRITIQUE in types
    assert ExecutionEventType.ACTION in types
    assert ExecutionEventType.OBSERVATION in types
    assert ExecutionEventType.VERIFICATION in types
    assert ExecutionEventType.COMPLETED in types
    session = engine.get_session(result.session_id)
    assert session is not None
    assert session.status is ProblemSolvingStatus.COMPLETED
    assert result.session_id == session.session_id


def test_happy_path_uses_real_fake_verifier() -> None:
    solver = SolverStub(expected_outcome="the expected marker")
    observation = FakeObservationProvider(
        observations=["the expected marker appeared"],
        action_succeeded=True,
    )
    engine = make_engine(solver=solver, verifier=FakeVerifier(), observation=observation)
    result = _run(engine.solve(Task(description="fake verifier")))
    assert result.success is True
    assert result.verification_status is VerificationStatus.VERIFIED


def test_research_runs_only_when_provider_configured() -> None:
    engine_with = make_engine(
        include_verifier=False,
        research=FakeResearchProvider(),
    )
    task = Task(description="research when provider")
    result_with = _run(engine_with.solve(task))
    assert result_with.success is True
    session_with = engine_with.get_session(result_with.session_id)
    assert session_with is not None
    assert any(
        event.event_type is ExecutionEventType.RESEARCH
        for event in session_with.events
    )
    assert len(session_with.research_results) >= 1

    engine_without = make_engine(include_verifier=False, research=None)
    result_without = _run(engine_without.solve(Task(description="no research")))
    session_without = engine_without.get_session(result_without.session_id)
    assert session_without is not None
    assert not any(
        event.event_type is ExecutionEventType.RESEARCH
        for event in session_without.events
    )
    assert session_without.research_results == []


def test_no_research_when_no_unresolved_questions() -> None:
    solver = SolverStub(unresolved_questions=[])
    engine = make_engine(
        solver=solver,
        include_verifier=False,
        research=FakeResearchProvider(),
    )
    result = _run(engine.solve(Task(description="no questions")))
    session = engine.get_session(result.session_id)
    assert session is not None
    assert any(
        event.message == "No unresolved questions that require research."
        for event in session.events
    )
    assert session.research_results == []


def test_research_failure_is_recoverable() -> None:
    engine = make_engine(
        research=FakeResearchProvider(
            fail=True, fail_message="research offline"
        ),
    )
    task = Task(description="research down")
    result = _run(engine.solve(task))
    assert result.success is True
    assert result.status is ProblemSolvingStatus.COMPLETED
    session = engine.get_session(result.session_id)
    assert session is not None
    assert any(
        event.event_type is ExecutionEventType.RESEARCH
        and event.success is False
        for event in session.events
    )


# ----------------------------------------------------------------------
# Replanning
# ----------------------------------------------------------------------


def test_critic_block_triggers_replan_then_passes() -> None:
    critic = ScriptedCritic([Severity.HIGH, Severity.MEDIUM])
    verifier = ScriptedVerifier([VerificationStatus.VERIFIED])
    engine = make_engine(
        critic=critic,
        verifier=verifier,
        include_predictor=False,
    )
    result = _run(engine.solve(Task(description="critic replan")))
    assert result.success is True
    assert result.iterations_used == 2
    session = engine.get_session(result.session_id)
    assert session is not None
    assert len(session.attempts) == 2
    assert len(critic.requests) == 2
    assert any(
        event.event_type is ExecutionEventType.REPLAN for event in result.events
    )


def test_action_failure_triggers_replan_then_passes() -> None:
    action = ScriptedActionExecutor([False, True])
    verifier = ScriptedVerifier([VerificationStatus.VERIFIED])
    engine = make_engine(
        action=action,
        verifier=verifier,
        include_predictor=False,
        include_critic=False,
    )
    result = _run(engine.solve(Task(description="action replan")))
    assert result.success is True
    assert result.iterations_used == 2
    assert len(action.requests) == 2
    session = engine.get_session(result.session_id)
    assert session is not None
    assert session.attempts[0].action_success is False
    assert session.attempts[1].action_success is True


def test_agent_step_failure_triggers_replan_then_passes() -> None:
    agent = ScriptedAgent([False, True])
    verifier = ScriptedVerifier([VerificationStatus.VERIFIED])
    engine = make_engine(
        agents=[agent],
        verifier=verifier,
        include_predictor=False,
        include_critic=False,
    )
    result = _run(engine.solve(Task(description="agent replan")))
    assert result.success is True
    assert result.iterations_used == 2
    session = engine.get_session(result.session_id)
    assert session is not None
    assert session.attempts[0].steps_failed == 1
    assert session.attempts[1].steps_succeeded == 1


def test_verification_failure_triggers_replan_then_passes() -> None:
    verifier = ScriptedVerifier(
        [VerificationStatus.FAILED, VerificationStatus.VERIFIED]
    )
    engine = make_engine(
        verifier=verifier,
        include_predictor=False,
        include_critic=False,
    )
    result = _run(engine.solve(Task(description="verify replan")))
    assert result.success is True
    assert result.iterations_used == 2
    session = engine.get_session(result.session_id)
    assert session is not None
    assert len(session.attempts) == 2
    assert session.attempts[0].verification_status == "failed"
    assert any(
        event.event_type is ExecutionEventType.REPLAN for event in result.events
    )


def test_inconclusive_defaults_to_replan() -> None:
    verifier = ScriptedVerifier(
        [VerificationStatus.INCONCLUSIVE, VerificationStatus.VERIFIED]
    )
    engine = make_engine(
        verifier=verifier,
        include_predictor=False,
        include_critic=False,
    )
    result = _run(engine.solve(Task(description="inconclusive replan")))
    assert result.success is True
    assert result.iterations_used == 2
    session = engine.get_session(result.session_id)
    assert session is not None
    assert session.attempts[0].verification_status == "inconclusive"


def test_inconclusive_fail_is_configured() -> None:
    verifier = ScriptedVerifier([VerificationStatus.INCONCLUSIVE])
    engine = make_engine(
        verifier=verifier,
        on_inconclusive="fail",
        include_predictor=False,
        include_critic=False,
    )
    result = _run(engine.solve(Task(description="inconclusive stops")))
    assert result.success is False
    assert result.status is ProblemSolvingStatus.FAILED
    assert "inconclusive" in (result.failure_reason or "")
    session = engine.get_session(result.session_id)
    assert session is not None
    assert session.status is ProblemSolvingStatus.FAILED


def test_max_iterations_exhausted_fails() -> None:
    verifier = ScriptedVerifier(
        [VerificationStatus.FAILED, VerificationStatus.FAILED]
    )
    engine = make_engine(
        verifier=verifier,
        max_iterations=2,
        include_predictor=False,
        include_critic=False,
    )
    result = _run(engine.solve(Task(description="max out")))
    assert result.success is False
    assert result.status is ProblemSolvingStatus.FAILED
    assert "attempt 2 of 2" in (result.failure_reason or "")
    assert result.iterations_used == 2
    session = engine.get_session(result.session_id)
    assert session is not None
    assert session.current_iteration == 2
    assert len(session.attempts) == 2


def test_loop_never_exceeds_max_iterations() -> None:
    verifier = ScriptedVerifier(
        [VerificationStatus.FAILED] * 10
    )
    engine = make_engine(
        verifier=verifier,
        max_iterations=3,
        include_predictor=False,
        include_critic=False,
    )
    result = _run(engine.solve(Task(description="bounded")))
    assert result.status is ProblemSolvingStatus.FAILED
    assert result.iterations_used == 3
    session = engine.get_session(result.session_id)
    assert session is not None
    assert session.current_iteration == 3


# ----------------------------------------------------------------------
# Error isolation
# ----------------------------------------------------------------------


def test_problem_solver_error_is_isolated() -> None:
    solver = SolverStub(raise_error=RuntimeError("boom"))
    engine = make_engine(solver=solver)
    result = _run(engine.solve(Task(description="solver boom")))
    assert result.success is False
    assert result.status is ProblemSolvingStatus.FAILED
    assert "Problem understanding failed" in (result.failure_reason or "")
    assert "Traceback" not in (result.failure_reason or "")
    session = engine.get_session(result.session_id)
    assert session is not None
    assert any(
        "RuntimeError" in event.message and event.success is False
        for event in session.events
    )


def test_planner_error_is_isolated() -> None:
    engine = make_engine(planner=FailingPlanner())
    result = _run(engine.solve(Task(description="planner boom")))
    assert result.success is False
    assert "Planning failed" in (result.failure_reason or "")
    assert "Traceback" not in (result.failure_reason or "")


def test_action_executor_raise_replans_then_passes() -> None:
    action = RaiseOnceActionExecutor()
    verifier = ScriptedVerifier([VerificationStatus.VERIFIED])
    engine = make_engine(
        action=action,
        verifier=verifier,
        include_predictor=False,
        include_critic=False,
    )
    result = _run(engine.solve(Task(description="raise once")))
    assert result.success is True
    assert result.iterations_used == 2
    assert action.calls == 2
    assert "Traceback" not in " ".join(
        event.message for event in result.events
    )


def test_persistent_action_error_fails_cleanly() -> None:
    engine = make_engine(
        action=AlwaysRaiseActionExecutor(),
        max_iterations=2,
        include_verifier=False,
        include_predictor=False,
        include_critic=False,
    )
    result = _run(engine.solve(Task(description="always raise")))
    assert result.success is False
    assert result.status is ProblemSolvingStatus.FAILED
    assert "Traceback" not in (result.failure_reason or "")
    assert "Traceback" not in " ".join(
        event.message for event in result.events
    )
    session = engine.get_session(result.session_id)
    assert session is not None
    assert session.attempts[0].action_success is False


def test_verifier_error_returns_controlled_result() -> None:
    verifier = FakeVerifier(raise_error=RuntimeError("verify boom"))
    engine = make_engine(
        verifier=verifier,
        max_iterations=1,
        include_predictor=False,
        include_critic=False,
    )
    result = _run(engine.solve(Task(description="verify boom")))
    assert result.success is False
    assert result.status is ProblemSolvingStatus.FAILED
    session = engine.get_session(result.session_id)
    assert session is not None
    assert any(
        event.event_type is ExecutionEventType.VERIFICATION
        and event.success is False
        for event in session.events
    )


# ----------------------------------------------------------------------
# Replan context passed to planner
# ----------------------------------------------------------------------


def test_planner_receives_iteration_and_prior_attempt_context() -> None:
    planner = RecordingPlanner(["step one"])
    verifier = ScriptedVerifier(
        [VerificationStatus.FAILED, VerificationStatus.VERIFIED]
    )
    engine = make_engine(
        planner=planner,
        verifier=verifier,
        include_predictor=False,
        include_critic=False,
    )
    task = Task(
        description="context handoff",
        context={"user": "kept"},
    )
    result = _run(engine.solve(task))
    assert result.success is True
    assert result.iterations_used == 2
    assert len(planner.calls) == 2
    first, second = planner.calls
    assert first.task_id == task.task_id
    assert second.task_id == task.task_id
    assert first.context["iteration"] == 1
    assert second.context["iteration"] == 2
    assert first.context["user"] == "kept"
    assert second.context["user"] == "kept"
    assert first.context["prior_attempts"] == []
    assert len(second.context["prior_attempts"]) == 1
    prior = second.context["prior_attempts"][0]
    assert prior["attempt_number"] == 1
    assert prior["verification_status"] == "failed"


# ----------------------------------------------------------------------
# Memory
# ----------------------------------------------------------------------


def test_memory_summary_stored_on_success_without_raw_description() -> None:
    memory = RecordingMemory()
    engine = make_engine(memory=memory)
    task = Task(description="super secret experiment description")
    result = _run(engine.solve(task))
    assert result.success is True
    assert len(memory.records) == 1
    record = memory.records[0]
    assert "super secret" not in record.content
    assert record.metadata["status"] == "completed"
    assert record.metadata["session_id"] == str(result.session_id)
    assert record.metadata["task_id"] == str(task.task_id)


def test_memory_store_failure_does_not_break_run() -> None:
    memory = RecordingMemory(fail=True)
    engine = make_engine(memory=memory)
    result = _run(engine.solve(Task(description="memory down")))
    assert result.success is True
    assert result.status is ProblemSolvingStatus.COMPLETED


def test_no_memory_means_no_storage_attempt() -> None:
    engine = make_engine(memory=None, include_verifier=False)
    result = _run(engine.solve(Task(description="no memory")))
    assert result.success is True


# ----------------------------------------------------------------------
# Cancellation and timeout
# ----------------------------------------------------------------------


def test_cooperative_cancellation_returns_controlled_result() -> None:
    planner = RecordingPlanner([f"step {i}" for i in range(8)])
    engine = make_engine(
        planner=planner,
        agents=[SlowAgent()],
        include_verifier=False,
        include_predictor=False,
        include_critic=False,
    )
    task = Task(description="cancel mid-run")
    session = engine.create_session(task)

    async def _cancel_after_sleep() -> None:
        await asyncio.sleep(0.1)
        engine.cancel(session.session_id)

    async def _solve_and_cancel():
        solve_task = asyncio.create_task(engine.solve(task, session=session))
        cancel_task = asyncio.create_task(_cancel_after_sleep())
        result = await solve_task
        await cancel_task
        return result

    result = asyncio.run(_solve_and_cancel())
    assert result.success is False
    assert result.status is ProblemSolvingStatus.CANCELLED
    assert result.failure_reason == "Problem-solving was cancelled."
    assert session.cancelled is True
    assert session.status is ProblemSolvingStatus.CANCELLED


def test_timeout_returns_controlled_result() -> None:
    engine = make_engine(
        action=SlowActionExecutor(),
        timeout_seconds=0.1,
        include_verifier=False,
        include_predictor=False,
        include_critic=False,
    )
    result = _run(engine.solve(Task(description="timeout")))
    assert result.success is False
    assert result.status is ProblemSolvingStatus.TIMED_OUT
    assert "timeout" in (result.failure_reason or "").lower()
    session = engine.get_session(result.session_id)
    assert session is not None
    assert session.status is ProblemSolvingStatus.TIMED_OUT


# ----------------------------------------------------------------------
# Concurrency / traces
# ----------------------------------------------------------------------


def test_concurrent_sessions_tracked_independently() -> None:
    engine = make_engine()
    task_a = Task(description="task A")
    task_b = Task(description="task B")

    async def _solve_both():
        first, second = await asyncio.gather(
            engine.solve(task_a), engine.solve(task_b)
        )
        return first, second

    first, second = asyncio.run(_solve_both())
    assert first.success is True
    assert second.success is True
    assert first.session_id != second.session_id
    sessions = engine.sessions()
    assert len(sessions) == 2
    session_a = engine.get_session(first.session_id)
    session_b = engine.get_session(second.session_id)
    assert session_a is not None
    assert session_b is not None
    assert session_a.status is ProblemSolvingStatus.COMPLETED
    assert session_b.status is ProblemSolvingStatus.COMPLETED


def test_events_carry_only_observable_statuses() -> None:
    engine = make_engine()
    result = _run(engine.solve(Task(description="trace only")))
    joined = "; ".join(event.message for event in result.events)
    for forbidden in ("I think", "chain-of-thought", "```", "secret"):
        assert forbidden not in joined.lower()
    for event in result.events:
        assert event.message == event.message.strip()
    assert result.final_output is not None
    assert "Traceback" not in result.final_output


# ----------------------------------------------------------------------
# FAILURES — each dependency failure isolation
# ----------------------------------------------------------------------


def test_predictor_error_is_isolated_as_notice() -> None:
    predictor = FakePredictor(raise_error=RuntimeError("predictor boom"))
    engine = make_engine(
        predictor=predictor,
        include_verifier=False,
        include_critic=False,
    )
    result = _run(engine.solve(Task(description="predictor down")))
    assert result.success is True
    assert result.status is ProblemSolvingStatus.COMPLETED
    assert "Traceback" not in " ".join(
        event.message for event in result.events
    )
    prediction_events = [
        e for e in result.events
        if e.event_type is ExecutionEventType.PREDICTION
    ]
    assert len(prediction_events) == 1
    assert prediction_events[0].success is False
    assert "skipped" in prediction_events[0].message.lower()


def test_critic_error_is_skipped_not_blocking() -> None:
    critic = FakeCritic(raise_error=RuntimeError("critic boom"))
    verifier = ScriptedVerifier([VerificationStatus.VERIFIED])
    engine = make_engine(
        critic=critic,
        verifier=verifier,
        include_predictor=False,
    )
    result = _run(engine.solve(Task(description="critic down")))
    assert result.success is True
    assert result.status is ProblemSolvingStatus.COMPLETED
    assert "Traceback" not in " ".join(
        event.message for event in result.events
    )
    critique_events = [
        e for e in result.events
        if e.event_type is ExecutionEventType.CRITIQUE
    ]
    assert len(critique_events) == 1
    assert critique_events[0].success is False
    assert "skipped" in critique_events[0].message.lower()


def test_observation_failure_triggers_replan_then_passes() -> None:

    class _ScriptedObsProvider(ObservationProvider):
        name = "scripted-obs-provider"
        description = "Fails first, then succeeds."

        def __init__(self) -> None:
            self._outcomes = [False, True]
            self.requests: list[ObservationRequest] = []

        async def observe(self, request: ObservationRequest) -> ObservationResult:
            self.requests.append(request)
            ok = self._outcomes.pop(0) if self._outcomes else True
            if ok:
                return ObservationResult.ok(
                    request.observation_id,
                    observations=["expected sign observed"],
                    action_succeeded=True,
                )
            return ObservationResult.fail(
                request.observation_id, error="simulated observation failure"
            )

    obs = _ScriptedObsProvider()
    verifier = ScriptedVerifier([VerificationStatus.VERIFIED])
    engine = make_engine(
        observation=obs,
        verifier=verifier,
        include_predictor=False,
        include_critic=False,
    )
    result = _run(engine.solve(Task(description="obs replan")))
    assert result.success is True
    assert result.iterations_used == 2
    assert len(obs.requests) == 2
    session = engine.get_session(result.session_id)
    assert session is not None
    assert session.attempts[0].action_success is True
    assert any(
        e.event_type is ExecutionEventType.REPLAN for e in result.events
    )


def test_routing_failure_triggers_replan_then_passes() -> None:

    class _CapabilityPlanPlanner(Planner):
        name = "capability-plan-planner"
        description = "Produces steps with scripted required capabilities."

        def __init__(self, capability_sets: list[frozenset[str]]) -> None:
            self._capability_sets = list(capability_sets)
            self.calls: list[Task] = []

        async def plan(self, task: Task) -> Plan:
            self.calls.append(task)
            cap = (
                self._capability_sets.pop(0)
                if self._capability_sets
                else frozenset()
            )
            steps = [
                PlanStep(
                    description="step",
                    required_capabilities=cap,
                )
            ]
            return Plan(
                task_id=task.task_id,
                goal=task.description,
                steps=steps,
            )

    planner = _CapabilityPlanPlanner(
        [frozenset({"nonexistent-cap"}), frozenset()]
    )
    verifier = ScriptedVerifier([VerificationStatus.VERIFIED])
    engine = make_engine(
        planner=planner,
        verifier=verifier,
        include_predictor=False,
        include_critic=False,
    )
    result = _run(engine.solve(Task(description="routing replan")))
    assert result.success is True
    assert result.iterations_used == 2
    delegation_events = [
        e for e in result.events
        if e.event_type is ExecutionEventType.DELEGATION
    ]
    assert any(
        e.success is False for e in delegation_events
    )
    assert any(
        e.success is True for e in delegation_events
    )
    assert "Traceback" not in " ".join(
        event.message for event in result.events
    )


# ----------------------------------------------------------------------
# SAFETY — inconclusive never becomes success
# ----------------------------------------------------------------------


def test_inconclusive_verification_never_becomes_success() -> None:
    verifier = ScriptedVerifier(
        [VerificationStatus.INCONCLUSIVE, VerificationStatus.INCONCLUSIVE]
    )
    engine = make_engine(
        verifier=verifier,
        max_iterations=2,
        include_predictor=False,
        include_critic=False,
    )
    result = _run(engine.solve(Task(description="inconclusive never ok")))
    assert result.success is False
    assert result.status is ProblemSolvingStatus.FAILED
    assert result.iterations_used == 2
    assert "Traceback" not in " ".join(
        event.message for event in result.events
    )
