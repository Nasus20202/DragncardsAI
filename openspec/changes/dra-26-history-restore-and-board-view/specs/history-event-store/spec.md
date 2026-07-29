# history-event-store spec delta

## MODIFIED Requirements

### Requirement: Restore to a past moment

The history-service SHALL restore a game to an arbitrary past moment identified by a target `seq` by reconstructing both the game state (loading the densest full-state base at or before the target into a game-service session and replaying the subsequent game-mutating events forward up to and including the target `seq`) and the agent's conversation context as of the target `seq` (loaded into an orchestrator session bound to the restored game), so the agent faces an identical, replayable situation.

The two layers are NOT equally essential, and the service SHALL NOT let the second fail the first. The game-state layer is the restore; the agent-context layer is an enhancement to it. A restore whose game state was applied SHALL be reported as a restore that happened, together with whether the agent conversation was rebuilt and, when it was not, a human-readable reason. This is not a cosmetic distinction: the agent-context layer runs after the game state has already been written, and an in-place restore has no rollback, so reporting a completed rewind as a failure describes a state that does not exist and invites the user to retry a destructive action that already succeeded.

Specifically, agent-orchestrator answers `404` to a `mode="in place"` context restore when no ACTIVE agent session is bound to the game. That is a correct answer, not a fault: the session that played a game is terminated long before anyone browses its history, so most games worth restoring have none to resume. The history-service SHALL treat that `404` as "there is no agent session to resume" and complete the restore. Any other upstream failure status SHALL still fail the restore, so a genuine fault is never silently swallowed.

The restore result SHALL name the DragnCards room holding the restored state whenever the restore created one. A branch restore's entire product is a new game room, and a room the caller cannot address is indistinguishable from a restore that never happened; the room slug is returned by game-service on the same response that assigns the session id, so naming it costs nothing and removes both an extra round trip and a race against the ephemeral reaper.

#### Scenario: Restore from the nearest full-state base then replay forward
- **WHEN** a client requests a restore of a `game_id` to a target `seq`
- **THEN** the history-service SHALL select the densest full-state base at or before the target `seq` — a periodic snapshot or a `game_state` event, whichever is more recent — load it into a game-service session, and replay the game-mutating events between that base and the target `seq` in ascending `seq` order

#### Scenario: Restore reconstructs the agent conversation context
- **WHEN** the history-service restores a `game_id` to a target `seq`
- **THEN** the history-service SHALL reconstruct the agent's conversation context as captured at the latest `agent` event at or before the target `seq` and SHALL provide it to the orchestrator to seed a session bound to the restored game

#### Scenario: Restore into a new branchable session
- **WHEN** a client requests a restore with the target mode "new session"
- **THEN** the history-service SHALL create a new game-service session and orchestrator session for the restored moment, SHALL leave the original game's events and any live session unmodified, and SHALL report the new session's `room_slug` so the caller can open the game that was created

#### Scenario: Restore in place over the live session
- **WHEN** a client requests a restore with the target mode "in place"
- **THEN** the history-service SHALL restore the existing live session to the target moment, discarding game state after the target `seq`

#### Scenario: In-place restore completes when no agent session is bound to the game
- **WHEN** a client requests an in-place restore of a game for which the orchestrator reports no active agent session bound to that `game_id`
- **THEN** the history-service SHALL complete the game-state restore, SHALL report that the agent conversation was not rebuilt together with the reason, and SHALL NOT report the restore as failed

#### Scenario: In-place restore over a live session that no longer exists
- **WHEN** a client requests an in-place restore of a game whose live game-service session has been deleted or reaped
- **THEN** the history-service SHALL reject the request with a message stating that the live session no longer exists and naming the branchable restore as the alternative, and SHALL NOT mutate anything

#### Scenario: Genuine orchestrator failures still fail the restore
- **WHEN** the orchestrator fails a context restore with any status other than `404`
- **THEN** the history-service SHALL fail the restore rather than reporting a partially completed one as successful

#### Scenario: Restore when no full-state base exists
- **WHEN** a client requests a restore to a target `seq` for which no snapshot and no usable `game_state` event exists at or before that `seq`
- **THEN** a branchable restore SHALL begin from an initial game-service session and replay the game-mutating events from `seq` 1 up to the target `seq`, and an in-place restore SHALL be rejected with a message naming the missing base — because replaying forward onto an un-rewound live session would double-apply every event

#### Scenario: Reject restore to an out-of-range moment
- **WHEN** a client requests a restore to a target `seq` that does not exist for the `game_id`
- **THEN** the history-service SHALL reject the request with a descriptive client error and SHALL NOT mutate any game-service or orchestrator session

#### Scenario: Agent decision events are not replayed as mutations
- **WHEN** the history-service replays events forward during a restore
- **THEN** it SHALL apply only `game-service` game-mutating events as actions and SHALL NOT apply `agent` decision events as game mutations

#### Scenario: The replay range is narrowed to replayable events in the database
- **WHEN** the history-service reads the events to replay between the base and the target
- **THEN** it SHALL restrict that read to `game-service` events in the query itself rather than reading every actor's events and skipping them after they are transferred — because when the base is the nearest `game_state` event that range contains no `game-service` events at all, so the read should return nothing rather than fetching and parsing every intervening agent payload only to skip it (measured: 219,476 bytes on a 124-event game)

### Requirement: Game-state events carry a full, self-sufficient reconstruction base

Every `game_state` event SHALL record the session `plugin_name` slug and the complete game state in its payload, so a reconstruction can be built from history alone. A restore SHALL load the full state embedded in the nearest `game_state` event at or before the target as its base when that event is at least as recent as the nearest periodic snapshot (the densest available, preferring it over a sparser snapshot), rather than relying on action replay — because setup actions (e.g. deck loading) are not all recorded as replayable actions, so replay-from-start yields an incomplete board.

This base selection SHALL apply to **every** restore mode, not only branchable ones. A `game_state` event embeds the same complete board a snapshot does, so it establishes an equally clean base for an in-place rewind; requiring a periodic snapshot there rejected every game shorter than one snapshot cadence, which is most games a user browses. The `plugin_name` SHALL be resolvable without any snapshot (from a `game_state` event), so short games with no snapshot can still be reconstructed.

Reading the `plugin_name` SHALL NOT require loading snapshot documents that are then discarded. Every snapshot row carries a full board (~245 KB measured), so the read SHALL be bounded to the single row it consumes rather than fetching every snapshot of the game to extract one short string (measured: 1,347,305 B across 6 documents to read a 16-character slug).

#### Scenario: Short game with no snapshot reconstructs with full state

- WHEN a branchable restore targets a game that has no periodic snapshot
- THEN the branch session is created from the `plugin_name` recorded on a `game_state` event, and the nearest `game_state` event's full state is loaded as the base, reproducing the board (including cards loaded during setup)

#### Scenario: In-place rewind of a game with no snapshot

- WHEN an in-place restore targets a moment for which no periodic snapshot exists but a `game_state` event does
- THEN that event's full recorded board is loaded into the live session as the clean base and the rewind completes, rather than being rejected for want of a snapshot

#### Scenario: Ephemeral reconstruction does not restore agent context

- WHEN an ephemeral (view-only) reconstruction is created
- THEN only the game-state layer is restored; no orchestrator agent session is created for it
