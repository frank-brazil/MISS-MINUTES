"""Worker-side service: registration, typed task execution, heartbeats.

The service is transport-independent: it depends only on injected
abstractions (``WorkerInfo``, a ``WorkerExecutor``, and an optional
``MasterTransport``).  A concrete transport (HTTP, in-memory) wires it up.
"""

import asyncio
import logging
from uuid import UUID

from app.distributed.config import HEARTBEAT_INTERVAL_SECONDS, DistributedConfig
from app.distributed.executor import WorkerExecutor
from app.distributed.models import (
    DistributedTask,
    DistributedTaskResult,
    WorkerHeartbeat,
    WorkerInfo,
    WorkerStatus,
)
from app.distributed.transport import MasterTransport
from app.security.manager import SecurityManager, as_security_manager
from app.security.models import (
    Permission,
    PermissionCategory,
    SecurityContext,
    SecurityDecision,
)
from app.security.policy import SecurityPolicy


class WorkerService:
    def __init__(
        self,
        *,
        worker_info: WorkerInfo,
        executor: WorkerExecutor,
        config: DistributedConfig | None = None,
        master_transport: MasterTransport | None = None,
        security: "SecurityManager | SecurityPolicy | None" = None,
    ) -> None:
        self._worker = worker_info
        self._executor = executor
        self._config = config or DistributedConfig()
        self._master_transport = master_transport
        self._security = as_security_manager(security)
        self._logger = logging.getLogger(__name__)

    @property
    def worker_id(self) -> UUID:
        return self._worker.worker_id

    @property
    def worker_info(self) -> WorkerInfo:
        return self._worker

    @property
    def executor(self) -> WorkerExecutor:
        return self._executor

    @property
    def security(self) -> SecurityManager | None:
        return self._security

    def attach_master_transport(self, transport: MasterTransport | None) -> None:
        self._master_transport = transport

    async def register_with_master(self) -> bool:
        """Register this worker with the master over the injected transport."""
        if self._master_transport is None:
            self._logger.warning(
                "No master transport configured; skipping registration for %s",
                self.worker_id,
            )
            return False
        self._logger.info("Registering worker %s with master", self.worker_id)
        return await self._master_transport.register_worker(self._worker)

    async def send_heartbeat(
        self,
        *,
        status: WorkerStatus | None = None,
    ) -> bool:
        """Send one heartbeat over the injected transport."""
        if self._master_transport is None:
            self._logger.warning(
                "No master transport configured; skipping heartbeat for %s",
                self.worker_id,
            )
            return False
        heartbeat = WorkerHeartbeat(
            worker_id=self.worker_id,
            status=status or self._worker.status,
            capabilities=self._worker.capabilities,
            resources=self._worker.resources,
        )
        self._logger.info(
            "Sending heartbeat: worker_id=%s status=%s",
            self.worker_id,
            heartbeat.status.value,
        )
        return await self._master_transport.send_heartbeat(heartbeat)

    async def heartbeat_loop(
        self,
        *,
        interval: float | None = None,
        exit_event: asyncio.Event | None = None,
    ) -> None:
        """Periodic heartbeat loop; returns when cancellation is requested.

        Deterministic tests may call :meth:`send_heartbeat` directly instead
        of driving this loop.
        """
        period = interval or self._config.heartbeat_interval_seconds
        self._logger.info(
            "Heartbeat loop started: worker_id=%s interval=%ss",
            self.worker_id,
            period,
        )
        while True:
            if exit_event is not None and exit_event.is_set():
                break
            await self.send_heartbeat()
            await asyncio.sleep(period)

    async def handle_task(
        self,
        task: DistributedTask,
        *,
        assignment_id: UUID | None = None,
    ) -> DistributedTaskResult:
        """Validate and execute one typed distributed task.

        Every task is validated against the executor's approved capabilities
        and task types before execution.  When a security policy is
        configured, the task is additionally evaluated against it and only
        executed on an explicit allow; unknown/critical risks and requests
        that need a human confirmation are refused (fail closed).  The result
        echoes the active assignment and this worker's ID so the master can
        deduplicate duplicate responses.
        """
        self._logger.info(
            "Worker received task: task_id=%s task_type=%s",
            task.distributed_task_id,
            task.task_type,
        )
        validate_error = self._executor.validate(task)
        if validate_error is not None:
            self._logger.warning(
                "Worker rejected unapproved task: task_id=%s error=%s",
                task.distributed_task_id,
                validate_error,
            )
            return DistributedTaskResult.fail(
                task.distributed_task_id,
                assignment_id=assignment_id,
                worker_id=self.worker_id,
                error=validate_error,
            )
        if self._security is not None:
            decision = self._authorize_task(task)
            if not decision.allowed:
                if decision.requires_confirmation:
                    reason = "task requires confirmation; worker cannot auto-confirm"
                else:
                    reason = (
                        "task denied by worker security policy: "
                        f"{decision.reason_code or 'denied'}"
                    )
                self._logger.warning(
                    "Worker security refused task: task_id=%s reason=%s",
                    task.distributed_task_id,
                    reason,
                )
                return DistributedTaskResult.fail(
                    task.distributed_task_id,
                    assignment_id=assignment_id,
                    worker_id=self.worker_id,
                    error=reason,
                )
        result = await self._executor.execute(task)
        result.assignment_id = assignment_id or result.assignment_id
        result.worker_id = self.worker_id
        return result

    def _authorize_task(self, task: DistributedTask) -> SecurityDecision:
        """Evaluate a typed task against the worker's security policy."""
        security = self._security  # guaranteed not None by caller
        permission = Permission(
            category=PermissionCategory.DISTRIBUTED,
            resource=task.task_type,
        )
        request = security.create_request(
            permission=permission,
            action="distributed:execute",
            task_id=task.distributed_task_id,
            actor=str(self.worker_id),
            origin="distributed-worker",
        )
        context = SecurityContext(
            actor_id=str(self.worker_id),
            worker_id=self.worker_id,
            origin="distributed-worker",
        )
        return security.check(request, context=context)