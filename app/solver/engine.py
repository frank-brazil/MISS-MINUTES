"""Bounded, controlled autonomous problem-solving loop.

The engine coordinates the existing problem-solving abstractions
(``ProblemSolver``, research, ``Planner``, ``AgentRouter``, ``Predictor``,
``Critic``, ``Verifier``, memory) into a single loop with a strict, session-
level iteration budget.

Guarantees:

- **Bounded**: never more than ``max_iterations`` attempts; the main loop is
  iterative, never recursive.
- **No unrestricted control**: actions and observations go through injectable
  providers that default to deterministic fakes.
- **Controlled failures**: every stage is error-isolated and returned as a
  structured result; no stack traces leak to the user.
- **Trace only**: sessions/events hold concise observable statuses, never
  chain-of-thought or private reasoning.

Replanning is triggered by an unacceptable critic review, an action failure,
an agent/step failure, verification failure, or a configured inconclusive
verification.  Prior attempts are preserved on the session and passed back to
the planner as ``task.context``.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from app.agents.base import Agent, AgentResult
from app.core.critic import Critic, Critique, CritiqueRequest, Severity
from app.core.planner import Plan, Planner
from app.core.prediction import DecisionAnalysis, PredictionRequest, Predictor
from app.core.problem_solver import Problem, ProblemAnalysis, ProblemSolver
from app.core.routing import (
    AgentRouter,
    NoMatchingAgentError,
    UnknownCapabilityError,
)
from app.core.task import Task
from app.core.verification import (
    ObservedResult,
    VerificationExpectation,
    VerificationResult,
    VerificationStatus,
    Verifier,
)
from app.memory.base import Memory, MemoryRecord
from app.research.base import ResearchProvider, SearchRequest
from app.security.manager import SecurityManager, as_security_manager
from app.security.models import Permission, PermissionCategory, SecurityContext
from app.security.policy import SecurityPolicy
from app.solver.actions import ActionExecutor, ActionRequest, ActionResult
from app.solver.events import ExecutionEvent, ExecutionEventType
from app.solver.fakes import FakeActionExecutor, FakeObservationProvider
from app.solver.observation import (
    ObservationProvider,
    ObservationRequest,
    ObservationResult,
)
from app.solver.result import ProblemSolvingResult
from app.solver.session import (
    DEFAULT_MAX_ITERATIONS,
    AttemptSummary,
    ProblemSolvingSession,
    ProblemSolvingStatus,
)

_SEVERITY_RANK: dict[Severity, int] = {
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
    Severity.UNKNOWN: 5,
}

_ON_INCONCLUSIVE = ("replan", "fail")


def _short(value: str, limit: int = 80) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."


def _severity_blocks(severity: Severity, threshold: Severity) -> bool:
    return _SEVERITY_RANK[severity] >= _SEVERITY_RANK[threshold]


class ProblemSolvingEngine:
    """Coordinates one or more bounded problem-solving sessions."""

    def __init__(
        self,
        *,
        problem_solver: ProblemSolver,
        planner: Planner,
        agent_router: AgentRouter,
        predictor: Predictor | None = None,
        critic: Critic | None = None,
        verifier: Verifier | None = None,
        research_provider: ResearchProvider | None = None,
        action_executor: ActionExecutor | None = None,
        observation_provider: ObservationProvider | None = None,
        memory: Memory | None = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        timeout_seconds: float | None = None,
        critic_severity_threshold: Severity = Severity.HIGH,
        on_inconclusive: Literal["replan", "fail"] = "replan",
        max_research_queries: int = 3,
        security: "SecurityManager | SecurityPolicy | None" = None,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be positive when provided"
            )
        if on_inconclusive not in _ON_INCONCLUSIVE:
            raise ValueError(
                f"on_inconclusive must be one of {', '.join(_ON_INCONCLUSIVE)}"
            )
        if max_research_queries < 1:
            raise ValueError("max_research_queries must be at least 1")

        self._logger = logging.getLogger(__name__)
        self._problem_solver = problem_solver
        self._planner = planner
        self._router = agent_router
        self._predictor = predictor
        self._critic = critic
        self._verifier = verifier
        self._research_provider = research_provider
        self._action_executor: ActionExecutor = (
            action_executor if action_executor is not None else FakeActionExecutor()
        )
        self._observation_provider: ObservationProvider = (
            observation_provider
            if observation_provider is not None
            else FakeObservationProvider()
        )
        self._memory = memory
        self._security = as_security_manager(security)
        self._max_iterations = max_iterations
        self._timeout_seconds = timeout_seconds
        self._critic_severity_threshold = critic_severity_threshold
        self._on_inconclusive = on_inconclusive
        self._max_research_queries = max_research_queries

        self._sessions: dict[UUID, ProblemSolvingSession] = {}
        self._cancel_requests: set[UUID] = set()

    # ------------------------------------------------------------------
    # Read-only accessors
    # ------------------------------------------------------------------

    @property
    def problem_solver(self) -> ProblemSolver:
        return self._problem_solver

    @property
    def planner(self) -> Planner:
        return self._planner

    @property
    def agent_router(self) -> AgentRouter:
        return self._router

    @property
    def predictor(self) -> Predictor | None:
        return self._predictor

    @property
    def critic(self) -> Critic | None:
        return self._critic

    @property
    def verifier(self) -> Verifier | None:
        return self._verifier

    @property
    def research_provider(self) -> ResearchProvider | None:
        return self._research_provider

    @property
    def action_executor(self) -> ActionExecutor:
        return self._action_executor

    @property
    def observation_provider(self) -> ObservationProvider:
        return self._observation_provider

    @property
    def memory(self) -> Memory | None:
        return self._memory

    @property
    def security(self) -> SecurityManager | None:
        return self._security

    @property
    def max_iterations(self) -> int:
        return self._max_iterations

    @property
    def timeout_seconds(self) -> float | None:
        return self._timeout_seconds

    def sessions(self) -> tuple[ProblemSolvingSession, ...]:
        return tuple(self._sessions.values())

    def get_session(self, session_id: UUID) -> ProblemSolvingSession | None:
        return self._sessions.get(session_id)

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def create_session(self, task: Task) -> ProblemSolvingSession:
        session = ProblemSolvingSession(
            task_id=task.task_id,
            max_iterations=self._max_iterations,
        )
        self._sessions[session.session_id] = session
        self._logger.info(
            "Created problem-solving session %s for task %s "
            "(max iterations %d)",
            session.session_id,
            task.task_id,
            self._max_iterations,
        )
        return session

    def cancel(self, session_id: UUID) -> bool:
        """Request a safe stop for a running session.

        Cancellation is cooperative: the session stops at its next safe point
        and returns a controlled ``CANCELLED`` result.
        """
        if session_id not in self._sessions:
            return False
        if session_id in self._cancel_requests:
            return False
        self._cancel_requests.add(session_id)
        self._logger.info("Cancellation requested for session %s", session_id)
        return True

    def _is_cancelled(self, session_id: UUID) -> bool:
        return session_id in self._cancel_requests

    # ------------------------------------------------------------------
    # Solve
    # ------------------------------------------------------------------

    async def solve(
        self,
        task: Task,
        *,
        session: ProblemSolvingSession | None = None,
    ) -> ProblemSolvingResult:
        if session is None:
            session = self.create_session(task)
        else:
            self._sessions[session.session_id] = session
        session.change_status(ProblemSolvingStatus.PENDING)

        if self._timeout_seconds is None:
            return await self._run_session(session, task)

        try:
            return await asyncio.wait_for(
                self._run_session(session, task),
                timeout=self._timeout_seconds,
            )
        except (TimeoutError, asyncio.TimeoutError):
            return self._finish_timed_out(session)
        except asyncio.CancelledError:
            self._finish_cancelled(session)
            raise

    # ------------------------------------------------------------------
    # Main bounded loop
    # ------------------------------------------------------------------

    async def _run_session(
        self,
        session: ProblemSolvingSession,
        task: Task,
    ) -> ProblemSolvingResult:
        analysis: ProblemAnalysis | None = None

        while session.current_iteration <= session.max_iterations:
            iteration = session.current_iteration

            if self._is_cancelled(session.session_id):
                return self._finish_cancelled(session)

            attempt = AttemptSummary(attempt_number=iteration)

            # 1) Understanding (once per session; reused when replanning)
            if analysis is None:
                analysis = await self._phase_understanding(session, task)
                if analysis is None:
                    return await self._fail(
                        session,
                        f"Problem understanding failed on attempt {iteration}.",
                    )
                if self._is_cancelled(session.session_id):
                    return self._finish_cancelled(session)

            # 2) Research (only when provider exists and questions remain)
            if iteration == 1 and self._research_provider is not None:
                await self._phase_research(session, analysis)
                if self._is_cancelled(session.session_id):
                    return self._finish_cancelled(session)

            # 3) Planning
            session.change_status(ProblemSolvingStatus.PLANNING)
            plan = await self._phase_planning(session, task, iteration)
            if plan is None:
                return await self._fail(
                    session, f"Planning failed on attempt {iteration}."
                )
            session.plan = plan
            if self._is_cancelled(session.session_id):
                return self._finish_cancelled(session)

            # 4) Delegating plan steps to agents
            session.change_status(ProblemSolvingStatus.DELEGATING)
            completed_steps, delegated = await self._phase_delegating(
                session, plan, attempt
            )
            if delegated:
                session.attempts.append(attempt)
                result = await self._replan_or_fail(
                    session,
                    f"Delegation failed on attempt {iteration}: "
                    f"{attempt.outcome or 'unknown error'}",
                )
                if result is not None:
                    return result
                continue
            if self._is_cancelled(session.session_id):
                return self._finish_cancelled(session)

            # 5) Predicting (optional heuristic; failures are notices only)
            session.change_status(ProblemSolvingStatus.PREDICTING)
            if self._predictor is not None:
                await self._phase_predicting(session, plan, analysis, iteration)
                if self._is_cancelled(session.session_id):
                    return self._finish_cancelled(session)

            # 6) Critiquing (optional approve gate before acting)
            session.change_status(ProblemSolvingStatus.CRITIQUING)
            block = False
            if self._critic is not None:
                _, block = await self._phase_critiquing(
                    session, plan, iteration
                )
                if self._is_cancelled(session.session_id):
                    return self._finish_cancelled(session)
            if block:
                attempt.outcome = (
                    "Critique flagged issues above the acceptable threshold."
                )
                session.attempts.append(attempt)
                result = await self._replan_or_fail(
                    session,
                    f"Critique blocked attempt {iteration}: {attempt.outcome}",
                )
                if result is not None:
                    return result
                continue

            # 7) Acting (via the injected executor)
            session.change_status(ProblemSolvingStatus.ACTING)
            action = await self._phase_acting(
                session, plan, analysis, iteration, attempt=attempt
            )
            if action is None or not action.success:
                attempt.action_success = action is not None and action.success
                if attempt.outcome is None:
                    attempt.outcome = f"Action failed on attempt {iteration}."
                session.attempts.append(attempt)
                result = await self._replan_or_fail(session, attempt.outcome)
                if result is not None:
                    return result
                continue
            attempt.action_success = True
            if self._is_cancelled(session.session_id):
                return self._finish_cancelled(session)

            # 8) Observing
            session.change_status(ProblemSolvingStatus.OBSERVING)
            observation = await self._phase_observing(
                session, action, iteration
            )
            if observation is None or not observation.success:
                attempt.outcome = f"Observation failed on attempt {iteration}."
                session.attempts.append(attempt)
                result = await self._replan_or_fail(session, attempt.outcome)
                if result is not None:
                    return result
                continue

            # 9) Verifying
            session.change_status(ProblemSolvingStatus.VERIFYING)
            verification = await self._phase_verifying(
                session, plan, action, observation, iteration
            )

            attempt.verification_status = (
                verification.status.value
                if verification is not None
                else VerificationStatus.NOT_RUN.value
            )
            attempt.outcome = (
                "Verified."
                if verification is not None and verification.is_verified
                else "Unverified or not verified."
            )
            session.attempts.append(attempt)

            if (
                verification is None
                or verification.status is VerificationStatus.NOT_RUN
            ):
                return await self._complete_unverified(
                    session, completed_steps, iteration
                )

            if verification.is_verified:
                return await self._complete(
                    session, verification, completed_steps, iteration
                )

            if (
                verification.status is VerificationStatus.INCONCLUSIVE
                and self._on_inconclusive == "fail"
            ):
                return await self._fail(
                    session,
                    f"Verification inconclusive on attempt {iteration}; "
                    "configured to stop.",
                )

            reason = (
                f"Verification {verification.status.value} on attempt "
                f"{iteration}."
            )
            result = await self._replan_or_fail(session, reason)
            if result is not None:
                return result
            continue

        return await self._fail(
            session,
            f"Maximum iterations ({session.max_iterations}) reached "
            "without a verified result.",
        )

    # ------------------------------------------------------------------
    # Phases
    # ------------------------------------------------------------------

    async def _phase_understanding(
        self,
        session: ProblemSolvingSession,
        task: Task,
    ) -> ProblemAnalysis | None:
        session.change_status(ProblemSolvingStatus.UNDERSTANDING)
        problem = Problem(
            description=task.description, context=dict(task.context)
        )
        self._logger.info(
            "Understanding problem for session %s task %s",
            session.session_id,
            task.task_id,
        )
        session.record_event(
            ExecutionEvent(
                event_type=ExecutionEventType.UNDERSTANDING,
                status=session.status.value,
                message=f"Understanding problem: {_short(task.description)}",
                success=True,
                iteration=session.current_iteration,
            )
        )
        try:
            analysis = await self._problem_solver.solve(problem)
        except Exception as exc:
            self._logger.warning(
                "Problem understanding raised %s for session %s",
                type(exc).__name__,
                session.session_id,
            )
            session.record_event(
                ExecutionEvent(
                    event_type=ExecutionEventType.UNDERSTANDING,
                    status=session.status.value,
                    message=(
                        f"Problem understanding raised {type(exc).__name__} "
                        "and was stopped."
                    ),
                    success=False,
                    iteration=session.current_iteration,
                )
            )
            return None
        session.record_event(
            ExecutionEvent(
                event_type=ExecutionEventType.UNDERSTANDING,
                status=session.status.value,
                message=(
                    f"Problem understood with {len(analysis.hypotheses)} "
                    f"hypothesis(es) and "
                    f"{len(analysis.candidate_solutions)} candidate "
                    "solution(s)."
                ),
                success=True,
                iteration=session.current_iteration,
            )
        )
        return analysis

    async def _phase_research(
        self,
        session: ProblemSolvingSession,
        analysis: ProblemAnalysis,
    ) -> None:
        session.change_status(ProblemSolvingStatus.RESEARCHING)
        provider = self._research_provider  # guaranteed not None by caller
        questions = [
            q.strip()
            for q in analysis.unresolved_questions
            if q.strip()
        ][: self._max_research_queries]

        if not questions:
            session.record_event(
                ExecutionEvent(
                    event_type=ExecutionEventType.RESEARCH,
                    status=session.status.value,
                    message="No unresolved questions that require research.",
                    success=True,
                    iteration=session.current_iteration,
                )
            )
            return

        self._logger.info(
            "Researching %d question(s) for session %s",
            len(questions),
            session.session_id,
        )
        session.record_event(
            ExecutionEvent(
                event_type=ExecutionEventType.RESEARCH,
                status=session.status.value,
                message=(
                    f"Researching {len(questions)} unresolved question(s)."
                ),
                success=True,
                iteration=session.current_iteration,
            )
        )
        for question in questions:
            request = SearchRequest(query=question)
            try:
                response = await provider.research(request)
            except Exception as exc:
                self._logger.warning(
                    "Research raised %s for session %s",
                    type(exc).__name__,
                    session.session_id,
                )
                session.record_event(
                    ExecutionEvent(
                        event_type=ExecutionEventType.RESEARCH,
                        status=session.status.value,
                        message=(
                            f"Research failed for '{_short(question, 40)}': "
                            f"{type(exc).__name__}."
                        ),
                        success=False,
                        iteration=session.current_iteration,
                    )
                )
                continue
            session.research_results.append(response)
            if response.success:
                session.record_event(
                    ExecutionEvent(
                        event_type=ExecutionEventType.RESEARCH,
                        status=session.status.value,
                        message=(
                            f"Research completed with "
                            f"{response.result_count} result(s)."
                        ),
                        success=True,
                        iteration=session.current_iteration,
                    )
                )
            else:
                session.record_event(
                    ExecutionEvent(
                        event_type=ExecutionEventType.RESEARCH,
                        status=session.status.value,
                        message=(
                            f"Research failed for "
                            f"'{_short(question, 40)}': "
                            f"{_short(response.error or 'unknown reason')}."
                        ),
                        success=False,
                        iteration=session.current_iteration,
                    )
                )

    async def _phase_planning(
        self,
        session: ProblemSolvingSession,
        task: Task,
        iteration: int,
    ) -> Plan | None:
        session.change_status(ProblemSolvingStatus.PLANNING)
        plan_task = self._build_plan_task(session, task, iteration)
        self._logger.info(
            "Planning with planner '%s' for session %s",
            self._planner.name,
            session.session_id,
        )
        session.record_event(
            ExecutionEvent(
                event_type=ExecutionEventType.PLAN,
                status=session.status.value,
                message=f"Planning with planner '{self._planner.name}'.",
                success=True,
                iteration=iteration,
            )
        )
        try:
            plan = await self._planner.plan(plan_task)
        except Exception as exc:
            self._logger.warning(
                "Plan creation raised %s for session %s",
                type(exc).__name__,
                session.session_id,
            )
            session.record_event(
                ExecutionEvent(
                    event_type=ExecutionEventType.PLAN,
                    status=session.status.value,
                    message=(
                        f"Plan creation raised {type(exc).__name__} and was "
                        "stopped."
                    ),
                    success=False,
                    iteration=iteration,
                )
            )
            return None
        session.record_event(
            ExecutionEvent(
                event_type=ExecutionEventType.PLAN,
                status=session.status.value,
                message=f"Plan created with {len(plan.steps)} step(s).",
                success=True,
                iteration=iteration,
            )
        )
        return plan

    async def _phase_delegating(
        self,
        session: ProblemSolvingSession,
        plan: Plan,
        attempt: AttemptSummary,
    ) -> tuple[list[str], bool]:
        completed: list[str] = []
        for index, step in enumerate(plan.steps):
            if self._is_cancelled(session.session_id):
                return completed, False
            step_number = index + 1
            try:
                agent: Agent = self._router.select(
                    step.required_capabilities
                )
            except (UnknownCapabilityError, NoMatchingAgentError) as exc:
                session.record_event(
                    ExecutionEvent(
                        event_type=ExecutionEventType.DELEGATION,
                        status=session.status.value,
                        message=(
                            f"Routing step {step_number} failed: "
                            f"{_short(str(exc))}."
                        ),
                        success=False,
                        iteration=session.current_iteration,
                    )
                )
                attempt.steps_failed += 1
                attempt.outcome = (
                    f"Routing failed for step {step_number}."
                )
                return completed, True

            step_task = Task(description=step.description)
            try:
                agent_result: AgentResult = await agent.execute(step_task)
            except Exception as exc:
                self._logger.warning(
                    "Agent '%s' raised %s for session %s",
                    agent.name,
                    type(exc).__name__,
                    session.session_id,
                )
                agent_result = AgentResult.fail(
                    error=(
                        f"Agent '{agent.name}' raised "
                        f"{type(exc).__name__} while executing step "
                        f"{step_number}."
                    )
                )

            session.record_event(
                ExecutionEvent(
                    event_type=ExecutionEventType.DELEGATION,
                    status=session.status.value,
                    message=(
                        f"Executed step {step_number} "
                        f"('{_short(step.description)}') with "
                        f"agent '{agent.name}'."
                    ),
                    success=agent_result.success,
                    agent_name=agent.name,
                    iteration=session.current_iteration,
                )
            )

            if agent_result.success:
                completed.append(step.description)
                attempt.steps_succeeded += 1
            else:
                attempt.steps_failed += 1
                attempt.outcome = (
                    f"Step {step_number} failed: "
                    f"{_short(agent_result.error or 'agent execution failed')}."
                )
                session.record_event(
                    ExecutionEvent(
                        event_type=ExecutionEventType.DELEGATION,
                        status=session.status.value,
                        message=attempt.outcome,
                        success=False,
                        agent_name=agent.name,
                        iteration=session.current_iteration,
                    )
                )
                return completed, True
        return completed, False

    async def _phase_predicting(
        self,
        session: ProblemSolvingSession,
        plan: Plan,
        analysis: ProblemAnalysis,
        iteration: int,
    ) -> DecisionAnalysis | None:
        predictor = self._predictor  # guaranteed not None by caller
        request = PredictionRequest(
            question=(
                "Predicted outcome of executing the plan for the task."
            ),
            situation={
                "task_id": str(session.task_id),
                "plan_id": str(plan.plan_id),
                "iteration": iteration,
            },
            candidate_options=[
                s.description for s in analysis.candidate_solutions
            ],
        )
        try:
            decision = await predictor.predict(request)
        except Exception as exc:
            self._logger.warning(
                "Prediction raised %s for session %s",
                type(exc).__name__,
                session.session_id,
            )
            session.record_event(
                ExecutionEvent(
                    event_type=ExecutionEventType.PREDICTION,
                    status=session.status.value,
                    message=(
                        f"Prediction failed and was skipped: "
                        f"{type(exc).__name__}."
                    ),
                    success=False,
                    iteration=iteration,
                )
            )
            return None
        session.record_event(
            ExecutionEvent(
                event_type=ExecutionEventType.PREDICTION,
                status=session.status.value,
                message=(
                    "Prediction recorded as a heuristic estimate; not a "
                    "guaranteed fact."
                ),
                success=True,
                iteration=iteration,
            )
        )
        return decision

    async def _phase_critiquing(
        self,
        session: ProblemSolvingSession,
        plan: Plan,
        iteration: int,
    ) -> tuple[Critique | None, bool]:
        critic = self._critic  # guaranteed not None by caller
        request = CritiqueRequest(
            target=f"Executed solution for '{_short(plan.goal)}'",
            context={
                "task_id": str(session.task_id),
                "plan_id": str(plan.plan_id),
                "iteration": iteration,
            },
        )
        try:
            critique = await critic.critique(request)
        except Exception as exc:
            self._logger.warning(
                "Critique raised %s for session %s",
                type(exc).__name__,
                session.session_id,
            )
            session.record_event(
                ExecutionEvent(
                    event_type=ExecutionEventType.CRITIQUE,
                    status=session.status.value,
                    message=(
                        f"Critique failed and was skipped: "
                        f"{type(exc).__name__}."
                    ),
                    success=False,
                    iteration=iteration,
                )
            )
            return None, False
        severity = critique.highest_severity
        block = _severity_blocks(
            severity, self._critic_severity_threshold
        )
        session.record_event(
            ExecutionEvent(
                event_type=ExecutionEventType.CRITIQUE,
                status=session.status.value,
                message=(
                    f"Critique recorded "
                    f"(highest severity={severity.value})."
                ),
                success=True,
                iteration=iteration,
            )
        )
        return critique, block

    async def _phase_acting(
        self,
        session: ProblemSolvingSession,
        plan: Plan,
        analysis: ProblemAnalysis | None,
        iteration: int,
        attempt: AttemptSummary | None = None,
    ) -> ActionResult | None:
        solution = analysis.recommended_solution if analysis else None
        description = solution.description if solution else plan.goal
        expected_outcome = (
            solution.expected_outcome if solution else None
        )
        request = ActionRequest(
            description=description,
            expected_outcome=expected_outcome,
            iteration=iteration,
        )
        if self._security is not None:
            if self._block_action_by_security(session, request, attempt):
                return None
        session.record_event(
            ExecutionEvent(
                event_type=ExecutionEventType.ACTION,
                status=session.status.value,
                message=f"Executing action: {_short(description)}.",
                success=True,
                tool_name=self._action_executor.name,
                iteration=iteration,
            )
        )
        try:
            result = await self._action_executor.execute(request)
        except Exception as exc:
            self._logger.warning(
                "Action executor raised %s for session %s",
                type(exc).__name__,
                session.session_id,
            )
            session.record_event(
                ExecutionEvent(
                    event_type=ExecutionEventType.ACTION,
                    status=session.status.value,
                    message=(
                        f"Action raised {type(exc).__name__} and was "
                        "stopped."
                    ),
                    success=False,
                    tool_name=self._action_executor.name,
                    iteration=iteration,
                )
            )
            return None
        result.description = request.description
        result.expected_outcome = request.expected_outcome
        return result

    def _block_action_by_security(
        self,
        session: ProblemSolvingSession,
        request: ActionRequest,
        attempt: AttemptSummary | None,
    ) -> bool:
        """Apply the configured security policy to an action request.

        Returns True when the action must not be executed (denied by policy,
        or gated behind an explicit confirmation that an autonomous loop
        cannot grant).  Records a structured trace event and marks the
        attempt outcome so the loop and result trace reflect the reason.
        """
        security = self._security  # guaranteed not None by caller
        permission = Permission(category=PermissionCategory.EXECUTE)
        description = _short(request.description, 120)
        security_request = security.create_request(
            permission=permission,
            action=f"action:{description}",
            session_id=session.session_id,
            task_id=session.task_id,
            actor=None,
            origin="solver",
        )
        context = SecurityContext(
            actor_id=None,
            session_id=session.session_id,
            task_id=session.task_id,
            origin="solver",
        )
        decision = security.check(security_request, context=context)
        if decision.allowed:
            return False
        if decision.requires_confirmation:
            if attempt is not None:
                attempt.outcome = (
                    "Action requires confirmation and was not auto-executed."
                )
            session.record_event(
                ExecutionEvent(
                    event_type=ExecutionEventType.ACTION,
                    status=session.status.value,
                    message=(
                        f"Action '{description}' requires confirmation "
                        "(confirmation %s); not auto-executed."
                        % decision.confirmation_id
                    ),
                    success=False,
                    tool_name=self._action_executor.name,
                    iteration=request.iteration,
                )
            )
            self._logger.info(
                "Action requires confirmation: session=%s confirmation=%s",
                session.session_id,
                decision.confirmation_id,
            )
            return True
        if attempt is not None:
            attempt.outcome = "Action denied by security policy."
        session.record_event(
            ExecutionEvent(
                event_type=ExecutionEventType.ACTION,
                status=session.status.value,
                message=(
                    f"Action '{description}' denied by security policy "
                    f"({decision.reason_code or 'denied'})."
                ),
                success=False,
                tool_name=self._action_executor.name,
                iteration=request.iteration,
            )
        )
        self._logger.info(
            "Action denied by security policy: session=%s reason=%s",
            session.session_id,
            decision.reason,
        )
        return True

    async def _phase_observing(
        self,
        session: ProblemSolvingSession,
        action: ActionResult,
        iteration: int,
    ) -> ObservationResult | None:
        request = ObservationRequest(
            description=(
                f"Observe outcome of: {_short(action.description)}"
            ),
            action_ref=action.action_id,
            expected_outcome=action.expected_outcome,
        )
        session.record_event(
            ExecutionEvent(
                event_type=ExecutionEventType.OBSERVATION,
                status=session.status.value,
                message="Recording observation for the executed action.",
                success=True,
                iteration=iteration,
            )
        )
        try:
            return await self._observation_provider.observe(request)
        except Exception as exc:
            self._logger.warning(
                "Observation provider raised %s for session %s",
                type(exc).__name__,
                session.session_id,
            )
            session.record_event(
                ExecutionEvent(
                    event_type=ExecutionEventType.OBSERVATION,
                    status=session.status.value,
                    message=(
                        f"Observation raised {type(exc).__name__} and was "
                        "stopped."
                    ),
                    success=False,
                    iteration=iteration,
                )
            )
            return None

    async def _phase_verifying(
        self,
        session: ProblemSolvingSession,
        plan: Plan,
        action: ActionResult,
        observation: ObservationResult,
        iteration: int,
    ) -> VerificationResult | None:
        if self._verifier is None:
            session.record_event(
                ExecutionEvent(
                    event_type=ExecutionEventType.VERIFICATION,
                    status=session.status.value,
                    message="Verification not configured.",
                    success=None,
                    iteration=iteration,
                )
            )
            return None

        expectation = VerificationExpectation(
            description=(
                f"Executed solution for '{_short(plan.goal)}' should "
                "meet its expected outcome."
            ),
            conditions=[]
            if action.expected_outcome is None
            else [action.expected_outcome],
            action_ref=action.action_id,
        )
        observed = ObservedResult(
            description=(
                f"Observed outcome of: {_short(action.description)}"
            ),
            observations=list(observation.observations),
            action_succeeded=observation.action_succeeded,
        )
        session.record_event(
            ExecutionEvent(
                event_type=ExecutionEventType.VERIFICATION,
                status=session.status.value,
                message=(
                    "Verifying the executed solution against observations."
                ),
                success=True,
                iteration=iteration,
            )
        )
        try:
            return await self._verifier.verify(expectation, observed)
        except Exception as exc:
            self._logger.warning(
                "Verification raised %s for session %s",
                type(exc).__name__,
                session.session_id,
            )
            session.record_event(
                ExecutionEvent(
                    event_type=ExecutionEventType.VERIFICATION,
                    status=session.status.value,
                    message=(
                        f"Verification raised {type(exc).__name__} and "
                        "was stopped."
                    ),
                    success=False,
                    iteration=iteration,
                )
            )
            return VerificationResult(
                status=VerificationStatus.FAILED,
                expectation=expectation,
                observed_outcome=(
                    "; ".join(observation.observations) or None
                ),
                discrepancy=(
                    f"Verification raised {type(exc).__name__}."
                ),
                error=f"Verification raised {type(exc).__name__}.",
                confidence=None,
            )

    # ------------------------------------------------------------------
    # Replan / terminal helpers
    # ------------------------------------------------------------------

    def _build_plan_task(
        self,
        session: ProblemSolvingSession,
        task: Task,
        iteration: int,
    ) -> Task:
        context: dict[str, Any] = dict(task.context)
        context["iteration"] = iteration
        context["prior_attempts"] = [
            {
                "attempt_number": s.attempt_number,
                "steps_succeeded": s.steps_succeeded,
                "steps_failed": s.steps_failed,
                "action_success": s.action_success,
                "verification_status": s.verification_status,
                "outcome": s.outcome,
            }
            for s in session.attempts
        ]
        return Task(
            task_id=task.task_id,
            description=task.description,
            image=task.image,
            context=context,
        )

    async def _replan_or_fail(
        self,
        session: ProblemSolvingSession,
        reason: str,
    ) -> ProblemSolvingResult | None:
        if session.current_iteration >= session.max_iterations:
            return await self._fail(
                session,
                f"{_short(reason, 120)} "
                f"(attempt {session.current_iteration} of "
                f"{session.max_iterations}).",
            )
        session.change_status(ProblemSolvingStatus.REPLANNING)
        session.current_iteration += 1
        next_attempt = session.current_iteration
        session.record_event(
            ExecutionEvent(
                event_type=ExecutionEventType.REPLAN,
                status=session.status.value,
                message=(
                    f"Replanning attempt {next_attempt} of "
                    f"{session.max_iterations}."
                ),
                success=True,
                iteration=next_attempt,
            )
        )
        self._logger.info(
            "Replanning session %s to attempt %d of %d",
            session.session_id,
            next_attempt,
            session.max_iterations,
        )
        return None

    async def _fail(
        self,
        session: ProblemSolvingSession,
        reason: str,
    ) -> ProblemSolvingResult:
        session.change_status(ProblemSolvingStatus.FAILED)
        session.failure_reason = _short(reason, 200)
        session.final_result = None
        session.record_event(
            ExecutionEvent(
                event_type=ExecutionEventType.FAILED,
                status=session.status.value,
                message=f"Problem-solving failed: {_short(reason, 120)}",
                success=False,
                iteration=session.current_iteration,
            )
        )
        self._logger.info(
            "Session %s failed after %d iteration(s): %s",
            session.session_id,
            session.current_iteration,
            session.failure_reason,
        )
        await self._store_memory_summary(session)
        return ProblemSolvingResult(
            success=False,
            status=session.status,
            session_id=session.session_id,
            task_id=session.task_id,
            iterations_used=session.current_iteration,
            final_output=None,
            verification_status=None,
            failure_reason=session.failure_reason,
            completed_steps=[],
            events=session.events,
        )

    async def _complete(
        self,
        session: ProblemSolvingSession,
        verification: VerificationResult,
        completed_steps: list[str],
        iteration: int,
    ) -> ProblemSolvingResult:
        session.change_status(ProblemSolvingStatus.COMPLETED)
        session.final_result = (
            f"Problem-solving completed after {iteration} iteration(s) "
            "with a verified result."
        )
        session.record_event(
            ExecutionEvent(
                event_type=ExecutionEventType.COMPLETED,
                status=session.status.value,
                message=(
                    f"Problem-solving completed successfully in "
                    f"{iteration} iteration(s)."
                ),
                success=True,
                iteration=iteration,
            )
        )
        self._logger.info(
            "Session %s completed after %d iteration(s)",
            session.session_id,
            iteration,
        )
        await self._store_memory_summary(session)
        return ProblemSolvingResult(
            success=True,
            status=session.status,
            session_id=session.session_id,
            task_id=session.task_id,
            iterations_used=iteration,
            final_output=session.final_result,
            verification_status=verification.status,
            failure_reason=None,
            completed_steps=completed_steps,
            events=session.events,
        )

    async def _complete_unverified(
        self,
        session: ProblemSolvingSession,
        completed_steps: list[str],
        iteration: int,
    ) -> ProblemSolvingResult:
        session.change_status(ProblemSolvingStatus.COMPLETED)
        session.final_result = (
            f"Problem-solving completed after {iteration} iteration(s); "
            "result recorded as not_run (verification was not configured)."
        )
        session.record_event(
            ExecutionEvent(
                event_type=ExecutionEventType.NOTICE,
                status=session.status.value,
                message=(
                    "No verifier configured; result recorded as not_run."
                ),
                success=True,
                iteration=iteration,
            )
        )
        session.record_event(
            ExecutionEvent(
                event_type=ExecutionEventType.COMPLETED,
                status=session.status.value,
                message=(
                    f"Problem-solving completed after {iteration} "
                    "iteration(s)."
                ),
                success=True,
                iteration=iteration,
            )
        )
        self._logger.info(
            "Session %s completed (unverified) after %d iteration(s)",
            session.session_id,
            iteration,
        )
        await self._store_memory_summary(session)
        return ProblemSolvingResult(
            success=True,
            status=session.status,
            session_id=session.session_id,
            task_id=session.task_id,
            iterations_used=iteration,
            final_output=session.final_result,
            verification_status=VerificationStatus.NOT_RUN,
            failure_reason=None,
            completed_steps=completed_steps,
            events=session.events,
        )

    def _finish_cancelled(
        self,
        session: ProblemSolvingSession,
    ) -> ProblemSolvingResult:
        session.change_status(ProblemSolvingStatus.CANCELLED)
        session.cancelled = True
        session.cancelled_at = datetime.now(UTC)
        session.failure_reason = "Problem-solving was cancelled."
        session.final_result = None
        session.record_event(
            ExecutionEvent(
                event_type=ExecutionEventType.CANCELLED,
                status=session.status.value,
                message="Problem-solving was cancelled.",
                success=False,
                iteration=session.current_iteration,
            )
        )
        return ProblemSolvingResult(
            success=False,
            status=session.status,
            session_id=session.session_id,
            task_id=session.task_id,
            iterations_used=session.current_iteration,
            final_output=None,
            verification_status=None,
            failure_reason=session.failure_reason,
            completed_steps=[],
            events=session.events,
        )

    def _finish_timed_out(
        self,
        session: ProblemSolvingSession,
    ) -> ProblemSolvingResult:
        session.change_status(ProblemSolvingStatus.TIMED_OUT)
        session.failure_reason = (
            "Problem-solving exceeded the configured timeout."
        )
        session.final_result = None
        session.record_event(
            ExecutionEvent(
                event_type=ExecutionEventType.TIMED_OUT,
                status=session.status.value,
                message="Problem-solving timed out.",
                success=False,
                iteration=session.current_iteration,
            )
        )
        return ProblemSolvingResult(
            success=False,
            status=session.status,
            session_id=session.session_id,
            task_id=session.task_id,
            iterations_used=session.current_iteration,
            final_output=None,
            verification_status=None,
            failure_reason=session.failure_reason,
            completed_steps=[],
            events=session.events,
        )

    async def _store_memory_summary(
        self, session: ProblemSolvingSession
    ) -> None:
        if self._memory is None:
            return
        content = (
            f"Problem-solving session {session.session_id} finished with "
            f"status {session.status.value} after "
            f"{session.current_iteration} iteration(s)."
        )
        record = MemoryRecord(
            content=content,
            metadata={
                "session_id": str(session.session_id),
                "task_id": str(session.task_id),
                "status": session.status.value,
                "iterations_used": session.current_iteration,
            },
        )
        try:
            await self._memory.store(record)
        except Exception as exc:
            self._logger.warning(
                "Memory summary store skipped: %s",
                type(exc).__name__,
            )
