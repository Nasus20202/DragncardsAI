## MODIFIED Requirements

### Requirement: Restore to a past moment

The history-service SHALL restore a game to an arbitrary past moment identified by a target `seq` by reconstructing both the game state (loading the densest full-state base at or before the target into a game-service session and replaying the subsequent game-mutating events forward up to and including the target `seq`) and the agent's conversation context as of the target `seq` (loaded into an orchestrator session bound to the restored game), so the agent faces an identical, replayable situation.

The two layers are NOT equally essential, and the service SHALL NOT let the second fail the first. The game-state layer is the restore; the agent-context layer is an enhancement to it. A restore whose game state was applied SHALL be reported as a restore that happened, together with whether the agent conversation was rebuilt and, when it was not, a human-readable reason. This is not a cosmetic distinction: the agent-context layer runs after the game state has already been written, and an in-place restore has no rollback, so reporting a completed rewind as a failure describes a state that does not exist and invites the user to retry a destructive action that already succeeded.

Specifically, agent-orchestrator answers `404` to a `mode="in place"` context restore when no ACTIVE agent session is bound to the game. That is a correct answer, not a fault: the session that played a game is terminated long before anyone browses its history, so most games worth restoring have none to resume. The history-service SHALL treat that `404` as "there is no agent session to resume" and complete the restore. Any other upstream failure status SHALL still fail the restore, so a genuine fault is never silently swallowed.

The restore result SHALL name the DragnCards room holding the restored state whenever the restore created one. A branch restore's entire product is a new game room, and a room the caller cannot address is indistinguishable from a restore that never happened; the room slug is returned by game-service on the same response that assigns the session id, so naming it costs nothing and removes both an extra round trip and a race against the ephemeral reaper.

A `mode="new"` restore SHALL accept an optional existing game-service session to restore into, and SHALL honour it ONLY when the restore is `ephemeral` AND a full-state base at or before the target exists. Building a room is several sequential round trips to DragnCards plus a channel join and a plugin load, measured at ~590 ms of a ~728 ms restore, whereas loading a full-state base into an already-open room was measured at ~55 ms; a caller viewing a second moment of the same game already holds a room that can be re-pointed instead of replaced.

The base requirement is the safety gate, not an optimisation detail. Loading a full-state base issues the DragnCards `set_game` action, which replaces the room's game document outright rather than merging into it, so the loaded document is the entire resulting state and nothing from the previous contents survives. A restore with no base has no such guarantee: it replays forward from `seq` 1 onto whatever the session already holds, which in a reused session is the previous view. The service SHALL therefore create a fresh session whenever no base exists, even when a session to reuse was supplied.

The `ephemeral` condition is what keeps the field aimed at the flow it exists for. Reuse overwrites a session the caller names rather than one the restore created, and an ephemeral reconstruction is by definition a throwaway the caller built in order to look at it. A kept branch restore's whole product is the room it creates, so it SHALL always create one; without this condition the field would be a way to replace an unrelated live session's board with a different game's.

A supplied session SHALL NOT be deleted by the restore's rollback when a restore fails, because the restore did not create it and the caller still owns it. A session whose plugin does not match the game being restored SHALL cause the restore to fail with a client error rather than be loaded into.

#### Scenario: Restore from the nearest full-state base then replay forward
- **WHEN** a client requests a restore of a `game_id` to a target `seq`
- **THEN** the history-service SHALL select the densest full-state base at or before the target `seq` — a periodic snapshot or a `game_state` event, whichever is more recent — load it into a game-service session, and replay the game-mutating events between that base and the target `seq` in ascending `seq` order

#### Scenario: Restore reconstructs the agent conversation context
- **WHEN** the history-service restores a `game_id` to a target `seq`
- **THEN** the history-service SHALL reconstruct the agent's conversation context as captured at the latest `agent` event at or before the target `seq` and SHALL provide it to the orchestrator to seed a session bound to the restored game

#### Scenario: Restore into a new branchable session
- **WHEN** a client requests a restore with the target mode "new session"
- **THEN** the history-service SHALL create a new game-service session and orchestrator session for the restored moment, SHALL leave the original game's events and any live session unmodified, and SHALL report the new session's `room_slug` so the caller can open the game that was created

#### Scenario: Restore into a supplied existing session
- **WHEN** a client requests an `ephemeral` `mode="new"` restore naming an existing game-service session to restore into, and a full-state base at or before the target exists
- **THEN** the history-service SHALL load that base into the named session and replay forward into it, SHALL NOT create a game-service session or a DragnCards room, and SHALL report the restore against the named session

#### Scenario: A reused session ends in exactly the target state
- **WHEN** a session that already holds one moment of a game is restored to a different moment of that game
- **THEN** the resulting game state SHALL be identical to the state produced by restoring that same moment into a freshly created session, carrying nothing over from the moment it previously held

#### Scenario: A supplied session is ignored when no full-state base exists
- **WHEN** a client requests an `ephemeral` `mode="new"` restore naming an existing session, but no snapshot and no usable `game_state` event exists at or before the target `seq`
- **THEN** the history-service SHALL create a fresh session and replay into that instead, and SHALL leave the named session untouched

#### Scenario: A supplied session is ignored for a kept branch restore
- **WHEN** a client requests a non-`ephemeral` `mode="new"` restore naming an existing session
- **THEN** the history-service SHALL create a fresh session and restore into that, and SHALL leave the named session untouched

#### Scenario: A supplied session is not deleted when the restore fails
- **WHEN** an `ephemeral` `mode="new"` restore into a supplied existing session fails part-way through
- **THEN** the history-service SHALL report the failure and SHALL NOT delete the supplied session, because the caller owns it

#### Scenario: A supplied session for the wrong plugin is rejected
- **WHEN** a client requests a restore into an existing session whose plugin differs from the plugin recorded for the game
- **THEN** the history-service SHALL fail the restore with a client error and SHALL NOT leave the named session holding a partially loaded state

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
