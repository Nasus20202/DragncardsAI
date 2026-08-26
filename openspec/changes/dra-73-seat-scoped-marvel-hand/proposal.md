# Expose the active Marvel LCG hand by seat

## User report

> Your hand is hidden from the engine view. Please list the 6 card names in your hand so I can recommend a play.

The Marvel LCG playing agent cannot observe its own hand through the neutral game
state/options surface and asks the human to transcribe it. The active seat's private
hand must be visible to that seat's agent while remaining hidden from other seats and
spectators.

## Interpretation and owner decision

The implementation adds a trusted-session projection selector to the existing neutral
`get_game_state` HTTP/MCP operation. `player_n` selects which seat's engine-permitted
view is projected, while omission selects the spectator/public projection. The selector
is not caller authorization: any caller that can invoke the existing endpoint can ask
for any held seat. This is the explicit owner decision for DRA-73. Caller-bound seat
authorization and raw-state restriction belong to DRA-75 and are not implemented here.

## What changes

- Add optional `player_n` to `get_game_state` without changing its operation ID or
  neutral response vocabulary.
- Forward the requested seat from the API through `GameSession`, fresh state retrieval,
  the platform seam, Marvel world retrieval, and normalization.
- Validate an explicit Marvel seat against the seats held by the session before making
  an engine request. Keep DragnCards' existing seat-agnostic state behavior.
- Make Marvel normalization a per-call projection. A selected seat sees hand cards whose
  engine ACL lists that seat even when the engine marks those hand cards face down; cards
  outside the ACL, other hands, and spectator hands are collapsed into `HIDDEN` entries,
  and malformed visibility metadata is fail-closed.
- Always emit `Cache-Control: private, no-store` on projected state reads and avoid
  reusing a reader-specific normalized view across sequential seat reads.
- Redact Marvel state used for durable history as a spectator projection so hand names
  never enter recorded events.
- Add focused schema, API, transport, visibility, cache, normalization, history, and
  regression tests.

## Non-goals

- No cross-user authentication, caller-to-seat binding, or authorization policy.
- No change to `/games/{session_id}/state/raw`; its existing HTTP-only debug contract
  remains under DRA-75.
- No change to DragnCards state projection, private-state semantics, or endpoint names.
- No change to Marvel LCG engine rules, render protocol, option identity, or setup.
