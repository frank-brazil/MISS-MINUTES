# Distributed multi-machine layer (CHUNK 29)

A master coordinates **typed tasks** across one or more worker machines.
Workers never accept arbitrary work: they only execute operations their
executor has approved for a declared **task type** and **capability set**.
The coordinator is deterministic and testable offline; the HTTP/network
layers are optional concrete transports on top of injection points.

## Scope

Implemented:

- Typed data models (`WorkerInfo`, `DistributedTask`, `TaskAssignment`,
  `DistributedTaskResult`, heartbeats, resources, statuses).
- Worker registry with heartbeat tracking, staleness detection and
  capability filtering.
- FIFO task queue, deterministic capability-aware scheduler.
- Master coordinator: submit → dispatch → execute → result, with bounded
  retries, idempotent result handling, dispatch timeouts and heartbeat-based
  staleness rerouting.
- Worker service + executor boundary; a fake executor ships for offline use.
- Provider-independent transports with in-memory fakes and real HTTP(S)
  transports (`HttpWorkerTransport`, `HttpMasterTransport`,
  `EndpointAwareWorkerTransport`), plus master/worker FastAPI apps.
- Shared-token authentication boundary (`X-Auth-Token`).
- Safe, concise observability events (no auth tokens, no raw payloads).
- Optional `DistributedAdapter` bridging planner steps to workers.

Explicitly **not** implemented (later chunks / out of scope):

- A full per-actor permissions/security framework (auth is a shared token).
- Unrestricted remote command execution; arbitrary shell/payload execution.
- Unauthorized network exposure (defaults bind to loopback only).
- AI-based or priority scheduling (the scheduler is deterministic).
- Durable task queues beyond the in-memory FIFO.

## Architecture

```
Master process                                   Worker process
------------------------------------------------  ---------------------------------
create_master_app                                create_worker_app
  registry (WorkerRegistry)                         WorkerService
  queue (DistributedTaskQueue)                        └─ WorkerExecutor
  coordinator (DistributedCoordinator)                 (approves task types +
      └─ transport (WorkerTransport)                       required capabilities)
           ├─ FakeWorkerTransport (offline/tests)   POST /distributed/execute
           ├─ HttpWorkerTransport (single worker)
           └─ EndpointAwareWorkerTransport (multi)
```

- The **coordinator** never executes work; it routes to the injected
  `WorkerTransport`.
- Workers POST registration + heartbeats to the master via
  `MasterTransport` (`HttpMasterTransport` in production).
- Master → worker dispatch is one `POST /distributed/execute` carrying the
  assignment id and the typed task; the response body is the
  `DistributedTaskResult`.

## Safety boundaries

1. **Typed tasks only.** A `DistributedTask` carries a `task_type` and a
   `required_capabilities` set of tags. `WorkerExecutor.validate()` (enforced
   by `WorkerService.handle_task`) rejects anything outside the worker's
   `allowed_task_types` / `capabilities`. Capabilities are tags, never code.
2. **No secrets in models.** `WorkerInfo`, `DistributedTask`, events and
   results contain no tokens or credentials. The auth token lives only in
   `DistributedConfig` and is attached by transports.
3. **Loopback by default.** Master and worker bind to `127.0.0.1`. To expose
   a worker to the network you must set the bind host explicitly **and**
   configure an auth token.
4. **Bounded retries + dedupe.** A task runs at most `max_retries` attempts.
   `DistributedTaskResult.assignment_id` lets the coordinator ignore stale or
   duplicate replies.
5. **Deterministic scheduling.** Capability match → `AVAILABLE` + non-stale →
   lowest `current_load` → lowest worker UUID. No randomness, reproducible
   offline.

## Configuration

`DistributedConfig` (env-prefixed `MISSMINUTES_*`):

| Variable | Default | Meaning |
| --- | --- | --- |
| `MISSMINUTES_MASTER_HOST` / `_PORT` | `127.0.0.1` / `8100` | Master bind address |
| `MISSMINUTES_WORKER_HOST` / `_PORT` | `127.0.0.1` / `8200` | Worker bind address |
| `MISSMINUTES_AUTH_TOKEN` | empty | Shared token; empty disables auth (loopback only) |
| `MISSMINUTES_HEARTBEAT_INTERVAL` | `15` | Heartbeat cadence (s) |
| `MISSMINUTES_HEARTBEAT_TIMEOUT` | `30` | No-heartbeat window before stale (s) |
| `MISSMINUTES_MAX_RETRIES` | `2` | Max attempts per task |
| `MISSMINUTES_MAX_CONCURRENT_DISPATCH` | `4` | Coordinator dispatch cap |
| `MISSMINUTES_DISPATCH_TIMEOUT` | `30` | In-flight assignment timeout (s) |

## Master API (mounted at `/distributed`)

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/workers/register` | Register a `WorkerInfo` (409 on duplicate) |
| POST | `/workers/heartbeat` | Apply a `WorkerHeartbeat` (404 if unregistered) |
| GET | `/workers` | List registered workers |
| POST | `/tasks` | Submit a `DistributedTask` (202) |
| GET | `/tasks` | Task snapshot summaries |
| DELETE | `/tasks/{task_id}` | Cancel a queued/in-flight task |
| GET | `/events` | Observability events |
| GET | `/health` | Role/counts |

Worker API: `POST /distributed/execute` (assignment id + typed task → result).

## Offline / test wiring

```python
registry = WorkerRegistry()
queue = DistributedTaskQueue()
transport = FakeWorkerTransport(executor=FakeWorkerExecutor(output="done"))
coordinator = DistributedCoordinator(registry=registry, queue=queue, transport=transport)
coordinator.submit(DistributedTask(task_type="analysis", required_capabilities=frozenset({"analysis"})))
assignment = coordinator.dispatch_next()
result = asyncio.run(coordinator.dispatch_async(assignment, task))
coordinator.accept_result(result)
```

The integration test drives the full master+worker HTTP pipeline over an
in-memory ASGI transport (`tests/integration/test_distributed_pipeline.py`).

## Test coverage

`tests/unit/test_distributed_*.py` (models, events, config, auth, registry,
queue, scheduler, executor, coordinator, worker service, transports, HTTP
API, adapter) plus the integration pipeline, ~135 tests. All run offline
without network or real clocks (injected `now`/`now_fn`).