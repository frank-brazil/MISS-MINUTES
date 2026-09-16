# Security and permissions system (CHUNK 30)

A centralized, fail-closed permission layer that gates tool calls in the
orchestrator, actions in the autonomous problem-solving loop, and task
dispatch/execution across the distributed layer.  It composes four concerns
behind one small entry point (`SecurityManager`): **risk assessment**,
**policy evaluation**, **human confirmation**, and **redacted audit**.

## Scope

Implemented:

- Typed security models (`PermissionCategory`, `RiskLevel`, `Permission`,
  `PermissionRequest`, `SecurityContext`, `SecurityDecision`,
  `PermissionRule`, `Confirmation`, `AuditEvent`) plus typed exceptions
  (`PermissionDenied`, `ConfirmationRequired`, ...).
- Deterministic `RiskAssessor`: a category baseline plus conservative,
  word-boundary-aware keyword heuristics.  Unclassifiable categories are
  `UNKNOWN` so policies fail closed.
- Injectable `SecurityPolicy` implementations: `AllowDenyPolicy`,
  `ConservativePolicy` (fail-closed default), `DefaultPolicy` (explicit
  low/medium-risk opt-in), `DenyAllPolicy` (used whenever a manager is built
  with no policy).
- `ConfirmationManager`: pending → approved/denied/expired, with a TTL so a
  stale approval can never enable a later request.
- `InMemoryAuditStore` + `AuditLogger` recording **redacted metadata only**
  with max-count and optional max-age retention.
- Secret-value `redaction` helpers applied before anything is stored or
  surfaced in a confirmation.
- Integration at every execution path exactly once: Orchestrator tool loop,
  problem-solving loop, distributed coordinator, distributed worker service.
- A `SecurityManager`/`SecurityPolicy`/`None` normalization helper
  (`as_security_manager`) so a bare policy can be injected anywhere.

Explicitly **not** implemented (later chunks / out of scope):

- A formal certifiable security framework: policies, redaction heuristics and
  the in-memory audit store are hygiene, not a published standard/audit.
- Credential vaulting or secret storage: secrets are never persisted here.
- Replacing the distributed shared-token auth (`X-Auth-Token`); security rules
  complement it, they do not replace transport authentication.
- Unrestricted remote execution: workers still only run typed, validated
  tasks through their approved executor.

## Architecture

```
Request/action/task
        │
        ▼
SecurityManager.check(request, context)
   ├─ RiskAssessor.assess(category, action)        → RiskLevel
   ├─ SecurityPolicy.evaluate(request, context)    → SecurityDecision
   ├─ ConfirmationManager (when gate required)     → confirmation_id
   └─ AuditLogger.log(...)                          → redacted AuditEvent
        │
        ▼
  ALLOW  → the existing Tool / ActionExecutor / Worker boundary executes
  DENY / REQUIRE_CONFIRMATION  → the operation must not run
```

- The security layer **never executes operations**.  It only decides; the
  existing tool/agent/executor boundaries do the work after an allow.
- Policy evaluation is pure and deterministic; confirmation and audit are the
  only side effects, and both are injectable for tests.
- `SecurityManager.check()` is synchronous so the (synchronous) coordinator
  can call it without restructuring.

## Risk assessment

Categories map to a baseline:

| Category      | Baseline risk |
|---------------|---------------|
| `READ`        | LOW           |
| `WRITE`       | MEDIUM        |
| `EXECUTE`     | MEDIUM        |
| `BROWSER`     | MEDIUM        |
| `NETWORK`     | MEDIUM        |
| `SYSTEM`      | HIGH          |
| `SENSITIVE`   | CRITICAL      |
| `DISTRIBUTED` | MEDIUM        |

Heuristics only **elevate**:

