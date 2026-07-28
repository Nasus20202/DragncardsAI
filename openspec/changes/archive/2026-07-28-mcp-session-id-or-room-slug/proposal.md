## Why

Every game-service MCP tool identifies a session by an opaque UUID. In practice an
operator reads a transcript full of `3f1a9c2e-5b6d-…` and an agent has to carry that
string through dozens of calls, while the same session already has a short,
human-readable DragnCards room slug (`lively-fog-1234`) printed in the room URL.

A previous change (`2026-06-24-accept-session-id-or-slug`) deliberately narrowed slug
support to a single read-only lookup (`GET /games/by-slug/{room_slug}`,
`lookup_session_by_slug`), keeping state/mutation/delete endpoints UUID-only. Its
recorded rationale: the session endpoints are unauthenticated, the slug is
low-entropy (`adjective-noun-NNNN`, roughly 27 bits) and visible in DragnCards URLs,
so accepting it on state/mutation/delete routes is an IDOR / access-control
downgrade — "a guessable slug must never be able to authorize a read, mutation, or
delete."

That rationale is overruled by an explicit repository-owner directive. Asked to use
"the game slug name in mcp tool endpoints, for better readability", and shown the
UUID-only code comment stating the slug must never authorize a read or delete, the
owner answered: "WE WANT IT TO BE STOOPID_HUMAN FRIENDLY". Readability for the human
and the agent driving a local-dev game harness is therefore valued above the residual
guessability of the room slug. This change makes the slug a first-class session
identifier everywhere.

## What Changes

- Add one shared resolver, `SessionManager.resolve_session_id`, that accepts either a
  UUID `session_id` or a room slug and returns the canonical session id. A
  well-formed UUID is normalized (`str(uuid.UUID(value))`) and returned without a
  store round-trip; anything else is resolved as a room slug via the in-process
  session pool and then the session store's `room_slug -> session_id` index.
- Route every session-identifying path through it: `get_session`, `delete_session`,
  and `session_operation_lock`. Because all ~36 MCP tools and every HTTP session
  endpoint funnel through those three, reads, mutations, and delete all accept a slug
  with no per-route changes. Resolution happens *before* the lock key is derived, so
  a slug-addressed and a UUID-addressed operation on the same session still contend
  for the same lock.
- Report an identifier that is neither a well-formed session id nor a known room slug
  as `SessionNotFoundError` (HTTP 404), with a message that names both accepted
  forms.
- Add `AmbiguousSessionIdentifierError` (HTTP 409) for the one case where a slug does
  not identify exactly one session: DragnCards room slugs are unique per room, but
  `attach_game` can create several game-service sessions pointing at the same room,
  and the store's slug index is last-writer-wins. When more than one live session
  shares a slug, the request is refused and the caller is told to use the UUID.
- Rewrite the shared `session_id` parameter description (the text an MCP agent
  actually reads) to state that either form is accepted everywhere, plus the 404 and
  409 behaviors. Retarget the `lookup_session_by_slug` description: it is now a
  metadata convenience, not a required first step.
- Simplify `DELETE /games/{session_id}`: it resolves the identifier once up front,
  returns the canonical `session_id`, and drops the local `_is_uuid` guard. Unknown
  identifiers still 404; a resolvable session that is already gone is still an
  idempotent success.
- Update `services/game-service/README.md`, `skills/marvel-champions-play/`, and
  `skills/marvel-champions-orchestrator/` where they told agents the slug was never
  accepted.

## Capabilities

### Modified Capabilities

- `game-service`: the "Look up a session by room slug" requirement is replaced by one
  that accepts a session id **or** a room slug on every session-identifying
  endpoint/tool, keeps the slug lookup as a metadata read, and defines the not-found
  and ambiguous-slug outcomes.

## Impact

- **Affected code**:
  - `services/game-service/src/game_service/logic/session_manager.py`
    (`resolve_session_id`, `_resolve_room_slug`, `_as_canonical_uuid`, replacing
    `_normalize_session_id`)
  - `services/game-service/src/game_service/logic/exceptions.py`
    (`AmbiguousSessionIdentifierError`)
  - `services/game-service/src/game_service/api/exception_handlers.py` (409 mapping)
  - `services/game-service/src/game_service/api/deps.py` (`SESSION_ID_DESCRIPTION`)
  - `services/game-service/src/game_service/api/routers/game_lifecycle.py` (delete
    resolves up front; lookup description)
  - `services/game-service/src/game_service/api/models.py`
    (`LookupSessionBySlugResponse` docstring)
- **Docs**: `services/game-service/README.md`,
  `skills/marvel-champions-play/SKILL.md`,
  `skills/marvel-champions-play/resources/tool-reference.md`,
  `skills/marvel-champions-play/resources/reading-state.md`,
  `skills/marvel-champions-orchestrator/references/round-loop.md`.
- **Tests**: `tests/unit/test_session_manager.py` (resolver matrix),
  `tests/unit/test_game_lifecycle_api.py` (HTTP acceptance, 404, 409),
  `tests/unit/test_mcp_server.py` (every session-scoped tool's `session_id`
  description mentions the room slug), `tests/integration/test_api.py` (slug-driven
  read, mutation, and delete against a live room).
- **Security — accepted trade-off, not resolved**: the game-service session endpoints
  are unauthenticated, and a room slug is low-entropy (~27 bits), guessable, and
  visible in DragnCards URLs. Accepting it on state, mutation, and delete paths
  therefore reinstates the IDOR / access-control downgrade the previous change
  removed: anyone who can reach the service and guess or observe a slug can read the
  board, mutate the game, or delete the session. This was accepted knowingly by the
  repository owner, on the directive quoted under "Why", for a local-development
  harness; it was not resolved. The mitigating context is only that
  the service is not exposed publicly; if it ever is, this decision must be revisited
  and replaced with real authentication rather than identifier entropy.
- **Compatibility**: purely additive for callers. Every existing UUID call keeps
  working; the only behavior change is that `DELETE /games/{session_id}` now echoes
  the canonical session id rather than the raw path value (identical for UUID
  callers).
