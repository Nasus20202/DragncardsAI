# Agent Orchestrator

## ADDED Requirements

### Requirement: Turn and phase authority is derived from the platform's neutral phase classification

The runtime's turn-authority check SHALL decide which phase the board is in by reading the neutral phase classification carried on the simplified game state, and SHALL NOT decide it by matching a platform's own step identifier against a set of step ids held in the orchestrator. The classification SHALL be drawn from the closed neutral set the simplified game state defines, and the platform's own normaliser SHALL be the only place that produces it.

The orchestrator SHALL hold no set of dotted step ids and no assumption about the spelling of a step identifier. DragnCards names its steps `"0.0"`, `"1.1"`, `"2.3"`; marvel-lcg has no dotted step ids at all — its step identifier is a monotonically increasing integer and its phase is human-readable prose such as `"Resolve Mulligans"` or `"Player 1 Turn"`. There is no correspondence between the two numbering schemes, so any orchestrator-side table of step ids is wrong for one platform by construction.

The step identifier and the platform's own phase label SHALL remain available to the runtime as opaque values, for reporting a finding back to a seat in the platform's own words, and SHALL NOT be interpreted. When the classification is `unknown`, the runtime SHALL record no finding, exactly as it records none today when the state cannot be read.

#### Scenario: A DragnCards phase is classified by the state, not by the orchestrator

- **WHEN** a seat of a DragnCards session calls a phase-sensitive tool while the simplified state reports its own step identifier `2.3` and `phase` classification `villain`
- **THEN** the runtime SHALL take `villain` from the state and record an illegal-action finding against that seat
- **AND** the runtime SHALL NOT re-derive the phase by matching `2.3` against any step-id set of its own

#### Scenario: A marvel-lcg integer step id is never matched against dotted step ids

- **WHEN** a seat of a marvel-lcg session calls a seat action tool while the simplified state reports step identifier `41`, `phaseLabel` `Player 1 Turn`, and `phase` classification `player`
- **THEN** no finding SHALL be recorded
- **AND** the integer step identifier SHALL NOT be compared against any dotted step-id vocabulary

#### Scenario: A marvel-lcg prose phase outside a player turn is not classified as a player phase

- **WHEN** a seat of a marvel-lcg session calls a seat action tool while the simplified state reports `phaseLabel` `Resolve Mulligans` and a `phase` classification that is not `player`
- **THEN** an illegal-action finding SHALL be recorded against that seat
- **AND** the finding SHALL name the platform's own `phaseLabel` so the seat reads back the phase in the platform's words

#### Scenario: An unclassifiable phase records no finding

- **WHEN** the simplified state reports phase classification `unknown`
- **THEN** the runtime SHALL record no finding and SHALL NOT fail the job

### Requirement: The phase-advancing and seat-action tool sets are declared per platform

The set of tool names that advance a phase and the set of tool names that constitute a seat playing SHALL be declared per platform, and SHALL NOT be one hardcoded list of DragnCards game-service tool names applied to every session. The runtime SHALL select the sets belonging to the session's platform, and a tool name that appears in one platform's sets SHALL NOT be classified from the other platform's sets.

A platform on which turns advance implicitly SHALL declare an empty phase-advancing set. On marvel-lcg a seat keeps answering prompts until its seat leaves the pending-prompt set; there is no call that moves a shared step marker, and ending a turn is itself one of the enumerated options the engine offers. A seat SHALL NOT be found in violation of phase authority through a tool that platform does not have, and the runtime SHALL NOT synthesise a phase-advancing tool for it.

A platform whose agent surface is enumerated options SHALL place the option-submission tool in its seat-action set, so that submitting a chosen option while the board is outside a player turn is detected the same way playing a card out of turn is detected on DragnCards.

#### Scenario: DragnCards keeps its phase-advancing tools

- **WHEN** a seat of a DragnCards session calls `next_step`, `prev_step`, `player_end_phase`, or `villain_end_phase` while the board is outside the player phase
- **THEN** the call SHALL still be dispatched and an illegal-action finding of the phase-advance kind SHALL be recorded against that seat

#### Scenario: A platform with implicit turn advancement declares no phase-advancing tools

