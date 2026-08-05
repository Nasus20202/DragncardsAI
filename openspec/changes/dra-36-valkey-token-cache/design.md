## Context

`SessionManager` bootstraps every DragnCards room with three HTTP calls in
sequence — `get_auth_token`, `get_user_id`, `create_room` — then a WebSocket
connect, a channel join, and an auto-seat round trip. Measured against the
running stack, the two credential calls account for ~305 ms of a ~590 ms
`POST /games`, and `POST /games/{id}/restore` with `ephemeral=true` totals
~728 ms.

The game-service already talks to Valkey: `ValkeySessionStore` and
`ValkeyHistoryEmitter` both drive a per-command RESP client (`_RespConnection`
in `coordination/session_store.py`) that opens a fresh TCP connection per
command. `history_emitter.py` already imports that class across module
boundaries, so a third consumer needs no new plumbing.

The agent-orchestrator solved the same problem for Bifrost model listings in
`integrations/bifrost.py`: `GET`/`SETEX` against a namespaced key, JSON payload,
and a broad `except Exception` around each command that logs a warning and
returns `None` so the caller falls through to a live fetch. That shape is the
precedent this change follows.

## Goals / Non-Goals

**Goals:**
- Stop re-authenticating against DragnCards on every room creation.
- Keep the cache out of process memory, in line with the repository Data Storage
  rule.
- Make a Valkey outage invisible to callers: slower, never broken.
- Keep the token out of logs, spans, error messages, and documentation.
- Reuse an already-open ephemeral room for a second moment of the same game,
  without ever showing a stale board.

**Non-Goals:**
- Caching room, plugin, or game state.
- Pooling ephemeral rooms across clients.
- Modifying `services/shared/src/dragncards_common/resp.py`.
- Changing the ephemeral TTL reaper.

## Decisions

### D1: Cache the token and the user id together, as one entry

**Decision**: One Valkey key holds `{"token": ..., "user_id": ...}`.

**Why**: `get_user_id` exists only to turn a token into the numeric id that
`create_room` and auto-seat need. It is a pure function of the token, so a
cached token whose id was discarded would still force a ~65 ms call. Caching
them together removes both round trips and makes them impossible to get out of
step: the id always belongs to the token stored beside it.

**Alternatives considered**:
- Two keys, one per value: they can expire independently, leaving a token with no
  id (a wasted call) or an id with no token (a correctness trap if the account
  ever changed). Rejected.
- Cache only the token: leaves ~65 ms of the ~305 ms on the table for no
  simplification. Rejected.

### D2: TTL of 900 s, against a verified 30-minute token lifetime

**Decision**: `DRAGNCARDS_AUTH_CACHE_TTL_SECONDS`, default `900` (15 minutes).
`0` disables the cache.

**Why**: The lifetime is known, not guessed. DragnCards issues the token through
`DragnCardsWeb.APIAuthPlug.create/3`, which stores it in
`Pow.Store.CredentialsCache`. In pow 1.0.27 that store is declared with
`ttl: :timer.minutes(30)` (`deps/pow/lib/pow/store/credentials_cache.ex`), and
DragnCards' `config :dragncards, :pow` block sets `user`, `repo`, `extensions`,
`controller_callbacks`, `mailer_backend` and `cache_store_backend` but no `:ttl`,
so the default stands. `APIAuthPlug.fetch/2` reads the store without rewriting the
entry, so the 30 minutes run from issue and are not extended by use.

15 minutes is half that. An entry read at the last instant before it expires still
carries at least 15 minutes of validity, which is ample for the one room creation
that follows. A shorter TTL would give back the saving for no safety gain; a
longer one would narrow the margin without removing another round trip, because
one cached token already serves every room created in its window.

`0` matching the model cache's convention means the cache can be switched off in
one variable if a DragnCards deployment ever shortens the lifetime, without a
code change.

**Alternatives considered**:
- Reading a TTL back from DragnCards: no endpoint reports it, and the value is
  compile-time in the upstream dependency. Rejected.
