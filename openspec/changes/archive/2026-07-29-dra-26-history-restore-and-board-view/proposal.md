# Make the three history restore actions work and say what they do

## Why

Two issues report the same surface — the per-event **Actions** menu in the dashboard's
History transcript — from two directions. DRA-26 reports three defects in what the actions
*do*; DRA-28 reports that the surface is slow and that it is unclear how it works. They are
one change because DRA-26's third bullet is DRA-28's subject.

DRA-26 reports, verbatim:

> - In place override fails with error 404 — it should overwrite the current game with the
>   old state.
> - New branch-able session don't create a new game in Dragncards — it should create a new
>   game, with new history, based on this point.
> - Open board at this event — should not overwrite the current game state, but create a
>   new, temporary game, only to show the board.

DRA-28 reports, verbatim:

> Improve viewing board state at time. Currently it's slow and unclear how it works.

Each of the three was established against the running stack before anything was changed.
One is a real bug with a findable cause, one is a reporting-and-discoverability failure
that makes working behaviour look broken, and one is a false premise about the server that
is nonetheless a real problem in the UI.

### 1. The 404 is real, and it comes from agent-orchestrator

An in-place restore rebuilds two layers: the game state, and the agent's conversation
context. The second layer calls agent-orchestrator `POST /sessions/restore` with
`mode="in_place"`, which resolves the agent session to resume via
`get_active_session_by_game_id` — a query that requires `status == "active"`
(`services/agent-orchestrator/src/agent_orchestrator/repositories/sessions.py:162-178`).
When no active session is bound to the game it answers `404`
(`api/routers/sessions.py:123-128`). Reproduced directly against the running stack:

```
POST http://localhost:4002/sessions/restore
{"game_id":"<a recorded game>","conversation_context":[],"mode":"in_place"}
→ 404 {"detail":"No active session bound to the supplied game_id"}
```

That is not an edge case, it is the normal state of anything worth restoring. On the
running stack 17 of 21 orchestrator sessions were `terminated` and only one carried a
`game_id` at all; the game with the richest history (124 events, 56 of them `agent_move`)
had no active session bound to it. A game is browsed in history precisely *after* the agent
that played it has finished.

history-service called `raise_for_status()` on that response
(`integrations/orchestrator.py:32`), and the broad `except Exception` in `_restore`
converted it into a `RestoreError` reported to the user as a failed restore. Two things
were wrong with that beyond the wording:

- **The rewind had already happened.** The agent-context layer runs *after* the base state
  is loaded and the events replayed onto the live session. `created_new_session` is false
  for an in-place restore, so there is nothing to roll back to. The live game was rewound
  and the user was told the restore failed.
- **The message named neither the service nor the cause.** It surfaced as a bare "404",
  which reads like a missing route in the endpoint that was called.

A second, independent `404` exists on the same path: the base load is
`PUT /games/{game_id}/snapshot` against game-service, which answers `404` when the original
DragnCards room no longer exists. On the running stack that was every recorded game — zero
live sessions for 46 recorded games. It surfaced with the same opaque wording.

### 2. Branch mode does create a new game; nothing tells the user where it is

The literal premise of the second bullet is **false**, and the evidence says so. A
`mode="new"` restore of a recorded game returned:

```
{"status":"restored","mode":"new",
 "game_session_id":"faaadaf0-15e9-47b9-abb0-342a5a7cf297", ...}
```

