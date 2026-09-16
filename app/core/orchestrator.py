"""Orchestration layer that connects tasks, planners, routing and agents.

The orchestrator owns the high-level lifecycle:

1. Receive a ``Task``.
2. When a ``ProblemSolvingEngine`` is configured, run the task through the
   bounded problem-solving loop (opt-in integration point for CHUNK 28).
3. When a ``Planner`` and an ``AgentRouter`` are available, create a plan,
   route each ``PlanStep`` to a matching ``Agent``, execute, collect results,
   and stop on the first failure.
4. Otherwise, fall back to the existing AI-model tool-calling loop or the
   deterministic placeholder path.
5. Return an ``OrchestrationResult`` whose JSON shape is unchanged so that
   the existing /tasks endpoint contract is preserved.

Step-level results are stored on the orchestrator instance (accessible via
``last_plan`` and ``last_step_results``) and are **not** added to
``OrchestrationResult`` in order to keep the /tasks API schema stable.
"""

import asyncio
import logging
from collections.abc import Iterable
from uuid import UUID

from pydantic import BaseModel

from app.agents.base import Agent, AgentResult
from app.core.ai import AIError, AIMessage, AIModel, ToolCall
from app.core.planner import Plan, PlanStep, Planner
from app.core.routing import AgentRouter, AgentSelection, NoMatchingAgentError, UnknownCapabilityError
from app.core.task import Task, TaskStatus
from app.memory.base import Memory
from app.security.manager import SecurityManager, as_security_manager
from app.security.models import (
    PermissionRequest,
    SecurityContext,
    SecurityDecision,
)
from app.security.policy import SecurityPolicy
from app.solver.engine import ProblemSolvingEngine
from app.tools.base import Tool, ToolResult


MAX_TOOL_CALLS = 10


class PlanExecutionError(Exception):
    """Raised when plan-based orchestration fails mid-execution."""


class AgentExecutionResult(BaseModel):
    """Outcome of executing a single agent for one plan step."""

    agent_name: str
    success: bool
    output: str | None = None
    error: str | None = None

    @classmethod
    def ok(
        cls, agent_name: str, output: str | None = None
    ) -> "AgentExecutionResult":
        return cls(agent_name=agent_name, success=True, output=output)

    @classmethod
    def fail(
        cls,
        agent_name: str,
        error: str,
        output: str | None = None,
    ) -> "AgentExecutionResult":
        return cls(
            agent_name=agent_name, success=False, error=error, output=output
        )


class PlanStepResult(BaseModel):
    """Execution result for a single plan step."""

    step_id: UUID
    description: str
    agent_name: str | None = None
    success: bool
    status: TaskStatus
    output: str | None = None
    error: str | None = None
    execution: AgentExecutionResult | None = None

    @classmethod
    def ok(
        cls,
        step_id: UUID,
        description: str,
        agent_name: str | None,
        output: str | None = None,
        execution: AgentExecutionResult | None = None,
    ) -> "PlanStepResult":
        return cls(
            step_id=step_id,
            description=description,
            agent_name=agent_name,
            success=True,
            status=TaskStatus.COMPLETED,
            output=output,
            execution=execution,
        )

    @classmethod
    def fail(
        cls,
        step_id: UUID,
        description: str,
        agent_name: str | None,
        error: str,
        execution: AgentExecutionResult | None = None,
    ) -> "PlanStepResult":
        return cls(
            step_id=step_id,
            description=description,
            agent_name=agent_name,
            success=False,
            status=TaskStatus.FAILED,
            error=error,
            execution=execution,
        )


class OrchestrationResult(BaseModel):
    task_id: UUID
    success: bool
    status: TaskStatus
    output: str | None = None
    error: str | None = None

    @classmethod
    def ok(
        cls, task_id: UUID, status: TaskStatus, output: str | None = None
    ) -> "OrchestrationResult":
        return cls(task_id=task_id, success=True, status=status, output=output)

    @classmethod
    def fail(
        cls, task_id: UUID, status: TaskStatus, error: str
    ) -> "OrchestrationResult":
        return cls(task_id=task_id, success=False, status=status, error=error)