- 25 minutes (close to the lifetime): leaves ~5 minutes of margin and depends on
  the upstream default never shrinking. Rejected as too tight for a ~300 ms saving.
- No TTL, evict only when a credential is found not to work: an entry would
  outlive the token, so the failure path (D3) would become the normal path — a
  dead room whenever the 30 minutes lapsed. Rejected.

### D3: Evict a cached credential when the room channel refuses the join

**Decision**: The Channel records a `room_unavailable` push. When a join is
refused and the credential came from the cache, `SessionManager` evicts the entry.
It does not retry and does not fail the caller.

**Why the join and not an HTTP status**: there is no HTTP status to hook. Measured
against the running backend, `POST /api/v1/games` with a garbage token answers
`201` and creates the room — the route is not behind the authenticated pipeline
upstream. `GET /api/v1/profile` does answer `401`, but the cache exists precisely
to stop calling it. The socket is likewise accepted with an unusable token
(`UserSocket.connect/2` assigns `user_id: nil, auth_failed: true` and still
returns `{:ok, socket}`); the room channel then answers `after_join` with
`room_unavailable` instead of a state. That push is the only observable place the
credential is judged.

**Why evict at all**: the TTL is a prediction about someone else's configuration,
and one cause is routine here — the DragnCards container's Pow credential store
lives in the container filesystem, so recreating it forgets every issued token
while a cached entry still looks fresh. Without eviction, every room creation for
the rest of the TTL would produce a silently dead session.

**Why only a cached credential**: `room_unavailable` also fires for a room with no
server state, so a refusal is not proof the credential is at fault. Evicting one
that was just derived would re-derive the identical value and prove nothing.

**Why no retry and no raise**: a refused join already produces a session that
fetches state on demand — that is pre-existing behaviour, unchanged. Raising
instead would strand the DragnCards room just created, because the same refusal
means the channel rejects every push, including the one that closes a room.
Making that path fail cleanly is a real improvement but a separate concern from
caching a credential, and coupling them would mean this change could leak a room.

**Alternatives considered**:
- Retry the whole bootstrap with a fresh credential: creates a second room per
  failure and cannot distinguish an auth refusal from a stateless room, so it
  doubles room creation on an unrelated fault. Rejected.
- Probe the token with `GET /api/v1/profile` before using it: that is the ~65 ms
  call the cache exists to remove. Rejected.
- Trust the TTL and evict nothing: makes recreating the DragnCards container break
  room creation for 15 minutes, which the cache would have caused. Rejected.

### D3a: Register the Channel before awaiting the join reply

**Decision**: `PhoenixClient.join` puts the Channel in `_channels` before the
`phx_join` reply is awaited, and removes it again if the join fails.

**Why**: without it, D3 cannot be observed. The receive loop is its own task, so
after the reply future resolves it keeps draining the socket while `join()` waits
to be rescheduled — and `_dispatch` silently drops a message whose topic is not
yet in `_channels`. Measured: a handler registered immediately after `join()`
returned saw no `room_unavailable` at all, while a probe hooked into `_dispatch`
saw it every time. The same window swallows the `current_state` the join itself
triggers, so this is a latent message-loss bug independent of the credential
cache.

**Alternatives considered**:
- Queue `room_unavailable` alongside state events so `wait_for_event` can see it:
  the existing `wait_for_state_update` puts non-matching messages back and
  re-reads them, so a queued refusal would spin until the timeout. Rejected.
- Poll for the flag after joining with a short delay: replaces a dropped message
  with a guess about how long the drop lasts. Rejected.

### D4: Key on the backend URL and the account, hashed

**Decision**: `game-service:dragncards-auth:<sha256(url + "\0" + email)[:32]>`.