game-service then listed that session with room `starry-liquid-8190`, its board populated
at the target moment (step `1.1` against the original's `1.2`), and history-service listed
it as a recorded game with its own event log. A new DragnCards game with new history is
exactly what was created.

What is missing is any way to *reach* it. The only feedback was
`Restored into session faaadaf0-15e9-47b9-abb0-342a5a7cf297.` — a bare UUID, with no room
slug, no link, and no navigation. The room slug was available all along: game-service
returns it on the same `POST /games` response that assigns the session id, and
`GameServiceClient.create_session` discarded it. A created game that cannot be found is
indistinguishable from one that was never created, which is what the issue reports.

### 3. Opening a board does not overwrite anything — verified byte-for-byte

The third premise is **false at the server**, and this was tested rather than reasoned
about. The original game's state was captured, an "open board" restore was run against it,
and the state was captured again:

```
sha256 before: 1ce91c8285bde6c6849768991d56c1c99ee1f255082973969a30909d2df3013a
sha256 after:  1ce91c8285bde6c6849768991d56c1c99ee1f255082973969a30909d2df3013a
```

Byte-identical. The reconstruction was created as a separate session flagged
`ephemeral=true`, and it emitted no history (`/timeline` for it returns an empty list). The
client always sends `mode: "new", ephemeral: true`
(`features/history/lib/use-board-reconstruction.ts:147-151`), and ephemeral sessions are
suppressed from emitting at `services/game-service/src/game_service/logic/session.py:275`.

So there is no data-loss bug to fix here. There *is* a real problem, and it is the one
DRA-28 names: nothing in the UI said so. Opening a board replaced the entire transcript
panel with an unfamiliar DragnCards room
(`features/history/components/history-workspace.tsx:438-443`), with a header reading only
"Board at event #N" and no statement that it is a throwaway copy. A user cannot tell a
sandbox from their real game by looking at it, and the reasonable conclusion from a board
appearing where your history used to be is that something was overwritten. Reporting this
as a data-loss bug is the predictable result of a destructive-looking read-only action.

### Slow: measured, and the dominant cost is not the payloads

DRA-17 established a precedent for oversized history payloads, so that was the first
hypothesis. It is not the main answer here. Measured against the running stack on a
124-event game (each probe repeated, agreeing to the byte):

| what | measured |
| --- | --- |
| `GET /games` used only to resolve one room slug | **235 B**, 1.4–2.1 ms |
| snapshot document fetched on every restore | **244,884 B**, entirely discarded when a state event wins |
| all snapshot documents, fetched to read one plugin slug | **1,347,305 B** across 6 documents |
| replay range, state-event base, target 124 | **219,476 B**, every row skipped in Python |
| replay range, snapshot base, 18-event span | **5,168,160 B** |
| replay range, no base, 124 events | **27,917,633 B**, 0.66 s |
| one HTTP round trip to the DragnCards backend, empty 401 body | **65 ms** |

The payload waste is real and worth removing, but it is not what makes the click feel slow.
Creating the room is: `POST /games` fans out sequentially inside game-service to
authenticate, read the profile, create the room, open a WebSocket, join the Phoenix channel,
wait for DragnCards to load the Marvel Champions plugin (a 15 s budget), and auto-seat
(`logic/session_manager.py:285-335`). That is five or more sequential external round trips
against a **measured 65 ms floor**, plus a channel join and a plugin load — seconds, and one
to two orders of magnitude above every payload cost in the table.

Two aggravating details in that fan-out: `get_auth_token` and `get_user_id` each construct a
throwaway `httpx.AsyncClient` and re-authenticate from scratch on every single room
creation, with no token cache anywhere
(`services/game-service/src/game_service/dragncards/http_client.py:15-39`).

This change removes the payload waste it can remove cheaply and honestly, and does **not**
attempt the room-creation fix — see *Deliberately not in this change*, which says why and
what it would take.

## What Changes

### An in-place rewind is no longer failed by a missing agent session

`_restore_agent_context` now returns a `(session_id, note)` pair and treats a `404` from
agent-orchestrator as what it is: there is no agent session to resume. It logs, reports, and
lets the completed game-state restore stand. Any other status still propagates — a `500` is
a genuine fault and must not be swallowed.

The result carries `agent_context_restored` and `agent_context_note`, so a caller can say
"the board was restored, the agent conversation was not, and here is why" instead of
choosing between a silent partial success and a false failure.

### A deleted live session is reported as such, not as a 404

The base load is wrapped: for `mode="in_place"`, a `404` from
`PUT /games/{id}/snapshot` becomes

> cannot rewind game '…' in place: its live game-service session no longer exists, so there
> is no game state to overwrite. Restore into a new branchable session instead.

This is the first mutating call of a restore, so failing here has changed nothing — the
message is safe to act on.

### An in-place rewind no longer requires a periodic snapshot

An in-place rewind rejected any target with no snapshot at or before it, because a snapshot
was treated as the only way to establish a clean base. But a `game_state` event embeds a
complete board and is *denser* than the snapshot cadence — the branch path already preferred
it. The base is now resolved once, identically for both modes, by `_choose_base`.

This matters in practice: snapshots land every 16 events, and a freshly recorded 9-event
game had none, so every in-place restore of it was rejected outright with

> no snapshot at or before the target exists to establish a clean base

Rejection is still correct when there is **no** full-state base of either kind — replaying
onto an un-rewound live session would double-apply every event — and the message now names
what is actually missing.

### A branch restore names the room it created, and the dashboard links to it

`GameServiceClient.create_session` returns a `BranchSession(session_id, room_slug)` instead
of dropping the slug that `POST /games` already returned. `RestoreResult` and
`RestoreResponse` carry `room_slug`, and the dashboard renders an **Open the new game ↗**
link. The user gets a room they can open, not a UUID.

This also removes the reason the board hook called `listGames()`: the slug is on the restore
response. The saving is small (235 B, ~2 ms measured) and is not the point — the point is
that the fallback searched a list of *all* sessions by id and raced the ephemeral reaper, so
a reaped-in-between session silently rendered a fallback iframe with no error shown. The
list is kept strictly as a fallback for a history-service that returns no slug.

### The replay range is narrowed in the database

`get_events_in_range` takes an optional `actor`, and restore passes `"game-service"`. Only
those events are ever replayed as mutations and only they carry the status the verification
step compares against, so the rows were always going to be filtered — previously in Python,
after transferring and JSON-parsing every discarded payload.

**What this saves, stated precisely**, because the obvious reading of the table above
overstates it. The filter keeps the `game-service` rows and drops the `agent`/`evaluator`
ones — and it is the `game_state` payloads that carry the ~430 KB boards. So it does *not*
turn the 27.9 MB span into nothing; roughly 26 MB of that span is `game-service` rows, which
the replay needs. What it removes there is the ~2 MB remainder.

Where it eliminates the read outright is the common path, and that is the real win: when the
base is the nearest `game_state` event, that event is by construction the last `game-service`
event at or before the target, so the range `(base.seq, target]` contains no `game-service`
events at all. Measured, that range was **219,476 B** of agent payloads fetched, parsed, and
skipped one at a time; filtered, it returns nothing.

There is no `(game_id, actor, seq)` index, so the planner range-scans `ix_events_game_seq` and
rechecks `actor`. The saving is in detoasting, transfer, and JSON parsing, not index I/O. An
index is not warranted at current row counts.

### The plugin slug is read without loading every snapshot document

`_resolve_plugin_name`'s fallback passes `limit=1`. It only ever consumed the first row, and
every snapshot row carries a full board, so the unbounded read transferred and parsed every
snapshot of the game to extract one short string. Measured saving: 1,347,305 B → ~245 KB.

### Each action states its effect, and destructive is distinguishable from read-only

All three actions sit in one ~288px popover. They now differ from each other before they are
clicked, and the read-only one comes first because it is the cheapest and most common thing
a user wants:

- **Look at it** — `Read-only` chip. "Opens a throwaway copy of the board as it was at this
  moment, to click around in. This game is not changed, and the copy is discarded when you
  close it."
- **Into a new game** — `Safe` chip. "Creates a separate DragnCards game with its own
  history, starting from this moment. This game is not changed."
- **Over this game** — `Destructive` chip. "Rewinds the live game itself to this moment.
  Everything played after it is gone."

The submit button names the action (**Create the new game** / **Rewind this game**) rather
than saying only "Restore". The popover widens from `w-72` to `w-80` to fit this.

The confirmation label was also inverted and is fixed: the button opened reading "Confirm
overwrite" and changed to the action name after the first click, so its scariest wording
appeared before the user had asked for anything. It now names the action first and becomes
"Confirm overwrite" only once armed.

### The reconstructed board says it is a throwaway copy

`BoardView` carries a `Temporary copy` chip and, under the header, "A throwaway copy for
looking around. Nothing you do here affects the recorded game, and it is discarded when you
close this." This is the one sentence whose absence produced DRA-26's third bullet.

While a board is opening, the button reads "Building the board…" over a note explaining that
a temporary DragnCards room is being created and that it takes a few seconds. The dominant
cost is not removed by this change, so the wait is explained rather than left blank —
`isOpening` previously rendered a bare spinner for a multi-second, entirely unexplained wait.

## Impact

- **`history-service`** — `runtime/restore.py` (base resolution unified across modes,
  `_choose_base`, `_load_base`, tolerant agent-context layer, `room_slug`),
  `integrations/game_service.py` (`BranchSession`), `storage/repository.py`
  (`get_events_in_range(actor=…)`), `schemas/api.py` and `api/routers/restore.py` (three new
  response fields). All additive on the wire: no field removed, no field's meaning changed.
- **`dashboard`** — `features/history/components/restore-control.tsx`, `board-control.tsx`,
  `history-transcript.tsx` (control order, popover width, `frontendUrl` on the room-context
  bundle), `history-workspace.tsx`, `lib/use-board-reconstruction.ts`,
  `features/shared/lib/types.ts`.
- **`agent-orchestrator`** — unchanged. Its `404` is a correct answer to "resume the session
  bound to this game" when none is bound; the defect was history-service treating a correct
  answer as a fault.
- **Ancillary files** — `services/history-service/README.md` documents the restore response's
  new fields and the tolerated `404`. No change is needed to `docker-compose.yaml`,
  `.env.example`, OTel configuration, `scripts/`, or the Swagger index: no service, port,
  environment variable, or endpoint was added or renamed, and the restore route's OpenAPI
  schema (and therefore its MCP tool) regenerates from the response model.
- **Compatibility** — a dashboard reading an older history-service still works (`room_slug`
  absent falls back to the session list; the two agent-context fields default to
  `false`/`null`).

## Deliberately not in this change

**Room creation is the dominant cost and is not fixed here.** The measurements are above;
the click stays about as slow as it was. Two fixes were identified, and each is a change in
its own right rather than something to bolt onto a bug fix:

- **Cache the DragnCards auth token.** `get_auth_token` and `get_user_id` re-authenticate on
  every room creation, so roughly two of the five-plus external round trips (~130 ms at the
  measured floor) plus a server-side password hash are pure repeat work. The obvious
  implementation — a module-level token cache — is forbidden by this repository's rule that
  services must not hold state in memory, so it belongs in Valkey alongside the existing
  session store. That is a correctness-sensitive piece of work (expiry, invalidation on a
  401, sharing across replicas) and it is not this issue.
- **Reuse an ephemeral reconstruction instead of recreating one.** Opening the board at a
  different moment currently disposes the room and builds a new one, paying the full cost
  every time. Loading the new state into the existing ephemeral room would turn every board
  view after the first into a single `PUT` (~50–200 ms). It needs a restore that can target
  an existing session, which needs a `GET /games/{session_id}` on game-service (there is
  none) and a guard restricting the target to ephemeral sessions — otherwise it becomes a way
  to overwrite an arbitrary game.

Four smaller measured items are also left alone, so the numbers are not mistaken for a claim
of completeness:

- **The snapshot document is still fetched on every restore** and discarded whenever a state
  event wins (244,884 B). The fix is to resolve the state-event base *first* — every
  `game_state` payload carries the `plugin_name`, so the snapshot read becomes a fallback
  rather than a precondition — which would also remove the `get_earliest_state_event` read
  (another ~430 KB) from the plugin-slug chain. It is a further reordering of the same
  function and wants its own change; against a multi-second room creation it buys little.
- **An in-place rewind now reads more than it did**: it prefers the dense state event, so it
  pays ~430 KB for that plus the ~245 KB snapshot it no longer uses, where before it read the
  245 KB snapshot and used it. That is a deliberate trade, not an oversight — the dense base
  collapses the replay range to empty, removing up to dozens of *sequential HTTP round trips*
  at a measured 65 ms floor each, which dominates local read volume by orders of magnitude.
- **`replay_events` is held to the end of the workflow** solely so `_verify_status` can rescan
  it. On the common path it is empty, so this costs nothing today; on a long snapshot-base
  span it retains every full row. The expected status is available from the base event already
  in hand.
- **`get_latest_state_event_at_or_before` filters on `actor` alone** rather than also requiring
  the row to carry a `state`, so an unusable row silently degrades to the snapshot or full-log
  path instead of saying so.
