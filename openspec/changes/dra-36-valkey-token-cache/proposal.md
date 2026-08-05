## Why

Opening the dashboard's "board at this event" view is slow, and DRA-28 established
that payload size is not the reason: it cut the plugin-slug read from 1,347,305 B
to ~245 KB and the replay range from 219,476 B to 0 on the common path, and the
click stayed about as slow. The cost is round trips, measured on the running
stack against a 124-event game:

| step | measured |
| --- | --- |
| `POST /api/v1/session` (DragnCards authentication) | ~240 ms |
| `GET /api/v1/profile` (numeric user id) | ~65 ms |
| `POST /api/v1/games` (create the room) | ~212 ms |
| channel connect + join + initial state + auto-seat | ~73 ms |
| **`POST /games` total** | **~590 ms** |
| **`POST /games/{id}/restore` (ephemeral) total** | **~728 ms** |

Two of those are avoidable.

**Authentication is repeated per room.** `SessionManager` calls
`get_auth_token` + `get_user_id` on every `create_session`, `attach_session` and
`_restore_session`. That is ~305 ms — over half of `POST /games` — spent
re-deriving a credential that DragnCards keeps valid for 30 minutes. The
authentication call is expensive because it verifies a password hash, not because
it transfers anything. An in-process cache is forbidden by the repository's
Data Storage rule, so the cache belongs in Valkey, following the
`agent-orchestrator` model cache (`agent-orchestrator:model-cache:all`).

**Ephemeral rooms are rebuilt rather than reused.** Viewing a second moment of
the same game creates a whole second DragnCards room, paying room creation and
channel setup again, when the room the viewer already has open can simply be
re-pointed at the new moment. Loading a full-state base into an already-open room
was measured at **~55 ms**, against ~728 ms to build a new one.

Reuse is only safe if the reused room is left in exactly the target state. It is:
the DragnCards `set_game` action returns `options["game"]` outright
(`external/dragncards/backend/lib/dragncards_game/ui/game_ui.ex`,
`resolve_action_type/4`), discarding the prior game, so the loaded document is the
whole result. Measured on the running stack, a room that had a different moment
loaded into it and was then re-pointed at the target produced a `game` document
with the **same sha256** as a freshly created room loaded with the same target,
and as the source document itself. Reuse is therefore restricted to the path where
a full-state base is loaded; a restore with no base replays onto whatever is
already there and never reuses a room.

## What Changes

- Add `DragnCardsAuthCache`: a Valkey-backed cache of the bot's DragnCards
  session token and numeric user id, keyed per backend URL + account, with a TTL
  shorter than the token's own 30-minute lifetime.
- `SessionManager` resolves credentials through the cache instead of
  authenticating directly, in all three places that need them.
- A cached credential the DragnCards backend no longer recognises is evicted, so
  the next room derives a new one instead of repeating the failure for the rest of
  the TTL. The detection point is the room channel join, because that is the only
  place the credential is actually checked: `POST /api/v1/games` is not behind the
  authenticated pipeline upstream and answers `201` for any token, so there is no
  HTTP rejection to hook. A join the backend will not serve answers
  `room_unavailable` instead of a state.
- `PhoenixClient.join` registers its Channel before awaiting the join reply. The
  receive loop is a separate task, so a channel registered only afterwards can miss
  the room's opening broadcasts entirely — including the `current_state` the join
  itself triggers — and `_dispatch` drops a message for a topic it does not yet
  know without a trace.
- A Valkey miss, outage, or transport error degrades to a live authentication and
  never fails the request, matching the model cache's behaviour.
- The cached token is never logged, never attached to a span, never placed in an
  error message, and never written to a spec or README example.
- New config `DRAGNCARDS_AUTH_CACHE_TTL_SECONDS` (default `900`); `0` disables
  the cache and restores per-room authentication.
- `POST /games/{game_id}/restore` accepts `reuse_session_id`. With an
  `ephemeral` `mode="new"` restore and a full-state base available, it loads that
  base into the named existing session instead of creating a room. Without a
  base, for a kept branch restore, or without the field, it creates a room exactly
  as before.
- The dashboard's board reconstruction keeps its ephemeral session alive when only
  the selected moment changes, and re-points it at the new moment. It still
  disposes the session on explicit close, game switch, unmount, and page unload —
  the `pagehide` event, per design D7. A tab merely becoming hidden is not a
  disposal.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `game-service`: DragnCards credentials are resolved through a shared Valkey
  cache rather than re-authenticated per room; cache failure degrades to a live
  authentication.
- `dragncards`: the integration contract records the credential's lifetime and
  that a token is reusable across room creations until it expires.
- `history-event-store`: an ephemeral `mode="new"` restore can target an existing
  session instead of creating one, gated on a full-state base being loaded.
- `game-history-ui`: the board reconstruction reuses its live ephemeral session
  across moments of the same game.

## Non-goals

- Caching anything other than the token and user id. Room state, plugin
  metadata, and game state are untouched.
- Sharing one ephemeral room between concurrent viewers. A reconstruction session
  stays owned by the one client that created it.
- Changing the ephemeral TTL reaper, which remains the safety net for a session
  a client never disposes.
- Replacing `services/shared/src/dragncards_common/resp.py` or changing how
  game-service connects to Valkey. The existing per-command RESP client is used
  as-is.
- Reusing rooms for non-ephemeral (kept) sessions, or for `mode="in_place"`
  restores, both of which own their rooms for reasons unrelated to speed.

## Impact

- `services/game-service/src/game_service/dragncards/auth_cache.py` — new module.
- `services/game-service/src/game_service/phoenix_client/client.py` — record a
  refused room on the Channel, and register the Channel before the join reply.
- `services/game-service/src/game_service/logic/session_manager.py` — resolve
  credentials through the cache, and evict a cached one on a refused join.
- `services/game-service/src/game_service/main.py` — construct the cache and read
  `DRAGNCARDS_AUTH_CACHE_TTL_SECONDS`.
- `services/history-service/src/history_service/schemas/api.py`,
  `runtime/restore.py` — `reuse_session_id`.
- `services/dashboard/features/history/lib/use-board-reconstruction.ts`,
  `features/history/lib/history-api.ts` — reuse the live session across moments.
- `docker-compose.yaml`, `.env.example`, `services/game-service/README.md`,
  `services/game-service/AGENTS.md` — the new config key.
- Unit tests in game-service, history-service and dashboard; game-service
  integration tests for the cached-credential path.