- **WHEN** the runtime resolves the phase-advancing tool set for a marvel-lcg session
- **THEN** the set SHALL be empty and no call SHALL be classified as a phase-advance violation for that session

#### Scenario: Submitting an enumerated option is a seat action

- **WHEN** a seat of a marvel-lcg session submits a chosen enumerated option while the phase classification is not `player`
- **THEN** the call SHALL still be dispatched and an illegal-action finding of the action kind SHALL be recorded against that seat

#### Scenario: One platform's tool names do not classify another platform's calls

- **WHEN** a session on one platform calls a tool whose name appears only in the other platform's seat-action or phase-advancing set
- **THEN** the runtime SHALL treat the call as belonging to neither set and SHALL record no finding for it

### Requirement: On a rules-enforcing platform the pending-prompt set is the turn authority for a seat

When the session's platform enumerates legal moves and names the seats whose decision is pending, the runtime SHALL treat that pending-prompt set, carried on the simplified game state, as the authority on whether a seat is permitted to act, and SHALL record an illegal-action finding against a seat that submits a move while its own seat is absent from that set.

This is stronger than the phase classification and SHALL be used in addition to it: the platform's engine silently discards input from a seat it is not asking, acknowledging the submission without applying it, so a seat acting out of turn there produces no error the seat can observe and no board change. Detection therefore SHALL NOT rest on the platform reporting a failure.

On a platform that does not enumerate pending prompts the simplified state SHALL omit the pending-prompt set, and the runtime SHALL fall back to the phase classification alone. The acting seat within a DragnCards player phase is not a field in game state, so turn order there SHALL remain the orchestrator's prompt-tracked responsibility as it is today.

#### Scenario: A seat acting while another seat is being asked gets a finding

- **WHEN** a seat of a marvel-lcg session submits a move while the pending-prompt set on the simplified state names only another seat
- **THEN** an illegal-action finding SHALL be recorded against the submitting seat
- **AND** the finding SHALL state that the platform was not asking that seat

#### Scenario: A seat acting while it is being asked records no finding

- **WHEN** a seat submits a move while the pending-prompt set names its own seat
- **THEN** no finding SHALL be recorded

#### Scenario: A platform without pending prompts falls back to the phase classification

- **WHEN** the simplified state for a session carries no pending-prompt set
- **THEN** the runtime SHALL classify the call from the phase classification alone and SHALL NOT record a finding for the absence of the set

### Requirement: The system prompt names the platform the session plays on

The assembled system prompt SHALL name the game platform the session is bound to, and SHALL NOT assert that play happens on any one platform unconditionally. The base prompt and the subagent prompt SHALL both state that the agent plays the Marvel Champions Living Card Game and SHALL take the name of the platform it is played on from the session's platform rather than from a fixed literal, so a marvel-lcg session is never told it is playing on the DragnCards digital tabletop.

The identity text SHALL continue to name DragnCardsAI as the system and Marvel Champions as the game, because neither is per-platform. A session whose platform is `dragncards` SHALL be described exactly as it is today, so the existing prompt text is preserved for the default platform rather than rewritten.

The prompt's harness guidance — the tools a main job must not call directly and the platform-specific working notes — SHALL likewise be selected for the session's platform, so a session is never instructed to use a tool its platform does not expose.

#### Scenario: A DragnCards session's prompt is unchanged

- **WHEN** the system prompt is rendered for a session whose platform is `dragncards`
- **THEN** it SHALL state that the Marvel Champions Living Card Game is played on the DragnCards digital tabletop

#### Scenario: A marvel-lcg session's prompt names its own platform

- **WHEN** the system prompt is rendered for a session whose platform is `marvel-lcg`
- **THEN** it SHALL name marvel-lcg as the platform in play
- **AND** it SHALL NOT contain the assertion that the game is played on the DragnCards digital tabletop

#### Scenario: The subagent prompt names the same platform as its parent

- **WHEN** a subagent of a marvel-lcg session begins execution
- **THEN** its system prompt SHALL name the same platform its parent session is bound to

#### Scenario: Harness guidance follows the platform

