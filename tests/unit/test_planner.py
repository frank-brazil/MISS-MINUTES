import asyncio
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.core.planner import (
    ManualPlanner,
    Plan,
    Planner,
    PlanStep,
)
from app.core.task import Task, TaskStatus


class FakePlanner(Planner):
    name = "fake-planner"
    description = "A fake planner that returns a canned plan for tests."

    def __init__(
        self, descriptions: Sequence[str], dependencies: Sequence[Sequence[str]] = ()
    ) -> None:
        self._descriptions = list(descriptions)
        self._dependencies = list(dependencies)

    async def plan(self, task: Task) -> Plan:
        steps: list[PlanStep] = []
        for index, description in enumerate(self._descriptions):
            deps: set[UUID] = set()
            for dep_description in (
                self._dependencies[index] if index < len(self._dependencies) else ()
            ):
                dep_steps = [step for step in steps if step.description == dep_description]
                if not dep_steps:
                    raise ValueError(f"unknown dependency: {dep_description}")
                deps.add(dep_steps[0].step_id)
            steps.append(PlanStep(description=description, dependencies=deps))
        return Plan(task_id=task.task_id, goal=task.description, steps=steps)


def test_plan_step_creation() -> None:
    step = PlanStep(description="Find relevant notes.")
    assert step.description == "Find relevant notes."
    assert isinstance(step.step_id, UUID)
    assert step.status == TaskStatus.PENDING
    assert step.dependencies == frozenset()


def test_plan_step_automatic_ids() -> None:
    first = PlanStep(description="first")
    second = PlanStep(description="second")
    assert isinstance(first.step_id, UUID)
    assert isinstance(second.step_id, UUID)
    assert first.step_id != second.step_id


def test_plan_step_blank_description_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanStep(description="")
    with pytest.raises(ValidationError):
        PlanStep(description="   ")


def test_plan_step_invalid_status_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanStep(description="step", status="invalid-status")


def test_plan_step_dependencies_coerced_to_frozenset() -> None:
    step_id = UUID(int=1)
    step = PlanStep(description="step", dependencies=[step_id])
    assert isinstance(step.dependencies, frozenset)
    assert step.dependencies == frozenset({step_id})


def test_plan_step_dependencies_are_immutable() -> None:
    step = PlanStep(description="step")
    with pytest.raises(AttributeError):
        step.dependencies.add(UUID(int=9))


def test_plan_creation() -> None:
    task = Task(description="Prepare exam revision.")
    step = PlanStep(description="Find notes.")
    plan = Plan(task_id=task.task_id, goal=task.description, steps=[step])
    assert isinstance(plan.plan_id, UUID)
    assert plan.task_id == task.task_id
    assert plan.goal == "Prepare exam revision."
    assert plan.steps == [step]
    assert isinstance(plan.created_at, datetime)
    assert plan.created_at.tzinfo is not None


def test_plan_automatic_plan_id() -> None:
    task = Task(description="a")
    first = Plan(task_id=task.task_id, goal="a", steps=[PlanStep(description="s")])
    second = Plan(task_id=task.task_id, goal="a", steps=[PlanStep(description="s")])
    assert first.plan_id != second.plan_id


def test_plan_blank_goal_rejected() -> None:
    task = Task(description="a")
    step = PlanStep(description="step")
    with pytest.raises(ValidationError):
        Plan(task_id=task.task_id, goal="", steps=[step])


def test_plan_without_steps_rejected() -> None:
    task = Task(description="a")
    with pytest.raises(ValidationError):
        Plan(task_id=task.task_id, goal="a", steps=[])


def test_plan_ordering_is_deterministic() -> None:
    task = Task(description="a")
    steps = [PlanStep(description="first"), PlanStep(description="second")]
    plan = Plan(task_id=task.task_id, goal="a", steps=steps)
    assert [step.description for step in plan.steps] == ["first", "second"]


def test_valid_dependencies_accepted() -> None:
    first = PlanStep(description="gather notes")
    second = PlanStep(description="summarize", dependencies={first.step_id})
    plan = Plan(
        task_id=UUID(int=1),
        goal="goal",
        steps=[first, second],
    )
    assert second.step_id in {s.step_id for s in plan.steps}
    assert plan.steps[1].dependencies == frozenset({first.step_id})


def test_multiple_valid_dependencies_accepted() -> None:
    a = PlanStep(description="a")
    b = PlanStep(description="b")
    c = PlanStep(description="c", dependencies={a.step_id, b.step_id})
    plan = Plan(task_id=UUID(int=1), goal="goal", steps=[a, b, c])
    assert plan.steps[2].dependencies == frozenset({a.step_id, b.step_id})


