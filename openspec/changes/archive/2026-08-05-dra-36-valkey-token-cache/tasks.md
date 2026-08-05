## 1. Baseline measurement

- [x] 1.1 Measure `POST /api/v1/session`, `GET /api/v1/profile` and `POST /api/v1/games` against the running DragnCards backend, several samples each, and record the per-call cost
- [x] 1.2 Measure `POST /games` (game-service, ephemeral) and `POST /games/{id}/restore` (history-service, `mode="new"`, `ephemeral=true`) several times each, and record the wall-clock totals and the round-trip count per room creation
- [x] 1.3 Read the DragnCards token lifetime out of the pinned upstream (`pow` credentials cache TTL plus any `config :dragncards, :pow` override) and record the value the cache TTL is chosen against
- [x] 1.4 Delete every session and room created while measuring, and confirm both `GET /games` and the DragnCards room list are empty

## 2. Detecting a credential the backend has forgotten

- [x] 2.1 Establish where a DragnCards credential is actually validated on the room path, and record the finding: `POST /api/v1/games` is NOT behind the authenticated pipeline upstream and returns `201` for an invalid token, so there is no HTTP `401` to hook
- [x] 2.2 Confirm at the wire that a socket bearing an unusable token is accepted and the room channel answers the join with `room_unavailable` instead of a state
- [x] 2.3 Record `room_unavailable` on the `Channel` unconditionally in `_handle`, not through `on()`, because the push can arrive before `join()` has returned the Channel
- [x] 2.4 Register the Channel in `PhoenixClient.join` before awaiting the join reply, so the room's opening broadcasts are not dropped by `_dispatch` for an unknown topic
- [x] 2.5 Evict a cached credential when a join is refused, and leave a freshly derived one alone; do not fail the caller, because raising would strand the room just created (its channel refuses the push that closes a room)
- [x] 2.6 Unit test: a refused join with a cached credential evicts it and the next room derives a fresh one
- [x] 2.7 Unit test: a refused join with a freshly derived credential does not evict it
- [x] 2.8 Unit test: a refused join still returns a session, preserving existing behaviour

## 3. Valkey-backed credential cache

- [x] 3.1 Add `services/game-service/src/game_service/dragncards/auth_cache.py` with a frozen `DragnCardsIdentity` (token + user id) and a `DragnCardsAuthCache` that reads with `GET` and writes with `SETEX`
- [x] 3.2 Key entries `game-service:dragncards-auth:<sha256(url + NUL + email)[:32]>`, so the key namespaces under the service, distinguishes backend and account, and carries neither in clear text
- [x] 3.3 Wrap every Valkey command so a miss, transport error, or malformed reply logs a warning naming the key and command only, and is reported to the caller as a miss
- [x] 3.4 Treat a non-positive TTL as "cache disabled": no read, no write, always authenticate live
- [x] 3.5 Add `invalidate()` (a `DEL`) used by the rejected-credential path, best-effort like the rest
- [x] 3.6 Unit test: cache hit returns the stored identity without any HTTP call
- [x] 3.7 Unit test: cache miss authenticates live, writes the entry with `SETEX` and the configured TTL, and returns the fresh identity
- [x] 3.8 Unit test: a connection that raises on `GET`, and one that raises on `SETEX`, both still yield a working identity
- [x] 3.9 Unit test: a malformed (non-JSON, or JSON of the wrong shape) cached value is treated as a miss rather than propagating
- [x] 3.10 Unit test: TTL `0` performs no Valkey command at all
- [x] 3.11 Unit test: keys differ for two different backend URLs and for two different accounts, and neither key contains the email

## 4. Session manager uses the cache

- [x] 4.1 Add a credential resolution helper to `SessionManager` returning `(token, user_id)` through the cache, and use it in `create_session`, `attach_session`, and `_restore_session`
- [x] 4.2 Pass the resolved identity into the room join so a refusal can tell a cached credential from a freshly derived one (see section 2; there is no HTTP status to catch, because room creation is unauthenticated upstream)
- [x] 4.3 Keep the cache optional — with no cache configured, `SessionManager` behaves exactly as before, so existing unit tests need no Valkey
- [x] 4.4 Unit test: two consecutive `create_session` calls perform one authentication, not two
- [x] 4.5 Unit test: `attach_session` shares the same cached credential as `create_session`
- [x] 4.6 Unit test: a manager constructed without a cache behaves exactly as before, and a zero TTL authenticates per room
- [x] 4.7 Unit test: no log record on any credential path contains the token, and the span the cache's commands are traced under carries only operation name, server address and port — never a command argument
- [x] 4.8 Confirm each new test fails when the behaviour it covers is deliberately broken