class Orchestrator:
    def __init__(
        self,
        *,
        ai_model: AIModel | None = None,
        memory: Memory | None = None,
        planner: Planner | None = None,
        agent_router: AgentRouter | None = None,
        problem_solving_engine: "ProblemSolvingEngine | None" = None,
        security: "SecurityManager | SecurityPolicy | None" = None,
    ) -> None:
        self._ai_model = ai_model
        self._memory = memory
        self._planner = planner
        self._router = agent_router if agent_router is not None else AgentRouter()
        self._problem_solving_engine = problem_solving_engine
        self._security = as_security_manager(security)
        self._logger = logging.getLogger(__name__)

        self._tools: dict[str, Tool] = {}

        self._last_plan: Plan | None = None
        self._last_step_results: list[PlanStepResult] = []

    # ------------------------------------------------------------------
    # Read-only properties
    # ------------------------------------------------------------------

    @property
    def ai_model(self) -> AIModel | None:
        return self._ai_model

    @property
    def memory(self) -> Memory | None:
        return self._memory

    @property
    def planner(self) -> Planner | None:
        return self._planner

    @property
    def agent_router(self) -> AgentRouter:
        return self._router

    @property
    def problem_solving_engine(self) -> "ProblemSolvingEngine | None":
        return self._problem_solving_engine

    @property
    def security(self) -> SecurityManager | None:
        return self._security

    @property
    def last_plan(self) -> Plan | None:
        return self._last_plan

    @property
    def last_step_results(self) -> tuple[PlanStepResult, ...]:
        return tuple(self._last_step_results)

    # ------------------------------------------------------------------
    # Registration (delegates to the router for agents)
    # ------------------------------------------------------------------

    def register_agent(self, agent: Agent) -> None:
        self._router.register(agent)

    def register_tool(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool
        self._logger.info("Registered tool '%s'", tool.name)

    def agents(self) -> tuple[Agent, ...]:
        return self._router.agents()

    def tools(self) -> tuple[Tool, ...]:
        return tuple(self._tools.values())

    def agent_names(self) -> tuple[str, ...]:
        return self._router.agent_names()

    def tool_names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    async def execute(self, task: Task) -> OrchestrationResult:
        task.change_status(TaskStatus.RUNNING)
        self._logger.info("Orchestrating task %s", task.task_id)
        try:
            output = await self._orchestrate(task)
        except Exception as exc:
            task.change_status(TaskStatus.FAILED)
            self._logger.error("Task %s failed: %s", task.task_id, exc)
            return OrchestrationResult.fail(
                task_id=task.task_id,
                status=task.status,
                error=str(exc) or "orchestration failed",
            )
        task.change_status(TaskStatus.COMPLETED)
        self._logger.info("Task %s completed", task.task_id)
        return OrchestrationResult.ok(
            task_id=task.task_id,
            status=task.status,
            output=output,
        )

    # ------------------------------------------------------------------
    # Internal orchestration dispatch
    # ------------------------------------------------------------------

    async def _orchestrate(self, task: Task) -> str:
        # The bounded problem-solving loop is an opt-in capability: configure
        # an engine to route tasks through it.  All pre-existing paths
        # (planner+agents, AI tool-calling, placeholder) stay untouched.
        if self._problem_solving_engine is not None:
            return await self._orchestrate_problem_solving(task)

        has_planner = self._planner is not None
        has_agents = len(self._router.agents()) > 0

        if has_planner and has_agents:
            return await self._orchestrate_plan(task)

        if self._ai_model is not None:
            return await self._orchestrate_ai(task)

        return await self._orchestrate_placeholder(task)

    async def _orchestrate_problem_solving(self, task: Task) -> str:
        result = await self._problem_solving_engine.solve(task)
        if result.success:
            self._logger.info(
                "Problem-solving engine completed task %s in session %s",
                task.task_id,
                result.session_id,
            )
            return result.final_output or (
                "Problem-solving completed successfully."
            )
        raise PlanExecutionError(
            result.failure_reason or f"Problem-solving {result.status.value}"
        )

    async def _orchestrate_plan(self, task: Task) -> str:
        planner = self._planner  # guaranteed not None by caller
        router = self._router
        step_results: list[PlanStepResult] = []

        self._logger.info(
            "Planning task %s with planner '%s'",
            task.task_id,
            planner.name,
        )

        plan: Plan
        try:
            plan = await planner.plan(task)
        except Exception as exc:
            raise PlanExecutionError(
                f"Planner raised {type(exc).__name__}: {exc}"
            ) from exc

        self._last_plan = plan
        self._last_step_results = []
        self._logger.info(
            "Plan %s created with %d step(s)", plan.plan_id, len(plan.steps)
        )

        for step in plan.steps:
            agent_name: str | None = None
            execution: AgentExecutionResult | None = None

            # --- Route ---
            try:
                agent = router.select(step.required_capabilities)
                agent_name = agent.name
            except (UnknownCapabilityError, NoMatchingAgentError) as exc:
                step_results.append(
                    PlanStepResult.fail(
                        step_id=step.step_id,
                        description=step.description,
                        agent_name=None,
                        error=f"Routing failed: {exc}",
                    )
                )
                self._last_step_results = list(step_results)
                raise PlanExecutionError(
                    f"Step '{step.description[:60]}' — {exc}"
                ) from exc

            # --- Execute ---
            step_task = Task(description=step.description)
            try:
                agent_result: AgentResult = await agent.execute(step_task)
            except Exception as exc:
                agent_result = AgentResult.fail(
                    error=f"Agent '{agent_name}' raised {type(exc).__name__}"
                )

            execution = AgentExecutionResult(
                agent_name=agent_name,
                success=agent_result.success,
                output=agent_result.output,
                error=agent_result.error,
            )

            if not agent_result.success:
                step_result = PlanStepResult.fail(
                    step_id=step.step_id,
                    description=step.description,
                    agent_name=agent_name,
                    error=agent_result.error or "Agent execution failed",
                    execution=execution,
                )
                step_results.append(step_result)
                self._last_step_results = list(step_results)
                raise PlanExecutionError(
                    f"Step '{step.description[:60]}' failed — "
                    f"agent '{agent_name}' returned error: "
                    f"{agent_result.error or 'unknown'}"
                )

            step_results.append(
                PlanStepResult.ok(
                    step_id=step.step_id,
                    description=step.description,
                    agent_name=agent_name,
                    output=agent_result.output,
                    execution=execution,
                )
            )

        self._last_step_results = list(step_results)
        completed = len(step_results)
        return (
            f"Planned task executed successfully "
            f"({completed} step(s), plan {plan.plan_id})"
        )

    async def _orchestrate_ai(self, task: Task) -> str:
        tool_definitions = [
            tool.to_tool_definition() for tool in self._tools.values()
        ]
        messages: list[AIMessage] = [
            AIMessage(role="user", content=task.description)
        ]

        for _ in range(MAX_TOOL_CALLS):
            response = await self._ai_model.chat(
                messages,
                tools=tool_definitions or None,
            )
            if not response.success:
                raise AIError(response.error or "AI model did not return a response")

            if not response.tool_calls:
                return response.content or ""

            messages.append(
                AIMessage(
                    role="assistant",
                    content=response.content or "",
                    tool_calls=response.tool_calls,
                )
            )
            for tool_call in response.tool_calls:
                self._logger.info(
                    "Executing tool call %s: tool='%s'",
                    tool_call.id,
                    tool_call.name,
                )
                tool = self._tools.get(tool_call.name)
                if tool is None:
                    self._logger.warning(
                        "Unknown tool '%s' requested in call %s",
                        tool_call.name,
                        tool_call.id,
                    )
                    tool_result = ToolResult.fail(
                        error=f"Unknown tool: {tool_call.name}"
                    )
                else:
                    tool_result = await self._execute_tool(tool, tool_call)
                messages.append(
                    AIMessage(
                        role="tool",
                        content=tool_result.output
                        if tool_result.success
                        else tool_result.error or "Tool execution failed",
                        tool_call_id=tool_call.id,
                    )
                )

        raise AIError(
            f"Maximum tool-call limit of {MAX_TOOL_CALLS} exceeded"
        )

    async def _orchestrate_placeholder(self, task: Task) -> str:
        await asyncio.sleep(0)
        self._logger.info(
            "Placeholder orchestration for task %s", task.task_id
        )
        return f"Task '{task.description}' orchestrated successfully"

    async def _execute_tool(self, tool: Tool, tool_call: ToolCall) -> ToolResult:
        if self._security is not None:
            blocked = await self._check_tool_security(tool, tool_call)
            if blocked is not None:
                return blocked
        try:
            tool_result = await tool.execute(**tool_call.arguments)
        except Exception as exc:
            self._logger.warning(
                "Tool '%s' call %s raised %s",
                tool.name,
                tool_call.id,
                type(exc).__name__,
            )
            return ToolResult.fail(
                error=f"Tool execution failed: {type(exc).__name__}"
            )
        self._logger.info(
            "Tool call %s finished: tool='%s' success=%s",
            tool_call.id,
            tool.name,
            tool_result.success,
        )
        return tool_result

    async def _check_tool_security(
        self, tool: Tool, tool_call: ToolCall
    ) -> ToolResult | None:
        """Evaluate tool execution against the configured security policy.

        Returns a ``ToolResult`` failure when the call is blocked (policy
        denial or an operator-confirmation gate that cannot be satisfied
        inside an autonomous loop); returns ``None`` when execution may
        proceed.  A tool that does not declare a permission is treated as
        unknown and denied (fail closed).
        """
        permission = self._security.tool_permission(tool)
        action = f"tool:{tool.name}"
        if permission is None:
            self._security.audit_event(
                action=action,
                permission="undeclared",
                risk="unknown",
                decision_value="deny",
                reason_code="undeclared_permission",
                success=False,
                origin="orchestrator",
            )
            self._logger.warning(
                "Tool '%s' has no declared permission; call %s denied",
                tool.name,
                tool_call.id,
            )
            return ToolResult.fail(
                error=(
                    f"Tool '{tool.name}' has no declared permission and was "
                    "denied by the security policy"
                )
            )
        request = self._security.create_request(
            permission=permission,
            action=action,
            actor=None,
            origin="orchestrator",
        )
        context = SecurityContext(
            actor_id=None,
            origin="orchestrator",
        )
        decision: SecurityDecision = self._security.check(
            request, context=context
        )
        if decision.allowed:
            return None
        if decision.requires_confirmation:
            self._logger.warning(
                "Tool '%s' call %s requires confirmation (id=%s); "
                "not auto-executed",
                tool.name,
                tool_call.id,
                decision.confirmation_id,
            )
            return ToolResult.fail(
                error=(
                    f"Tool '{tool.name}' requires confirmation "
                    f"(confirmation {decision.confirmation_id}); "
                    "not auto-executed in the autonomous loop"
                )
            )
        self._logger.warning(
            "Tool '%s' call %s denied: %s",
            tool.name,
            tool_call.id,
            decision.reason,
        )
        return ToolResult.fail(
            error=f"Tool '{tool.name}' denied by security policy: {decision.reason}"
        )
