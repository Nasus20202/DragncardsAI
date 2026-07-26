# Persistent evaluations queue

## Why

Evaluations run asynchronously and can target a single move, a round, a seq range, or
the whole game. Today the only way to watch one is inside the per-game Evaluate drawer:
closing the drawer tears down the SSE stream and the user loses the view, there is no way
to see evaluations for other games, and there is no single place that shows everything
currently in flight. Users want evaluations to drop into a **persistent queue that is
accessible at all times**, where they can see what is in progress (across all games) and
cancel it.

## What Changes

- **eval-service** — add a cross-game listing endpoint `GET /evaluations` that returns
  recent + active evaluation requests (newest first), each summarized with its
  `request_id`, `game_id`, overall status, `created_at`, and a per-target summary
  (`scope`, `target_seq`, `round_span`, `status`). Support an `active=true` filter (only
  requests with at least one non-terminal target) and a bounded `limit`. Backed by a new
  `Repository.list_requests(...)` query over the eval Postgres — no in-memory state.
- **dashboard (History tab)** — a persistent **Evaluations queue**: a header control with
  an active-count badge that opens a standing panel listing all games' in-progress + recent
  evaluations (friendly game name + a scope label "Move #seq" / "Round N" / "Range" /
  "Whole game" + status + progress), polling the new list endpoint, with a per-request
  **Cancel**. Accessible anytime you are in the History tab, independent of the per-game
  Evaluate drawer.
- **dashboard (Evaluate drawer)** — becomes **configure-and-submit-only**: choosing scope +
  judge and submitting enqueues the request (which immediately appears in the queue) and the
  drawer can be closed freely; live progress, streaming, and cancel move to the queue. This
  also resolves the "closing the drawer mid-evaluation loses progress" problem, since the
  drawer no longer owns the stream.

## Impact

- Affected specs: `agent-move-evaluation` (new cross-game request listing), `game-history-ui`
  (persistent queue UI + enqueue-and-watch submit flow).
- Affected code: `services/eval-service/` (api/routers/evaluations.py, repository, schemas);
  `services/dashboard/features/history/` (new queue components + `useEvaluationQueue`, an
  `listEvaluations` eval-api fn, the proxy allowlist for `eval/evaluations`, workspace header,
  Evaluate drawer refactor); `services/dashboard/features/proxy` if the path allowlist needs it.
- Sequencing: builds ON TOP of `history-play-style-browser` (both touch the History header +
  Evaluate drawer); implement after that change lands to avoid conflicts.
- Constraint: the queue is derived from eval-service Postgres via the polled list endpoint —
  no state is stored in memory in any service or duplicated client-side beyond view cache.
