## ADDED Requirements

### Requirement: Game-state events carry a full, self-sufficient reconstruction base

Every `game_state` event SHALL record the session `plugin_name` slug and the complete game state in its payload, so a branchable reconstruction can be built from history alone. A branchable ("new"/ephemeral) restore SHALL load the full state embedded in the nearest `game_state` event at or before the target as its base (the densest available, preferring it over a sparser periodic snapshot), rather than relying on action replay — because setup actions (e.g. deck loading) are not all recorded as replayable actions, so replay-from-start yields an incomplete board. The branch `plugin_name` SHALL be resolvable without any snapshot (from a `game_state` event), so short games with no snapshot can still be reconstructed.

#### Scenario: Short game with no snapshot reconstructs with full state

- WHEN a branchable restore targets a game that has no periodic snapshot
- THEN the branch session is created from the `plugin_name` recorded on a `game_state` event, and the nearest `game_state` event's full state is loaded as the base, reproducing the board (including cards loaded during setup)

#### Scenario: Ephemeral reconstruction does not restore agent context

- WHEN an ephemeral (view-only) reconstruction is created
- THEN only the game-state layer is restored; no orchestrator agent session is created for it


### Requirement: Ephemeral reconstruction sessions are non-emitting and self-reclaiming

Reconstructing a past moment for viewing SHALL create an ephemeral session that emits no history events (so it never appears in the games list and produces nothing to clean up), distinct from a kept "new branchable session". Ephemeral reconstruction sessions SHALL be reclaimed server-side after a configurable TTL — their session state and DragnCards room deleted — even if the client never issues an explicit teardown (e.g. lost network connection, tab crash, or power loss). Explicit client teardown remains the fast path for immediate cleanup.

#### Scenario: Viewing reconstruction does not pollute history

- WHEN a user opens the board reconstructed at a past event (an ephemeral reconstruction)
- THEN that reconstruction emits no history events and does not appear as a new game in the games list

#### Scenario: Reconstruction is reclaimed after a lost connection

- WHEN the client that opened an ephemeral reconstruction never issues a teardown (its connection is lost or the tab is killed)
- THEN the server reclaims the reconstruction session and its room after the TTL elapses, leaving no orphaned session or room

#### Scenario: Explicit teardown reclaims immediately

- WHEN the client closes the reconstruction view and issues a teardown
- THEN the reconstruction session and its room are deleted immediately rather than waiting for the TTL