**Why**: Namespacing under `game-service:` matches `game-service:session:` and
avoids collision with anything else on the instance. Including the URL and the
account means pointing the service at a different backend, or changing
`BOT_EMAIL`, cannot serve a token minted for the other one — the key simply
misses. The parts are hashed because the key name is the one part of a cache
entry that shows up in operational tooling (`KEYS`, slow logs, dashboards), and an
account address does not need to be there for the cache to work.

**Alternatives considered**:
- A single fixed key: a URL or account change would serve a token for the wrong
  backend until the TTL expired. Rejected.
- The email in clear text in the key: readable, but publishes the bot account to
  anything that lists keys, for no functional gain. Rejected.

### D5: The token lives in the value; nothing else may carry it

**Decision**: The token appears only as part of the JSON value written by
`SETEX` and the `authorization` header of DragnCards requests. Cache
diagnostics log the key and the command, never the value. No span attribute
carries it. The refusal this change does surface names the room and whether the
credential was cached, never the credential itself or an upstream response body.

**Why**: Caching a credential moves it into a store other subsystems read, so the
places it could leak from multiply. The game-service's RESP client already only
records `parts[0]` as `db.operation.name`, so command arguments never reach a
span — which is why `SETEX` is safe to trace and why that property has to stay
true. Errors are the usual leak: an upstream 401 body echoed into an exception
message ends up in logs and, from there, in traces.

**Alternatives considered**:
- Encrypting the cached value: the key material would have to live beside it, and
  Valkey is already an internal-only store holding session records. Adds a moving
  part without changing who can read it. Rejected.
- Logging a truncated token prefix to aid debugging: a prefix is still credential
  material and the key plus the command already identify the entry. Rejected.

### D6: Reuse an ephemeral room only when a full-state base is loaded

**Decision**: `POST /games/{game_id}/restore` accepts `reuse_session_id`. It is
honoured only when `mode="new"` **and** the restore is `ephemeral` **and** a
snapshot or recorded state event at or before the target exists. Otherwise the
restore creates a room as before, and the caller's session is left untouched.

**Why**: The gate is what makes reuse provably correct rather than probably
correct. `_load_base` sends DragnCards `set_game`, and
`GameUI.resolve_action_type/4` implements `set_game` as
`options["game"]` — the prior game is discarded, not merged, so the loaded
document is the entire result and no card, token, or counter can survive. Measured
on the running stack: a room loaded with the seq-25 base and then re-pointed at the
seq-107 base exported a `game` document with sha256
`35ac59133e34b9e39db7c415f0b858969c06ce800bce5a1508cbd1318404f208`, identical to a
freshly created room loaded with seq-107 and to the seq-107 document itself.

The no-base path has no such guarantee: it replays forward from seq 0 onto
whatever the room currently holds. In a fresh room that is a new game; in a reused
room it is the previous view. Rather than reason about which replays are total,
the gate excludes the path outright.

The `ephemeral` condition is a separate concern from correctness: it keeps the
field aimed at the flow it exists for. Reuse overwrites a session the caller
names rather than one the restore created, so without it the field would let a
caller replace an unrelated live session's board with a different game's — an
authority the existing routes do not grant (`mode="in_place"` can only rewind a
session to a moment of its own game). An ephemeral reconstruction is by
definition a throwaway the caller built in order to look at it, and a kept branch
restore's whole product is the room it creates.

`created_new_session` already governs rollback, so a reused session is not deleted
when a restore fails — which is correct, because the caller owns it.

**Alternatives considered**:
- Reusing unconditionally and resetting the room first: `reset_game` reloads the
  plugin, costing more than the room creation being avoided. Rejected.
- A server-side pool of idle ephemeral rooms in game-service: the service that
  creates the room does not know whether the caller will load a full base into it,
  so the safety gate cannot be expressed there. Rejected.
- Letting the dashboard load the base itself and skip restore: duplicates the
  forward-replay and verification logic that restore owns. Rejected.

### D7: The dashboard keeps the session, not the view, across moments

**Decision**: Changing the selected moment clears the displayed reconstruction
but retains the session id and room slug for reuse. Explicit close, game switch,
unmount, and `pagehide` dispose the session as they do today.