- **WHEN** the system prompt is rendered for a session
- **THEN** the tool names it forbids calling directly in the main job SHALL be tools the session's platform actually exposes

## MODIFIED Requirements

### Requirement: A seat may act only on its own cards, enforced by the server
A tool call made by a player-seat job SHALL be checked against the caller's own seat before it is dispatched, and SHALL be refused when any argument identifies a player seat other than the caller's own. Refusal SHALL mean the tool is not invoked at all.

The caller's seat SHALL be determined from the seat identity recorded on its session by the orchestrator, and SHALL NOT be taken from anything the player agent can write. A player agent SHALL have no way to change the seat it is treated as. Seat identifiers SHALL remain the neutral `player1`..`player4` vocabulary on every platform; a platform whose transport numbers its seats differently SHALL map them at its own transport edge and SHALL NOT surface its numbering to the guard.

The shapes in which card ownership is addressed SHALL be declared per platform rather than assumed. Two shapes are platform-neutral and SHALL always be checked: an argument that is or contains a seat identifier, and an explicit player-identifying argument. The remaining shapes SHALL come from the session's platform: DragnCards addresses a seat's cards through its `player<N><Group>` group naming, so a group identifier whose seat digit is not the caller's SHALL be refused; marvel-lcg has no group names at all and addresses cards by integer object ids that spell no seat, so ownership there SHALL be resolved from the zone ownership on the normalised game state rather than inferred from the spelling of an identifier.

The guard SHALL NOT infer seat ownership from the shape of an identifier on a platform that does not use that shape. An identifier whose owning seat cannot be resolved SHALL NOT be refused, exactly as a group no seat owns is not refused today, because a seat legitimately affects the villain and shared areas during its own turn. On a platform that enumerates only the moves legal for the seat being asked, that enumeration SHALL be treated as an additional layer of enforcement and SHALL NOT be treated as a reason to skip the check.

A refused call SHALL return an error result naming which argument identified which foreign seat, so the agent can correct itself, and SHALL be recorded as an event on the job so the attempt is visible in the session's timeline and to evaluation.

Enforcement SHALL NOT depend on the seat's instructions. A seat that is told, tricked, or decides to act for another seat SHALL be refused identically.

#### Scenario: A seat acting on another seat's group is refused
- **WHEN** a player agent for seat `player1` of a DragnCards session calls a tool naming a group owned by seat `player2`
- **THEN** the tool SHALL NOT be invoked, an error result SHALL name the offending argument and the foreign seat, and a seat-scope-violation event SHALL be recorded on the job

#### Scenario: A seat acting on its own group is allowed
- **WHEN** a player agent for seat `player1` calls a tool naming a group owned by seat `player1`
- **THEN** the tool SHALL be invoked normally

#### Scenario: A seat affecting a shared area is allowed
- **WHEN** a player agent calls a tool naming a group that no seat owns
- **THEN** the tool SHALL be invoked normally

#### Scenario: An explicit foreign seat argument is refused
- **WHEN** a player agent for seat `player1` calls a tool with a player-identifying argument whose value is `player3`
- **THEN** the tool SHALL NOT be invoked and an error result SHALL be returned

#### Scenario: A foreign seat's card is refused on a platform without group names
- **WHEN** a player agent for seat `player1` of a marvel-lcg session submits an option whose target is a card the normalised state places in seat `player2`'s own zone
- **THEN** the tool SHALL NOT be invoked and the error result SHALL name the target and the foreign seat

#### Scenario: An unresolvable identifier is not refused
- **WHEN** a player agent of a marvel-lcg session submits an option whose target is a card the normalised state places in a shared zone or cannot attribute to any seat
- **THEN** the tool SHALL be invoked normally

#### Scenario: DragnCards group naming is not applied to another platform
- **WHEN** a player agent of a marvel-lcg session passes a string that happens to match the `player<N><Group>` spelling
- **THEN** the guard SHALL NOT treat it as a group identifier of that platform, because the platform declares no group-name shape

#### Scenario: The orchestrator is not seat-scoped
- **WHEN** the orchestrating job calls a tool naming any group
- **THEN** the seat check SHALL NOT apply, because the orchestrator holds no seat