def test_dependency_on_unknown_step_rejected() -> None:
    step = PlanStep(description="step", dependencies={UUID(int=999)})
    with pytest.raises(ValidationError, match="unknown step"):
        Plan(task_id=UUID(int=1), goal="goal", steps=[step])


def test_self_dependency_rejected() -> None:
    fixed_id = UUID(int=7)
    step = PlanStep(
        step_id=fixed_id,
        description="step",
        dependencies={fixed_id},
    )
    with pytest.raises(ValidationError, match="depend on itself"):
        Plan(task_id=UUID(int=1), goal="goal", steps=[step])


def test_forward_dependency_rejected() -> None:
    later = PlanStep(description="later")
    earlier = PlanStep(description="earlier", dependencies={later.step_id})
    with pytest.raises(ValidationError, match="earlier step"):
        Plan(task_id=UUID(int=1), goal="goal", steps=[earlier, later])


def test_duplicate_step_ids_rejected() -> None:
    duplicate_id = UUID(int=42)
    first = PlanStep(step_id=duplicate_id, description="first")
    second = PlanStep(step_id=duplicate_id, description="second")
    with pytest.raises(ValidationError, match="duplicate step id"):
        Plan(task_id=UUID(int=1), goal="goal", steps=[first, second])


def test_auto_ids_do_not_trigger_duplicate() -> None:
    steps = [PlanStep(description="a"), PlanStep(description="b")]
    plan = Plan(task_id=UUID(int=1), goal="goal", steps=steps)
    ids = [step.step_id for step in plan.steps]
    assert len(set(ids)) == len(ids)


def test_planner_is_abstract() -> None:
    with pytest.raises(TypeError):
        Planner()


def test_planner_requires_metadata() -> None:
    with pytest.raises(TypeError, match="name"):

        class MissingMetadata(Planner):
            async def plan(self, task: Task) -> Plan:
                return Plan(
                    task_id=task.task_id,
                    goal=task.description,
                    steps=[PlanStep(description="step")],
                )


def test_planner_is_provider_independent() -> None:
    assert "fastapi" not in getattr(Planner, "__module__", "")
    assert Planner.__module__ == "app.core.planner"


def test_manual_planner_satisfies_interface() -> None:
    planner = ManualPlanner(["Find notes.", "Create revision plan."])
    assert isinstance(planner, Planner)
    assert planner.name == "manual"


def test_manual_planner_builds_plan_for_task() -> None:
    task = Task(description="Prepare my Computer Networks exam revision.")
    planner = ManualPlanner(
        [
            "Find relevant notes.",
            "Find previous questions.",
            "Analyze important topics.",
            "Create a revision plan.",
        ]
    )
    plan = asyncio.run(planner.plan(task))
    assert isinstance(plan, Plan)
    assert plan.task_id == task.task_id
    assert plan.goal == task.description
    assert [step.description for step in plan.steps] == [
        "Find relevant notes.",
        "Find previous questions.",
        "Analyze important topics.",
        "Create a revision plan.",
    ]
    assert all(step.status == TaskStatus.PENDING for step in plan.steps)


def test_manual_planner_does_not_hard_code_tasks() -> None:
    first_task = Task(description="Plan A")
    second_task = Task(description="Plan B")
    planner = ManualPlanner(["step one", "step two"])
    plan_a = asyncio.run(planner.plan(first_task))
    plan_b = asyncio.run(planner.plan(second_task))
    assert plan_a.task_id == first_task.task_id
    assert plan_b.task_id == second_task.task_id
    assert plan_a.task_id != plan_b.task_id
    assert plan_a.goal == "Plan A"
    assert plan_b.goal == "Plan B"


def test_fake_planner_returns_canned_plan() -> None:
    task = Task(description="generic goal")
    planner = FakePlanner(["alpha", "beta", "gamma"])
    plan = asyncio.run(planner.plan(task))
    assert plan.task_id == task.task_id
    assert [step.description for step in plan.steps] == [
        "alpha",
        "beta",
        "gamma",
    ]
    assert [step.status for step in plan.steps] == [TaskStatus.PENDING] * 3


def test_fake_planner_builds_valid_dependencies() -> None:
    task = Task(description="goal")
    planner = FakePlanner(
        ["alpha", "beta", "gamma"],
        [(), ("alpha",), ("alpha", "beta")],
    )
    plan = asyncio.run(planner.plan(task))
    assert plan.steps[1].dependencies == frozenset({plan.steps[0].step_id})
    assert plan.steps[2].dependencies == frozenset({plan.steps[0].step_id, plan.steps[1].step_id})
