## Why

Each session has a human-readable, unique DragnCards `room_slug` (e.g.
`lively-fog-1234`) that is far easier for an operator or LLM to recognize than the
opaque UUID `session_id`. We want to preserve that readability benefit — letting a
caller find a session by its slug — without weakening access control.

The session endpoints are unauthenticated; previously only the unguessable UUID
`session_id` protected a session. The `room_slug` is low-entropy
(`adjective-noun-NNNN`, ~27 bits) and is visible in DragnCards URLs, so accepting it
on state/mutation/delete routes is an IDOR / access-control downgrade: a guessable
slug must never be able to authorize a read, mutation, or delete. The slug is
therefore made **lookup-only**.

## What Changes

- Add a single dedicated, non-mutating lookup `GET /games/by-slug/{room_slug}`
  (exposed as the `lookup_session_by_slug` MCP tool) that returns the session's
  metadata, including the canonical UUID `session_id`. This is the ONLY place a slug
  is accepted.
- Keep state, mutation, and delete endpoints UUID-only: a room slug supplied in the
  `{session_id}` position is NOT resolved and surfaces the existing
  `SessionNotFoundError` (HTTP 404). `get_session`, `delete_session`, and
  `session_operation_lock` resolve by UUID only.
- Normalize a supplied UUID to its canonical form (`str(uuid.UUID(value))`) so a
  valid-but-non-canonical UUID still matches the stored canonical id.
- Keep the secondary `room_slug -> session_id` index in both session stores
  (Valkey `game-service:session-by-slug:{room_slug}` and the in-memory fallback),
  written on session create/attach/put and removed on delete; it backs the lookup.
- Update the `{session_id}` parameter description to state it is UUID-only and point
  callers at the slug lookup; give the lookup tool a clear description.

## Capabilities

### Modified Capabilities

- `game-service`: adds a requirement that a session may be looked up by its
  `room_slug` through a dedicated non-mutating endpoint/tool, while state, mutation,
  and delete endpoints remain UUID-only.

## Impact

- **Affected code**:
  - `services/game-service/src/game_service/logic/session_manager.py`
    (`_normalize_session_id` for UUID-only `get_session` / `delete_session` /
    `session_operation_lock`, plus `lookup_session_by_slug`)
  - `services/game-service/src/game_service/api/routers/game_lifecycle.py`
    (`GET /games/by-slug/{room_slug}` lookup endpoint)
  - `services/game-service/src/game_service/api/models.py`
    (`LookupSessionBySlugResponse`)
  - `services/game-service/src/game_service/coordination/session_store.py`
    (slug index in `InMemorySessionStore` and `ValkeySessionStore`)
  - `services/game-service/src/game_service/api/deps.py` (`SessionIdentifier`
    documented as UUID-only)
- **Tests**: unit coverage in `tests/unit/test_session_store.py`,
  `tests/unit/test_session_manager.py`, `tests/unit/test_game_lifecycle_api.py`, and
  `tests/unit/test_mcp_server.py`.
- **Security**: removes the IDOR/access-control downgrade — a guessable slug can no
  longer authorize state reads, mutations, or deletes.
- **Compatibility**: UUID-based clients are unaffected; slug callers must now use the
  lookup to obtain the `session_id` first.
