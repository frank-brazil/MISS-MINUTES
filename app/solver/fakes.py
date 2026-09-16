"""Deterministic fakes for the action and observation boundaries.

These fakes never touch the real computer, screen, browser, network or file
system.  They exist so the problem-solving loop is safe and testable offline
by default.
"""

import logging
from typing import Any

from app.solver.actions import ActionExecutor, ActionRequest, ActionResult
from app.solver.observation import (
    ObservationProvider,
    ObservationRequest,
    ObservationResult,
)


class FakeActionExecutor(ActionExecutor):
    name = "fake-action-executor"
    description = (
        "Deterministic action executor that performs no real actions, used "
        "offline and in tests."
    )

    def __init__(
        self,
        *,
        fail: bool = False,
        fail_message: str = "simulated action failure",
        raise_error: Exception | None = None,
        success_output: str = "Action completed.",
        observation_data: dict[str, Any] | None = None,
        fail_iterations: frozenset[int] = frozenset(),
    ) -> None:
        self._logger = logging.getLogger(__name__)
        self._fail = fail
        self._fail_message = fail_message
        self._raise_error = raise_error
        self._success_output = success_output
        self._observation_data = observation_data or {}
        self._fail_iterations = fail_iterations
        self._requests: list[ActionRequest] = []

    @property
    def requests(self) -> tuple[ActionRequest, ...]:
        return tuple(self._requests)

    async def execute(self, request: ActionRequest) -> ActionResult:
        self._requests.append(request)
        if self._raise_error is not None:
            self._logger.error(
                "Fake action executor raising: %s",
                type(self._raise_error).__name__,
            )
            raise self._raise_error
        if self._fail or request.iteration in self._fail_iterations:
            self._logger.warning(
                "Fake action executor configured to fail at iteration %s",
                request.iteration,
            )
            return ActionResult.fail(
                action_id=request.action_id,
                error=self._fail_message,
            )
        self._logger.info(
            "Fake action executor succeeded at iteration %s",
            request.iteration,
        )
        return ActionResult.ok(
            action_id=request.action_id,
            output=self._success_output,
            observation_data=dict(self._observation_data),
        )


class FakeObservationProvider(ObservationProvider):
    name = "fake-observation-provider"
    description = (
        "Deterministic observation provider that returns configured, "
        "pre-recorded observations and performs no real observation."
    )

    def __init__(
        self,
        *,
        observations: list[str] | None = None,
        action_succeeded: bool | None = True,
        fail: bool = False,
        fail_message: str = "simulated observation failure",
        raise_error: Exception | None = None,
    ) -> None:
        self._logger = logging.getLogger(__name__)
        self._observations = list(observations or [])
        self._action_succeeded = action_succeeded
        self._fail = fail
        self._fail_message = fail_message
        self._raise_error = raise_error
        self._requests: list[ObservationRequest] = []

    @property
    def requests(self) -> tuple[ObservationRequest, ...]:
        return tuple(self._requests)

    async def observe(self, request: ObservationRequest) -> ObservationResult:
        self._requests.append(request)
        if self._raise_error is not None:
            self._logger.error(
                "Fake observation provider raising: %s",
                type(self._raise_error).__name__,
            )
            raise self._raise_error
        if self._fail:
            self._logger.warning(
                "Fake observation provider configured to fail"
            )
            return ObservationResult.fail(
                observation_id=request.observation_id,
                error=self._fail_message,
                observations=list(self._observations),
            )
        return ObservationResult.ok(
            observation_id=request.observation_id,
            observations=list(self._observations),
            action_succeeded=self._action_succeeded,
        )