- shell metacharacters (`| & ; > < ` $ \`) elevate MEDIUM→HIGH, HIGH→CRITICAL;
- destructive keywords (`delete`, `drop table`, `rm -rf`, ...) elevate
  LOW→MEDIUM, MEDIUM→HIGH, HIGH→CRITICAL;
- privileged keywords (`admin`, `sudo`, `password`, `secret`, `token`, ...)
  elevate LOW→MEDIUM, MEDIUM→HIGH.

Keyword matching is case-insensitive and word-boundary aware, so ordinary
words such as “information” (which contains “format”) do not falsely elevate.

## Policy evaluation

`AllowDenyPolicy` applies this precedence (highest first):

1. explicit deny rule matches → **DENY**
2. unknown risk → **DENY** (fail closed)
3. critical risk → **DENY** (never auto-approved)
4. no allow rule matches → **DENY** (missing permission)
5. risk class is in `require_confirmation` → **REQUIRE_CONFIRMATION**
6. otherwise → **ALLOW**

`PermissionRule.resource` is matched exactly or with a leading/trailing `*`
wildcard (`*.txt`, `state/*`, `*secret*`); a missing resource matches any
subject in that category.  Explicit deny always beats allow.  The generic
fail-closed default is `DenyAllPolicy`.  `ConservativePolicy` allows only
explicit rules; `DefaultPolicy` additionally auto-allows LOW/MEDIUM without a
rule (useful for local, single-actor tooling only).

## Confirmation flow

Creating a confirmation is **never** an approval:

1. a check returns `REQUIRE_CONFIRMATION` and `ConfirmationManager.create`
   opens a `PENDING` confirmation with an expiry (default TTL 60s);
2. an operator must **explicitly** call `approve(...)` (or `deny(...)`);
3. the caller re-checks the same request passing
   `approved_confirmation_id`; `is_active_approval_for` returns true only for
   an APPROVED, unexpired confirmation bound to that exact request;
4. the re-check yields `ALLOW` with `reason_code="approved_confirmation"`.

Expired/denied confirmations can never approve; a confirmation that expires
between approval and use is treated as inactive.  An autonomous loop (no human
in the loop) therefore **never** auto-executes gated actions — it fails closed
and the trace records why.

## Audit and redaction

- Every `check` and every manual `audit_event` write is persisted through
  `AuditLogger`, which stores an immutable, structured `AuditEvent`.
- `success` is derived from the decision: ALLOW → `True`,
  REQUIRE_CONFIRMATION → `None`, DENY → `False`.
- Free-text fields (`action`, `resource`) are **redacted before storage**:
  bearer/basic tokens, `key=value` / `key: value` secrets, and mapping values
  under secret-looking keys (`token`, `password`, `secret`, `api_key`, ...)
  are scrubbed.  Redaction is heuristic, not a formal guarantee.
- `InMemoryAuditStore` enforces `max_events` (default 1000) and an optional
  `max_age_seconds`; `snapshot()` returns retained events oldest-first.

## Integration points

One check per execution path; behavior is fail-closed when no permission is
declared or the system is unknown.

- **Orchestrator** (`app/core/orchestrator.py`): every tool call in the AI
  loop passes `_check_tool_security` before `tool.execute`.  A tool with no
  declared permission is denied (audited as `undeclared_permission`).  Denied
  or confirmation-gated calls become failed `ToolResult`s and are never
  executed.
- **Problem-solving loop** (`app/solver/engine.py`): each acting phase calls
  `_block_action_by_security` (category `EXECUTE`).  Denial/gating sets the
  attempt outcome, records an `ACTION` event, and the loop fails with a clear
  reason.
- **Distributed coordinator** (`app/distributed/coordinator.py`): each
  dispatch is authorized (category `DISTRIBUTED`, resource = task type)
  before assignment; refused tasks fail with an audited reason instead of
  stranding.
- **Distributed worker** (`app/distributed/service.py`): the task is first
  validated by the executor (approved types/capabilities), then authorized.
  Denial or a confirmation gate returns a failed `DistributedTaskResult`;
  workers never auto-confirm.

`Origin` values (`orchestrator`, `solver`, `distributed-master`,
`distributed-worker`) and actor/worker IDs are recorded in the audit trail.

## Tool permission mapping

Tools keep their existing `ToolPermission` (read/write/system; the enum is
unchanged and asserted by `tests/unit/test_permissions.py`).  The manager maps
`READ/WRITE/SYSTEM` onto the matching `PermissionCategory`.  Tools that do not
declare a permission are treated as unknown and denied.

## Testing

- `tests/unit/test_security_{models,redaction,risk,policy,confirmation,audit,manager}.py`
  cover the security package itself (pure policy evaluation, confirmation
  lifecycle, retention, redaction, manager normalization).
- `tests/unit/test_security_integrations.py` exercises the real integration
  seams: orchestrator allow/deny/confirmation/undeclared, loop deny/confirmation,
  coordinator dispatch refusal/allow, worker refusal/allow, plus a static check
  that `app/security` imports no browser/vision/screen/tools/network client.

## Limitations / notes

- Policy rules are machine-readable and deterministic, but an operator still
  owns reviewing what is allowed before enabling a policy in production.
- Redaction and risk heuristics are best-effort; they must not be treated as
  the sole protection for real credentials.
- The audit store ships in-memory; a durable backend is future work.
- Distributed transport authentication remains the shared `X-Auth-Token`
  scheme; permission checks are an additional authorization layer on top.