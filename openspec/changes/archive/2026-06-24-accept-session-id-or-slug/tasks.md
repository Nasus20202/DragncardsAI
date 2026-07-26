## 1. Session store slug index

- [x] 1.1 Add `get_session_id_by_slug` to the `SessionStore` protocol
- [x] 1.2 Maintain a `room_slug -> session_id` index in `InMemorySessionStore` on put/delete
- [x] 1.3 Maintain a `game-service:session-by-slug:{room_slug}` key in `ValkeySessionStore` on put/delete

## 2. SessionManager: lookup-only slug, UUID-only mutations

- [x] 2.1 Add a non-mutating `lookup_session_by_slug` that resolves a slug via the pool/store and returns session metadata (incl. `session_id`)
- [x] 2.2 Keep `get_session`, `delete_session`, and `session_operation_lock` UUID-only (no slug resolution)
- [x] 2.3 Normalize a supplied UUID to canonical form (`str(uuid.UUID(value))`) on the UUID-only paths
- [x] 2.4 Surface `SessionNotFoundError` for an unknown slug and for a slug supplied to a UUID-only path

## 3. API / MCP surface

- [x] 3.1 Add `GET /games/by-slug/{room_slug}` returning `LookupSessionBySlugResponse`, exposed as the `lookup_session_by_slug` MCP tool with a clear description
- [x] 3.2 Document the `SessionIdentifier` (`{session_id}`) path parameter as UUID-only and point callers at the slug lookup

## 4. Verify and test

- [x] 4.1 Add unit tests: slug lookup returns the correct `session_id`; unknown slug → 404; slug index maintained on create/delete; state/mutation/delete routes are UUID-only (a slug does NOT resolve); non-canonical UUID still matches
- [x] 4.2 Run unit tests
- [x] 4.3 Run the Python formatter
