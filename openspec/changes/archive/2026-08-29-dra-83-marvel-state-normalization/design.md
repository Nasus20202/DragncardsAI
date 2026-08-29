## Context

The Marvel engine sends a `WorldDescriptor` whose active cards are grouped by area. Runtime
values are in each card's `info` mapping: current villain health is `health`, scheme threat is
`k_threat`, and keyword indicators use names such as `crisis`, `hazard`, and
`acceleration_icon`. The existing normalizer exposes raw engine info keys as neutral tokens,
does not map `area_schemes_side`, and defaults a missing world-level villain health field to
zero.

## Goals / Non-Goals

**Goals:**

- Keep one compact, seat-filtered normalized state for HTTP, MCP, history, and downstream
  consumers.
- Translate only authoritative current values and preserve absence for unavailable facts.
- Use a named shared side-scheme zone and canonical sparse token names that match existing
  DragnCards state.
- Pin the behavior to a representative multi-seat Rhino descriptor fixture and focused tests.

**Non-Goals:**

- No changes to option enumeration, turn ownership, orchestrator prompts, evaluation code, or
  the vendored engine.
- No attempt to calculate printed values, remaining values, or hidden-card contents that the
  engine descriptor does not expose.

## Decisions

### Derive villain health from the active card descriptor and current damage

Read the first visible active villain card's numeric `info.health` value (remaining HP) and add
current damage (`c_damage`, `k_damage`, or `damage`) to emit the cross-platform neutral top-level
`villainHitPoints` (representing total HP of the current villain stage). The damage counter is
simultaneously normalized as `tokens.damage` on the card in `sharedVillain`, so consumers uniformly
calculate remaining HP as `villainHitPoints - sharedVillain[0].tokens.damage`. If a compatible engine
variant explicitly reports a numeric world-level `villain_hit_points`, use it only when no active-card
value is available. Emit the field only when one of those authoritative values is an integer (or a
strict integer string if the engine uses one); do not use a default or fabricated zero.
**Alternatives rejected:** Summing all `area_villain` cards would make the existing singular
neutral field ambiguous for scenarios with multiple villains. Falling back to printed catalog
HP would be stale after damage and would violate the authoritative-world requirement.

### Normalize engine info into the existing token vocabulary

Translate dynamic engine prefixes (`k_` and `c_`) to the canonical token names and map
`acceleration_icon`/`acceleration_token` to `acceleration`. Preserve other non-zero info
keys for compatibility, including target and escalation metadata. This keeps `tokens.threat`
and `tokens.damage` readable by the existing skills while retaining useful engine metadata.

**Alternatives rejected:** Returning both raw and canonical aliases duplicates facts and invites
consumers to choose inconsistent values. Dropping all non-canonical info would remove target
threat and stage metadata already emitted by this normalizer.

### Add `sharedSideSchemes` as a neutral area

Map the engine's shared `area_schemes_side` area to `sharedSideSchemes`. Side schemes are
scenario-wide in the engine and are not equivalent to a seat's engaged-enemy area; assigning
them to a player zone would hide or duplicate them in multiplayer. Apply the same visibility
and hidden-card collapse rules as all shared zones.

**Alternatives rejected:** Omitting side schemes fails the issue's state contract. Reusing
`sharedMainScheme` conflates primary and secondary threat and breaks agents' target selection.

### Enumerate known phase labels before conservative fallback

Recognize all current engine `Phase.State` labels, including `Enemy Activation`, with exact
case-insensitive values and a small compatibility fallback for numbered player turns. Leave
unrecognized prose as `unknown`, while always preserving the original phase label.

**Alternatives rejected:** Substring-only matching misses `Enemy Activation` and can classify
future unrelated labels incorrectly. Parsing `current_step_id` is invalid because Marvel IDs
are opaque render sequence values rather than phase IDs.

## Risks / Trade-offs

- The engine's descriptor shape is upstream behavior we do not control; missing or malformed
  `info` values intentionally result in omitted fields rather than a guessed value.
- Adding a neutral zone is additive, but consumers that enumerate zones must tolerate unknown
  keys; the existing state contract already treats zones as a map and omits empty areas.
- The Marvel render WebSocket can expose an intermediate frame while effects resolve. The
  normalizer remains stateless and reports exactly that frame, including an empty pending-seat
  list and any currently visible card values.