## 5. Configuration and documentation

- [x] 5.1 Read `DRAGNCARDS_AUTH_CACHE_TTL_SECONDS` in `services/game-service/src/game_service/main.py` (default `900`) through a non-negative env helper — separate from the existing strictly-positive one, because `0` here means "do not cache" rather than a typo — and construct the cache from the session-store Valkey URL
- [x] 5.2 Add the variable to `docker-compose.yaml` and `.env.example` with the default, and no credential value anywhere near it
- [x] 5.3 Document it in `services/game-service/README.md` and record the caching rule in `services/game-service/AGENTS.md`, including that the token must never reach a log, span, error, or example
- [x] 5.4 Grep the whole diff for the live token value and for the bot password, and confirm neither appears

## 6. Restore into an existing session

- [x] 6.1 Add `reuse_session_id: str | None` to `RestoreRequest` in `services/history-service/src/history_service/schemas/api.py`, documenting that it is honoured only for `mode="new"` with a full-state base
- [x] 6.2 In `runtime/restore.py`, use the supplied session when `mode="new"`, `ephemeral`, and `base is not None`; otherwise create a session as before and leave the supplied one untouched
- [x] 6.3 Leave `created_new_session` false for a reused session so rollback never deletes a session the caller owns
- [x] 6.4 Attach the reuse decision to the `history.restore` span as a boolean flag only
- [x] 6.5 Unit test: a reuse request with a base loads into the supplied session and creates no session
- [x] 6.6 Unit test: a reuse request with no base, and a non-ephemeral one, each create a fresh session and do not touch the supplied one
- [x] 6.7 Unit test: a failed reuse restore does not delete the supplied session
- [x] 6.8 Unit test: a plugin mismatch on the supplied session surfaces as a client error
- [x] 6.9 Integration test (game-service, against the real DragnCards): loading a state into a room that already holds another one yields a game document byte-for-byte identical to loading it into a fresh room — the upstream `set_game` guarantee reuse rests on

## 7. Dashboard reuses its reconstruction session

- [x] 7.1 Thread `reuse_session_id` through `services/dashboard/features/history/lib/history-api.ts`
- [x] 7.2 In `use-board-reconstruction.ts`, retain the session and room slug when only the selected moment changes, clear the displayed reconstruction, and pass the retained session id on the next open
- [x] 7.3 Dispose the retained session on explicit close, game change, unmount, and `pagehide`, exactly as a displayed one is disposed
- [x] 7.4 Use the remembered room slug when a reuse restore reports no new room, without listing sessions
- [x] 7.5 Unit test: a second open at a different moment of the same game sends the retained session id and creates no second session
- [x] 7.6 Unit test: moving the selection stops rendering the board but does not delete the session
- [x] 7.7 Unit test: switching game deletes the retained session
- [x] 7.8 Unit test: a reuse response without a room slug embeds the remembered room and does not call the session list

## 8. Verification

- [x] 8.1 `./scripts/lint.sh --fix` then `./scripts/lint.sh` exits 0
- [x] 8.2 `./scripts/test.sh unit` — record per-service counts against the recorded baselines
- [x] 8.3 `./scripts/test.sh integration game-service` and `./scripts/test.sh integration history-service`
- [x] 8.4 Re-measure `POST /games` and the ephemeral restore the same way as task 1, several samples, and record the before/after wall clock and the round trips per room creation
- [x] 8.5 Verify a cached token is genuinely reused by observing that a second room creation performs no authentication
- [x] 8.6 Verify a Valkey outage still produces a working room, by pointing the cache at a port with nothing listening
- [x] 8.7 Drive the dashboard with Playwright: open a board at one moment, then at a second moment of the same game, and confirm the second board shows the second moment and that only one room was created
- [x] 8.8 Delete every session, room, and cache key created during verification and confirm the stack is clean
- [x] 8.9 `openspec validate dra-36-valkey-token-cache --strict` and `openspec validate --all`
- [x] 8.10 Scan the change directory for unfinished-work markers and empty sections, and confirm none are present
