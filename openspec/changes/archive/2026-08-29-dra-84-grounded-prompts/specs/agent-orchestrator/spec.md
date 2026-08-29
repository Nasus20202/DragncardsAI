# Grounded Marvel player prompts

## MODIFIED Requirements

### Requirement: Player-agent prompts use verified current authority

The agent-orchestrator SHALL provide one player-turn prompt contract for every configured seat
on either supported game platform. Before a seat is prompted, the coordinator SHALL read the
latest platform-neutral `game-service_get_game_state` projection for that seat and SHALL build
the prompt from that normalized state only. For `marvel-lcg`, the prompt SHALL also carry the
exact current `game-service_list_game_options` response for the assigned seat, including the
engine prompt, option identifiers, targets, and payment data.

The prompt SHALL identify the session, platform, and assigned seat, and SHALL keep the complete
normalized state in an `AUTHORITATIVE STATE CHECKPOINT` block. It SHALL keep the current engine
response in a separate `CURRENT ENGINE PROMPT` block. The coordinator SHALL NOT add rules,
printed statistics, card locations, outcomes, recommended actions, target rankings, or other
facts absent from those authoritative responses. An omitted normalized field SHALL remain
unreported rather than being filled from memory or a player report. `phase` SHALL be used for
phase classification; opaque `phaseLabel` text SHALL NOT be parsed.

If a required checkpoint field is missing or the checkpoint conflicts with the last verified
checkpoint, the coordinator SHALL perform exactly one fresh authoritative state read. If the
fresh read remains missing or contradictory, the coordinator SHALL stop and report the
observed state without prompting the seat.

#### Scenario: Current normalized state replaces a stale board summary

- **WHEN** a persistent seat has a prior prompt containing an old threat value or HP value and
the latest normalized state reports different values
- **THEN** the new player prompt SHALL contain the latest normalized state values
- **AND** the new prompt SHALL NOT copy the old values or the seat's prior report

#### Scenario: Rhino threat checkpoints remain current and non-terminal

- **WHEN** verified normalized checkpoints report main-scheme threat `9/14`, `12/14`, and
`14/14` while the active villain reports 19 remaining HP (stage total `villainHitPoints=28` with 9 damage tokens) and `mode=in progress`
- **THEN** each prompt SHALL report the checkpoint as ongoing normalized state
- **AND** the coordinator SHALL NOT report the villain as defeated from the final `14/14`
checkpoint

#### Scenario: Missing or contradictory state stops prompt construction

- **WHEN** a required normalized field is missing or conflicts with the previously verified
checkpoint
- **THEN** the coordinator SHALL perform one fresh authoritative state read
- **AND** SHALL stop without prompting when that read does not resolve the contradiction

#### Scenario: Engine options remain engine-owned

- **WHEN** a `marvel-lcg` seat has a current enumerated engine response
- **THEN** the player prompt SHALL preserve the response's prompt and option data exactly
- **AND** the coordinator SHALL NOT rewrite it as a preferred action or supply an option that
is absent from the response

### Requirement: Persistent player-session memory has current-state precedence

A player seat's persistent session SHALL use one memory contract on every invocation. Earlier
prompts, tool results, reports, card facts, threat values, HP values, phases, stages, option
identifiers, and terminal claims SHALL be treated as historical. The current prompt's complete
`AUTHORITATIVE STATE CHECKPOINT` SHALL take precedence over replayed context.

When the current checkpoint is absent, incomplete, or contradictory, the seat SHALL perform one
fresh `game-service_get_game_state` read for its assigned seat before any move. If the fresh
read does not resolve the issue, the seat SHALL stop and report the observed missing or
contradictory state. The seat SHALL NOT restore the missing fact from persistent replay.

#### Scenario: Persistent replay cannot restore a stale fact

- **WHEN** a seat's replayed transcript says an earlier HP, threat, phase, or option value and
the current checkpoint supplies a different value
- **THEN** the seat SHALL discard the replayed value for the current invocation
- **AND** SHALL use only the current checkpoint and current engine response

#### Scenario: One fresh read is bounded

- **WHEN** the current prompt lacks a required state block or contains contradictory state
- **THEN** the seat SHALL make at most one fresh authoritative state read before acting
- **AND** SHALL stop rather than repeatedly retrying or guessing when the contradiction remains

### Requirement: Terminal reporting follows normalized state

The coordinator and player seats SHALL report a terminal outcome only when the latest
normalized state reports `mode=win` or `mode=loss`, or when the exact current engine response
is explicitly terminal. Missing `villainHitPoints`, a threat value, an old HP value, a stage-like
card name, or a player claim SHALL NOT establish terminal state. If authoritative HP or stage
data remains while `mode=in progress`, the villain SHALL be reported as ongoing.

#### Scenario: Remaining villain health blocks a defeated claim

- **WHEN** normalized state reports an active villain with authoritative HP or stage data and
`mode=in progress`
- **THEN** the coordinator SHALL NOT report the villain as defeated
- **AND** SHALL continue or stop according to the current phase and engine authority

#### Scenario: Missing health remains unknown

- **WHEN** normalized state omits `villainHitPoints`
- **THEN** the coordinator and seat SHALL treat current health as unreported
- **AND** SHALL NOT substitute zero or use absence as a win signal