**Why**: The rendered header is labelled with the moment the board was built
from, so leaving a board on screen while the selection moves would make the label
lie. Clearing the view and keeping the session separates the two concerns: the
user still re-opens deliberately, and the re-open is the fast path.

The cost is that a retained session holds its room until the user opens another
moment, closes the panel, or leaves. That is the case the TTL reaper already
exists for, and it is bounded to one room per client.

**Alternatives considered**:
- Auto-reloading the board when the selection changes: turns scrubbing a timeline
  into a room mutation per step. Rejected.
- Keeping the previous board rendered until the new one loads: shows a board under
  a header naming a different moment. Rejected as the exact staleness this change
  is supposed to avoid.

## Risks / Trade-offs

- **The cached token is a credential in a shared store.** Valkey already holds
  game-service session records and is not exposed outside the Docker network, but
  the entry is readable by anything that can reach the instance.
  → Mitigation: TTL well under the token's lifetime, so a leaked entry is
  short-lived; the token never appears in a log, span, error, or document; the key
  does not name the account.

- **Valkey transport errors happen here.** DRA-35 tracks `ConnectionResetError`
  from the shared RESP client, and the game-service client opens a new TCP
  connection per command, so a refused or reset connection is a live possibility.
  → Mitigation: every cache command is wrapped; a failure logs and returns as a
  miss, and the caller authenticates live. Covered by a unit test that raises from
  the connection on both read and write.

- **A credential can stop working before its cached TTL elapses.** The 30-minute
  Pow default is upstream configuration this repository does not control, and
  recreating the DragnCards container forgets every issued token outright.
  → Mitigation: D3 evicts the entry on the refused join, so the damage is bounded
  to the one room that hit it rather than every room for the rest of the TTL, and
  `DRAGNCARDS_AUTH_CACHE_TTL_SECONDS=0` disables the cache without a deploy. Not
  fully mitigated: that one room still yields a session with no state, which is
  what a refused join has always produced.

- **A reused room accumulates DragnCards replay deltas.** `add_delta/2` appends a
  delta per `set_game`, and those live in `gameui["deltas"]`, outside the `game`
  document. A reused room therefore has a longer undo history than a fresh one,
  and each entry is a diff between two full boards.
  → Mitigation: the board itself is unaffected (the sha256 comparison covers the
  whole `game` document), reuse is bounded by the ephemeral TTL, and one client
  holds at most one room. Recorded history is untouched because ephemeral sessions
  emit no events.

- **A retained session holds a room longer than today.** Before this change, moving
  the selection freed the room immediately.
  → Mitigation: the dashboard disposes on close, game switch, unmount, and page
  hide; the reaper reclaims anything those miss.

## Migration Plan

1. Add `auth_cache.py`, and make the Phoenix client record a refused room and
   register its Channel before the join reply; no caller behaviour changes yet.
2. Route `SessionManager` credential resolution through the cache; construct it in
   `main.py` from the existing session-store Valkey URL. With no Valkey passed
   (unit tests, `GAME_SERVICE_USE_IN_MEMORY_SESSION_STORE`) the cache is inert and
   behaviour is exactly as before.
3. Add config to `docker-compose.yaml`, `.env.example`, and the game-service
   README and AGENTS guide.
4. Add `reuse_session_id` to the restore request and honour it under the D6 gate.
5. Teach the dashboard's board reconstruction to retain and reuse its session.

No data migration: the cache is empty on first boot and the first room creation of
each TTL window authenticates live and populates it.

**Rollback**: `DRAGNCARDS_AUTH_CACHE_TTL_SECONDS=0` restores per-room
authentication with no code change. Reverting step 4 or 5 independently is safe —
a `reuse_session_id` the history-service does not recognise is ignored, and a
dashboard that never sends the field gets today's behaviour.

## Open Questions

None. The token lifetime was read from the pinned upstream dependency and the
reuse guarantee was measured on the running stack; both are recorded above.
