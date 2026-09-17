import asyncio

import pytest
from app.agents.base import Agent, AgentResult
from app.core.task import Task


class SuccessfulSampleAgent(Agent):
    name = "sample-agent"
    description = "A sample agent that succeeds."
    capabilities = frozenset({"sample", "test"})

    async def execute(self, task: Task) -> AgentResult:
        return AgentResult.ok(output=f"handled {task.description}")


class FailingSampleAgent(Agent):
    name = "failing-agent"
    description = "A sample agent that fails."
    capabilities = frozenset({"sample", "failure"})

    async def execute(self, task: Task) -> AgentResult:
        return AgentResult.fail(error="sample failure", output="partial output")


def test_agent_is_abstract() -> None:
    with pytest.raises(TypeError):
        Agent()


def test_agent_requires_metadata() -> None:
    with pytest.raises(TypeError, match="name"):

        class MissingMetadata(Agent):
            async def execute(self, task: Task) -> AgentResult:
                return AgentResult.ok()


def test_required_agent_metadata() -> None:
    assert SuccessfulSampleAgent.name == "sample-agent"
    assert SuccessfulSampleAgent.description == "A sample agent that succeeds."
    assert SuccessfulSampleAgent.capabilities == frozenset({"sample", "test"})


def test_concrete_sample_satisfies_interface() -> None:
    agent = SuccessfulSampleAgent()
    assert isinstance(agent, Agent)
    task = Task(description="verify interface")
    assert asyncio.run(agent.execute(task)) is not None


def test_successful_execution_result() -> None:
    agent = SuccessfulSampleAgent()
    task = Task(description="do something")
    result = asyncio.run(agent.execute(task))
    assert isinstance(result, AgentResult)
    assert result.success is True
    assert result.output == "handled do something"
    assert result.error is None


def test_failure_execution_result() -> None:
    agent = FailingSampleAgent()
    task = Task(description="do something")
    result = asyncio.run(agent.execute(task))
    assert isinstance(result, AgentResult)
    assert result.success is False
    assert result.error == "sample failure"
    assert result.output == "partial output"
