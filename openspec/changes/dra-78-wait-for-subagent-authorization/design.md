## Context

The wait handler is bound to the running job's session id and job id. The `jobs` table stores each child job's nullable `parent_job_id`, while the child runs on its own child session; the current parent job's persisted `session_id` is the authoritative link back to the orchestrator session. The existing outcome resolver accepts only a job id and begins by subscribing to that job's live event stream. See proposal.md for the security motivation.

The vulnerable path reads and resolves an arbitrary id before any ownership comparison. The fix must be local to the agent-orchestrator runtime, must not add persistence or API surface, and must leave the resolver's timeout, live-event, and cancellation semantics intact for authorized children.

## Goals / Non-Goals

**Goals:**

- Establish an authorization decision before any child event subscription or outcome polling.
- Require the referenced job to name the current parent job, and require that current parent job to belong to the bound orchestrator session.
- Keep missing-job handling generic and avoid returning foreign job state or output.
- Preserve existing owned-child completion, failure, timeout, and parent-cancellation behavior.
- Exercise the authorization boundary and its no-polling property with deterministic unit tests.

**Non-Goals:**

- No changes to child spawning, child monitoring, cancellation propagation, or the job schema.
- No changes to the game-service or DragnCards WebSocket/Phoenix protocol; this path does not speak to that upstream surface.
- No attempt to authorize monitor tasks separately: monitors receive child ids directly from the server-owned spawn path and are not model-callable handlers.

## Decisions

1. **Check the persisted child and parent rows in the wait handler before invoking the resolver.**
   - The handler will fetch the requested job once, return the existing missing-job error when no row exists, fetch the current parent row when a context id is supplied, and reject unless the child names that parent and the parent belongs to the bound session.
   - Alternative rejected: adding a new repository query or database constraint. The existing job rows contain the authoritative relationship and session fields, and a new abstraction would expand a one-boundary fix without changing the race-free creation path.
   - Alternative rejected: putting the check inside `resolve_child_outcome`. That resolver is also used by the server-owned child monitor, whose inputs already come from a successful spawn, and mixing handler authorization into the generic outcome primitive would obscure its existing contract.

2. **Fail closed when the handler lacks parent/session context.**
   - Empty or mismatched context cannot prove ownership, so the handler returns the same generic ownership error and does not subscribe to the requested id.
   - Alternative rejected: authorizing by session only when `job_id` is empty. A session can contain multiple top-level and child jobs; session membership alone would leave the parent-job boundary bypassable.

3. **Use one generic ownership error with no child state.**
   - The rejection response will not include the child id's status, result text, error code/message, or cancellation reason. This avoids turning the authorization check into an existence/status oracle while giving the current agent an actionable refusal.
   - Alternative rejected: reuse `describe_child_outcome` for rejected rows. That function intentionally renders terminal details and would disclose exactly the data this boundary protects.

4. **Keep timeout and cancellation callbacks unchanged after authorization.**
   - Once the row matches, the handler invokes `resolve_child_outcome` with the same configured absolute budget, poll interval, and parent-cancellation callback, and keeps the existing timeout event announcement and result wrapping.
   - Alternative rejected: alter `resolve_child_outcome` or cancel unauthorized/timeout children. Waiting is observational; existing behavior explicitly abandons only the wait on timeout and leaves child cancellation to the parent cancellation path.

## Risks / Trade-offs

- The authorization lookup and the resolver's first row read are separate reads. The job relationship is server-managed and immutable during normal child execution, so this preserves the smallest change without adding a transaction around a potentially long wait. If a future administrative path can retarget parent jobs, that path must preserve the same ownership invariant.
- Existing direct unit tests that constructed unparented jobs must bind their handlers to a real parent and child. This makes tests reflect the runtime contract rather than weakening production authorization for test convenience.
- No DragnCards WebSocket or upstream protocol is involved, so there is no protocol compatibility risk from this change; the only external behavior change is refusal of previously unauthorized result reads.
