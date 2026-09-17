"""HTTP transports for the distributed layer.

- :class:`HttpWorkerTransport` (master → worker): POSTs a typed assignment to
  the worker's ``/distributed/execute`` endpoint and reads the structured
  result back from the response.
- :class:`HttpMasterTransport` (worker → master): POSTs registration and
  heartbeats to the master's endpoints.

Both attach the shared authentication header built from configuration.
Concrete network classes are optional dependencies of the core layer: the
core coordinator/worker code only ever sees the ABCs in ``transport.py``.
"""

import logging

import httpx

from app.distributed.auth import request_headers
from app.distributed.config import DistributedConfig
from app.distributed.models import (
    DistributedTask,
    DistributedTaskResult,
    WorkerHeartbeat,
    WorkerInfo,
)
from app.distributed.registry import WorkerRegistry
from app.distributed.transport import (
    MasterTransport,
    TransportError,
    WorkerTransport,
    WorkerUnreachableError,
)

EXECUTE_PATH = "/distributed/execute"
REGISTER_PATH = "/distributed/workers/register"
HEARTBEAT_PATH = "/distributed/workers/heartbeat"


class HttpWorkerTransport(WorkerTransport):
    """Master → worker dispatch over HTTP(S).

    The worker endpoint is expected to execute the typed task and return the
    ``DistributedTaskResult`` JSON body directly.
    """

    name = "http-worker-transport"
    description = "Dispatches typed tasks to workers over authenticated HTTP(S)."

    def __init__(
        self,
        *,
        base_url: str,
        config: DistributedConfig | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._config = config or DistributedConfig()
        self._timeout = timeout
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._logger = logging.getLogger(__name__)

    @property
    def base_url(self) -> str:
        return self._base_url

    async def dispatch_task(
        self,
        assignment,
        task: DistributedTask,
    ) -> DistributedTaskResult:
        payload = {
            "assignment_id": str(assignment.assignment_id),
            "task": task.model_dump(mode="json"),
        }
        url = f"{self._base_url}{EXECUTE_PATH}"
        headers = request_headers(self._config)
        headers["accept"] = "application/json"
        try:
            response = await self._client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            self._logger.warning("HTTP dispatch request failed: url=%s error=%s", url, exc)
            raise WorkerUnreachableError(
                f"cannot reach worker at {self._base_url}: {type(exc).__name__}"
            ) from exc

        if response.status_code in (404, 405):
            raise WorkerUnreachableError(
                f"worker at {self._base_url} does not expose {EXECUTE_PATH}"
            )
        if response.status_code == 401:
            raise TransportError(f"worker at {self._base_url} rejected the auth token")
        if response.status_code >= 400:
            raise TransportError(f"worker returned HTTP {response.status_code}")
        try:
            data = response.json()
            return DistributedTaskResult.model_validate(data)
        except (ValueError, TypeError) as exc:
            raise TransportError(
                f"worker returned an invalid result body: {type(exc).__name__}"
            ) from exc

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class EndpointAwareWorkerTransport(WorkerTransport):
    """Master → worker dispatch that resolves each worker's HTTP endpoint.

    The assignment's ``worker_id`` is looked up in the injected registry; the
    worker's ``endpoint`` field supplies the base URL.  This supports the
    multi-machine master fanning tasks out to many workers.
    """

    name = "endpoint-aware-http-transport"
    description = "Dispatches to each worker's registered HTTP endpoint."

    def __init__(
        self,
        *,
        registry: WorkerRegistry,
        config: DistributedConfig | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._registry = registry
        self._config = config or DistributedConfig()
        self._timeout = timeout
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._logger = logging.getLogger(__name__)

    async def dispatch_task(self, assignment, task: DistributedTask) -> DistributedTaskResult:
        worker = self._registry.lookup(assignment.worker_id)
        if worker is None or not worker.endpoint:
            raise WorkerUnreachableError(f"no endpoint for worker {assignment.worker_id}")
        from app.distributed.httptransports import HttpWorkerTransport

        transport = HttpWorkerTransport(
            base_url=worker.endpoint,
            config=self._config,
            client=self._client,
        )
        return await transport.dispatch_task(assignment, task)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class HttpMasterTransport(MasterTransport):
    """Worker → master registration and heartbeat over HTTP(S)."""

    name = "http-master-transport"
    description = "Registers workers and sends heartbeats over authenticated HTTP(S)."

    def __init__(
        self,
        *,
        base_url: str,
        config: DistributedConfig | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._config = config or DistributedConfig()
        self._timeout = timeout
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._logger = logging.getLogger(__name__)

    @property
    def base_url(self) -> str:
        return self._base_url

    async def register_worker(self, info: WorkerInfo) -> bool:
        response = await self._post(REGISTER_PATH, info.model_dump(mode="json"))
        return 200 <= response.status_code < 300

    async def send_heartbeat(self, heartbeat: WorkerHeartbeat) -> bool:
        response = await self._post(HEARTBEAT_PATH, heartbeat.model_dump(mode="json"))
        return 200 <= response.status_code < 300

    async def _post(self, path: str, payload: dict) -> httpx.Response:
        url = f"{self._base_url}{path}"
        headers = request_headers(self._config)
        headers["accept"] = "application/json"
        try:
            return await self._client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            self._logger.warning("HTTP master request failed: url=%s error=%s", url, exc)
            raise TransportError(
                f"cannot reach master at {self._base_url}: {type(exc).__name__}"
            ) from exc

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
