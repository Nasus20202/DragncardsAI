## Context

A player child session is represented by three metadata values: its player id, display name, and orchestrator session id. Those values are written by the player-agent runtime, but public session create and update endpoints currently accept arbitrary metadata. Seat resolution must therefore treat metadata as an untrusted hint and verify the relationship against the orchestrator's loaded `SessionPlayerConfig` rows.

The persistent seat path currently reads a configuration, creates or reuses a child, then writes the child session id. The write must be conditional on the row still being unclaimed so two prompts cannot overwrite ownership.

## Decisions

1. Define the three player identity metadata keys as server-owned at the session API boundary. Copy incoming metadata, remove those keys, and then apply the validated persona snapshot. Preserve unrelated caller metadata.
2. In `resolve_seat_identity`, require an orchestrated parent and a loaded player configuration whose `player_id` matches the metadata and whose `agent_session_id` equals the candidate child session id. Fail closed when the association is missing.
3. Replace the persistent seat repository read/write claim with `UPDATE ... WHERE agent_session_id IS NULL`. Return whether exactly one row was claimed; callers retain the existing behavior when the claim loses a race.
4. Keep metadata-based identity as the transport format for existing history and tool guards, but make roster persistence the authority for authorization.

## Data and concurrency invariants

- A public caller cannot persist `player_id`, `player_display_name`, or `orchestrator_session_id` as session metadata.
- A session is a player seat only when its identity metadata and its parent's persisted roster agree.
- At most one child session id can win the transition of a seat from unclaimed to claimed.
- Existing seat sessions remain reusable; a failed conditional claim never changes the stored owner.

## Risks and mitigations

- ORM test doubles may not expose `player_configs`; they must be updated to model the loaded relationship so tests exercise the fail-closed path.
- Database row-count behavior differs across drivers; the repository treats one affected row as success and any other result as a lost claim.
- Existing callers that use public metadata for non-seat values remain unaffected because only the three reserved keys are removed.
