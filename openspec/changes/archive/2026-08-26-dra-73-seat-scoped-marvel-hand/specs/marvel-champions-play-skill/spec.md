# Seat-scoped player state guidance

## ADDED Requirements

### Requirement: Player state reads carry the assigned seat

The `marvel-champions-play` runtime skill SHALL instruct a player agent to pass its
assigned neutral seat as `player_n` on every `get_game_state` call. The instruction SHALL
appear in `SKILL.md` and in the state-reading tool reference, state-reading resource,
strategy and recovery resources, play recipes, and both platform references that tell an
agent to read state. The skill SHALL explain that omitting `player_n` requests the
spectator/public projection rather than implicitly selecting `player1`.

#### Scenario: A player agent requests its own state

- **WHEN** the skill directs a player agent to observe or verify the board
- **THEN** the instruction SHALL show `get_game_state` with the agent's assigned `player_n`
- **AND** the agent-facing guidance SHALL explain that this permits the seat's ACL-filtered hand projection

#### Scenario: A deliberate spectator read remains distinct

- **WHEN** guidance describes a read without `player_n`
- **THEN** it SHALL identify that read as the spectator/public projection
- **AND** it SHALL state that omission does not imply `player1`
