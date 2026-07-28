## 1. Shared identifier resolution

- [x] 1.1 Add `SessionManager.resolve_session_id` accepting a UUID or a room slug, with `_as_canonical_uuid` normalization and `_resolve_room_slug` pool-then-store lookup
- [x] 1.2 Raise `SessionNotFoundError` naming both accepted forms when an identifier resolves to neither
- [x] 1.3 Add `AmbiguousSessionIdentifierError` for a slug shared by more than one live session and map it to HTTP 409
- [x] 1.4 Route `get_session`, `delete_session`, and `session_operation_lock` through the resolver, resolving before the lock key is derived
- [x] 1.5 Reuse the resolver in `lookup_session_by_slug`

## 2. API / MCP surface

- [x] 2.1 Rewrite `SESSION_ID_DESCRIPTION` to state that a UUID or a room slug is accepted on every session-identifying endpoint, including 404 and 409 outcomes
- [x] 2.2 Retarget the `lookup_session_by_slug` endpoint description and response-model docstring to a metadata convenience
- [x] 2.3 Resolve the identifier once in `DELETE /games/{session_id}`, return the canonical id, and drop the local `_is_uuid` guard

## 3. Docs and skills

- [x] 3.1 Update `services/game-service/README.md` (session lifecycle, slug lookup, MCP tool surface)
- [x] 3.2 Update `skills/marvel-champions-play/` (SKILL.md, tool-reference, reading-state)
- [x] 3.3 Update `skills/marvel-champions-orchestrator/references/round-loop.md`

## 4. Verify and test

- [x] 4.1 Resolver unit tests: canonical UUID passthrough, non-canonical UUID, slug from pool, slug from store index, unknown identifier, ambiguous slug, stale slug index
- [x] 4.2 Representative read/mutate/delete coverage: HTTP state read and delete by slug, 404 for unknown, 409 for ambiguous, shared lock key for slug vs UUID
- [x] 4.3 MCP test asserting every session-scoped tool's `session_id` description mentions the room slug and no longer claims UUID-only
- [x] 4.4 Integration test driving a live session by slug through read, mutation, and delete
- [x] 4.5 Run `./scripts/lint.sh --fix`, `./scripts/test.sh unit`, `./scripts/test.sh integration game-service`
