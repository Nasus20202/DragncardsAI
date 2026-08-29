## ADDED Requirements

### Requirement: Successful game creation establishes a replay boundary

The agent-orchestrator SHALL treat a successful `game-service` `create_game` response that identifies a game different from the calling orchestrator session's current binding as an explicit replay boundary. It SHALL replace the orchestrator session's stored `metadata.game_id` with the newly created game identifier and SHALL preserve any supported platform metadata returned for that game.

#### Scenario: A replacement game rebinds the orchestrator
- **WHEN** an orchestrated session bound to `old-game` successfully calls `create_game` and the response identifies `new-game`
- **THEN** the session SHALL be bound to `new-game` for subsequent game-service calls and emitted move events

#### Scenario: Failed creation does not rebind the orchestrator
- **WHEN** an orchestrated session bound to `old-game` calls `create_game` and game-service returns an error
- **THEN** the session SHALL remain bound to `old-game`

### Requirement: Replay retires persistent seat sessions

When a successful `create_game` call establishes a replacement binding for an orchestrated session, the agent-orchestrator SHALL retire every persistent player-agent session associated with that orchestrator, clear each seat's stored agent-session link, and retain the seat configurations for recreation on the replacement game. Retired player-agent sessions SHALL remain available as terminated records and SHALL NOT be reused for the replacement game.

#### Scenario: The next player prompt starts a fresh seat session
- **WHEN** a replacement game is successfully created for an orchestrated session with a persistent `player1` session
- **THEN** the old `player1` session SHALL be terminated, its seat link SHALL be cleared, and the next `prompt_player_agent` call SHALL create a new child session bound to the replacement game

#### Scenario: An unplayed seat remains configured
- **WHEN** a replacement game is successfully created for an orchestrated session whose `player2` configuration has no agent-session link
- **THEN** the `player2` configuration SHALL remain available with no link and its first prompt SHALL create a replacement-game child session

### Requirement: Existing-game binding remains an authorization boundary

The replay boundary SHALL apply only to a successful `create_game` response. The agent-orchestrator SHALL continue refusing calls that target a different existing game through `attach_game`, `lookup_session_by_slug`, state reads, actions, or turn operations, and SHALL not expose downstream responses from refused calls.

#### Scenario: Attaching an existing different game remains refused
- **WHEN** a session bound to `old-game` calls `attach_game` or `lookup_session_by_slug` and the result identifies `new-game`
- **THEN** the call SHALL be refused without changing the stored binding or forwarding an action for `new-game`

#### Scenario: A replacement game can be used after creation
- **WHEN** `create_game` successfully rebinds a session to `new-game` and the next game-service call supplies `session_id: "new-game"`
- **THEN** the call SHALL be forwarded and SHALL use `new-game` as its event correlation identifier
