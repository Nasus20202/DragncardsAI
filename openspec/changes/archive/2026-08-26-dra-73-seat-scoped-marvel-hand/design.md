# Design: trusted seat-scoped Marvel hand projection

## Context

The game-service currently stores the latest raw platform state on `GameSession` and
normalizes that state for the neutral state endpoint. Marvel LCG world retrieval is
seat-addressed because the engine exposes card ACL metadata and the render transport
has one socket per held seat. The previous normalizer retained a reader seat on the
shared platform object, which made a multi-seat read vulnerable to the wrong reader
being reused. The neutral API also had no way to select the active seat, so an agent
could not request its own hand.

## Goals

- Make the requested Marvel seat explicit at every layer that can affect state
  retrieval or projection.
- Keep spectator reads useful for public board information while hiding every player
  hand, including when the request omits `player_n`.
- Prevent a seat-specific raw response or normalized result from contaminating a later
  read for another seat.
- Ensure durable history is never populated from a player-specific hand projection.
- Preserve the existing DragnCards behavior and the existing `get_game_state`
  operation ID.

## Decisions

### Decision 1: The API selector is optional and trusted-session only

`GET /games/{session_id}/state` gains an optional `player_n` query parameter using the
existing neutral seat vocabulary. A missing parameter is passed as `None` and means the
spectator/public projection; it is never converted to `player1`. The value chooses a
projection inside a trusted service session and is not checked against the caller's
identity. The endpoint returns `Cache-Control: private, no-store` because the response
can contain private hand names. DRA-75 owns caller-bound authorization and raw-state
restriction.

The generated MCP tool remains `get_game_state`, because the operation ID and route do
not change. The optional query parameter therefore appears as an optional tool input
without creating a second state operation.

### Decision 2: Seat selection crosses the session and platform seams

`GameSession.get_state(player_n)` forwards the selector into state retrieval. A
reader-sensitive platform advertises that capability and obtains a fresh world for an
explicit seat rather than using the shared raw-state cache. Marvel is reader-sensitive
because its engine transport applies ACLs at the requested seat. A platform that ignores
`player_n`, such as DragnCards, retains the existing session-cache behavior. The cache
stores raw transport state only; it never stores a normalized reader view. The router
passes the same selector to `GameSession.normalise_state`, so the reader used by the
engine and the reader used by the normalizer cannot silently diverge.

The Marvel driver validates an explicit seat against `held_seats` before checking the
socket or calling `GET /get_world`. When no selector is supplied, Marvel uses its first
held seat only as a transport fallback needed to obtain an engine world. That fallback
is not passed to normalization and cannot reveal that seat's hand in a spectator read.
DragnCards accepts the new protocol argument and ignores it, preserving its current
projection rules and Phoenix request payload.

### Decision 3: Normalization is stateless and fail-closed

`MarvelLcgNormaliser` retains only immutable session configuration and accepts
`player_n` on each `normalise` call. It does not mutate a shared reader seat. For a
selected seat, a hand card is visible when the engine's `visible_for_players` ACL
contains the corresponding zero-based seat; the engine's `is_face_up` flag is not used
to hide owner hand names because Marvel hands are reported face down. Cards in other
zones additionally require a real true `is_face_up` value. Malformed ACL values,
malformed face-up values where face-up is required, missing ACL metadata, and ACLs that
do not include the reader produce `HIDDEN` rather than a card name or identifier.

For a spectator read, each player `hand_cards` zone is forced to `HIDDEN`. Shared or
other public zones are shown only when their ACL permits every engine seat represented
in the world; a card visible to only one seat remains hidden. This keeps public board
information available without treating a spectator as a player. Hidden cards continue
to merge by zone and preserve only their stack count.

### Decision 4: History uses the spectator projection

Marvel platform-native history events call the normalizer with `player_n=None`, never
with the transport fallback or the seat that produced the most recent render frame.
This preserves public board cards where their ACL is unambiguous, forces all hands to
hidden, and prevents private names, identifiers, or metadata from entering the durable
event payload. The existing best-effort history publication contract is unchanged.

## Alternatives rejected

- **Implicitly treat omission as `player1`:** this leaks a seat's private hand to
  spectators and makes a multi-seat agent's view depend on configuration order.
- **Mutate `normaliser.reading_seat` per request:** sequential requests can interleave
  or leave the next caller with the prior reader; per-call input is deterministic.
- **Normalize a cached reader-specific response:** a cache entry obtained for one seat
  cannot safely serve a later seat. Explicit seat reads therefore refresh the world.
- **Use the held-seat transport fallback as the projection reader:** transport access
  and information disclosure are separate concerns; this would leak the first held
  hand on omitted reads.
- **Treat missing or malformed ACL metadata as public:** ambiguous visibility must not
  become an information disclosure, so the card is hidden instead.
- **Put a seat identity into history:** history is durable and shared; it must use the
  spectator-redacted state rather than whichever private view happened to be fetched.

## Security limitation

This change protects projections by seat selection and response caching policy, but it
does not authenticate the selector. A caller with access to the trusted game-service
endpoint can request another held seat's projection. It also leaves the existing raw
state HTTP debug route unchanged. DRA-75 is the follow-up for binding callers to seats
and restricting raw-state access; this design deliberately does not claim those
controls exist.

## Test strategy

Focused game-service unit tests cover the optional HTTP/MCP schema and stable operation
ID, omission semantics, cache-control header, Marvel unheld-seat rejection before
transport, requested-seat forwarding, two-seat and spectator visibility, owner ACL
visibility for engine face-down hand cards, malformed ACL fail-closed behavior,
sequential fresh reads, history redaction, and unchanged DragnCards projection and
cache behavior through the real DragnCards driver. An agent-orchestrator regression
checks that every player-skill state-reading reference names the assigned `player_n`.
