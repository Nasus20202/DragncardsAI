# Game Orchestration

## ADDED Requirements

### Requirement: The orchestrator skill ships one round-loop reference per platform

The `marvel-champions-orchestrator` skill SHALL keep a single platform-neutral round-loop skeleton in its own body — the order of the phases, the seat loop, the terminal conditions, and the separation of authority — and SHALL move every harness-specific instruction into one reference file per supported platform. It SHALL ship a DragnCards round-loop reference and a marvel-lcg round-loop reference, SHALL name each in its routing table together with the condition under which the agent loads it, and SHALL instruct the agent to load exactly the reference for the platform its session is bound to.

The authoritative tool list SHALL live in the per-platform reference and SHALL NOT live in the neutral skeleton, because a tool list is the most platform-specific thing the skill carries: DragnCards' round loop is a sequence of named game-service calls that move a step marker, and marvel-lcg has no such call at all. The neutral skeleton SHALL NOT name a platform's tools, and it SHALL NOT contain conditional prose that branches on the platform inside a step, because the authority of a procedure comes from being unambiguous at the point of action.

The Marvel Champions rules the loop implements SHALL NOT be duplicated per platform. What differs between the references is how a phase is observed and advanced, not what the phases are.

#### Scenario: The skill routes to the reference for the session's platform

- **WHEN** the orchestrator agent of a marvel-lcg session loads the skill
- **THEN** the routing table SHALL name the marvel-lcg round-loop reference and its load condition
- **AND** the agent SHALL load that reference rather than the DragnCards one

#### Scenario: The neutral skeleton names no platform tools

- **WHEN** the orchestrator agent reads the skill body
- **THEN** the phase order, the seat loop, and the terminal conditions SHALL be stated without naming any platform's tools
- **AND** the authoritative tool list SHALL be found only in a per-platform reference

#### Scenario: The rules are stated once

- **WHEN** both platform references are read
- **THEN** neither SHALL restate the Marvel Champions phase rules, which SHALL remain in the neutral skeleton and the shared rules corpus

### Requirement: On a rules-enforcing platform the orchestrator drives from the pending-prompt signal

When the session's platform adjudicates the rules and names the seats whose decision is pending, the orchestrator SHALL drive the round from that pending-prompt signal read from game state, and SHALL NOT drive it from a phase clock it tracks in its own prompt. It SHALL prompt the seat the platform is asking, SHALL wait until that seat's own turn has left the pending-prompt set before prompting another seat, and SHALL treat an empty pending-prompt set as the platform still resolving and not as a seat's turn to act.

Turn advancement on such a platform SHALL be observed, not commanded. On marvel-lcg a seat keeps answering prompts until its seat leaves the pending-prompt set; there is no call that ends a turn, because ending the turn is itself one of the enumerated options the engine offers to the seat whose turn it is. The orchestrator SHALL therefore never attempt to advance a turn, a phase, or a round on that platform, and SHALL NOT treat the absence of an advancement call as a stalled loop.

The prompt-tracked turn order the orchestrator maintains on a platform that exposes no acting seat SHALL NOT be maintained on a platform that does. Where the platform names the seat it is asking, that name SHALL be the authority and the orchestrator's own record SHALL NOT override it.

#### Scenario: The orchestrator prompts the seat the platform is asking

- **WHEN** the pending-prompt set on the game state names one seat
- **THEN** the orchestrator SHALL prompt that seat's player agent and SHALL NOT prompt another seat until that seat has left the set

#### Scenario: An empty pending-prompt set is not a turn

- **WHEN** the pending-prompt set is empty
- **THEN** the orchestrator SHALL treat the platform as still resolving, SHALL prompt no seat, and SHALL NOT record a stall

#### Scenario: The orchestrator never advances a turn on a rules-enforcing platform

- **WHEN** a seat of a marvel-lcg session reports its turn complete
- **THEN** the orchestrator SHALL re-read the pending-prompt set rather than issuing any turn, phase, or round advancement
- **AND** it SHALL treat ending the turn as the seat's own enumerated option, already taken by that seat

#### Scenario: The platform's named seat overrides the orchestrator's record

- **WHEN** the orchestrator's prompt-tracked turn order disagrees with the seat the platform names as pending
- **THEN** the orchestrator SHALL follow the platform and SHALL record the disagreement rather than prompting the seat it expected

## MODIFIED Requirements

### Requirement: Separation of orchestrator and player authority
The orchestrator SHALL coordinate the game and SHALL NOT make a hero's play decisions. Each player agent SHALL decide and execute only its own hero's actions and SHALL NOT advance phases, resolve the villain phase, or act for another seat. This separation SHALL hold for every round so that each player agent's recorded moves reflect only that player's own decisions.

In an orchestrated session the card-ownership half of this separation SHALL be enforced by the server and SHALL NOT rest on the skill's instructions: a tool call from a seat that identifies another seat's cards SHALL be refused before the tool is invoked, whether the seat was instructed to make it, persuaded into it, or chose it. The instructions in the skill SHALL remain, because an agent that understands its scope plays better than one that discovers it through errors — but they are guidance layered over enforcement, not the enforcement itself.

The turn-and-phase half of the separation SHALL also be enforced by the server, after the fact, and SHALL be expressed per platform rather than against one platform's tool names and step ids. When a seat's tool call belongs to its platform's phase-advancing tool set or its platform's seat-action tool set, the runtime SHALL read the neutral phase classification from game state and, when the board is outside the player phase, SHALL record an illegal-action finding against that seat through the same findings store the `report_illegal_action` tool writes to. The call SHALL NOT be refused — detection is after the fact — and the finding SHALL be carried into every later invocation of that seat until the orchestrator resolves it, and SHALL reach the durable timeline as an `illegal_action` history event. The state read SHALL happen only for those phase-sensitive tools, SHALL use the same game-service state read the session already holds, and SHALL degrade to no finding rather than failing the job when the state cannot be read or the phase cannot be classified.

Which tools are phase-sensitive SHALL follow the platform. On DragnCards the phase-advancing tools are `next_step`, `prev_step`, `player_end_phase`, and `villain_end_phase`, and the acting player within the player phase is not a field in game state, so turn order within the player phase SHALL remain the orchestrator's prompt-tracked responsibility. On a platform where turns advance implicitly the phase-advancing set SHALL be empty, no seat SHALL be found in violation through a tool that platform does not have, and the platform's own pending-prompt set SHALL be the authority on whose turn it is.

#### Scenario: Orchestrator defers a hero decision to its seat
- **WHEN** it is a seat's turn during the player phase
- **THEN** the orchestrator SHALL prompt that seat's player agent and SHALL NOT choose which cards that hero plays

#### Scenario: Player agent stays within its seat
- **WHEN** a player agent takes its turn
- **THEN** the skill SHALL instruct it to act only on its own hero and its own cards, and to end its turn by reporting back rather than by advancing the game phase

#### Scenario: A seat reaching for another seat's cards is refused, not merely discouraged
- **WHEN** a player agent in an orchestrated session calls a tool identifying another seat's cards
- **THEN** the call SHALL be refused before the tool is invoked and the attempt SHALL be recorded on the seat's job

#### Scenario: A seat advancing the phase outside the player phase gets a finding
- **WHEN** a player agent in an orchestrated DragnCards session calls a phase-advancing tool while the board is outside the player phase
- **THEN** the call SHALL still be dispatched
- **AND** an open illegal-action finding SHALL be recorded against that seat, carried into its later invocations and emitted as an `illegal_action` history event

#### Scenario: A seat playing an action tool during the villain phase gets a finding
- **WHEN** a player agent in an orchestrated session calls a seat action tool of its platform while the phase classification is `villain`
- **THEN** the call SHALL still be dispatched
- **AND** an open illegal-action finding SHALL be recorded against that seat

#### Scenario: A seat acting during the player phase records no finding
- **WHEN** a player agent in an orchestrated session calls an action tool or a phase-advancing tool while the phase classification is `player`
- **THEN** no finding SHALL be recorded for that call

#### Scenario: A read-only or setup tool never records a finding
- **WHEN** a player agent calls a read-only tool (`get_game_state`, card search), a lifecycle tool (`create_game`, deck loading, `set_player_count_action`) or `mulligan_draw_hand` at any step
- **THEN** no finding SHALL be recorded for that call

#### Scenario: A platform with no phase-advancing tool produces no phase-advance findings
- **WHEN** a player agent in an orchestrated marvel-lcg session takes every action available to it for a whole round
- **THEN** no finding of the phase-advance kind SHALL be recorded, because that platform declares no phase-advancing tool

### Requirement: Orchestrated round structure matches the game rules
The orchestrator SHALL drive each round in the order defined by the Marvel Champions rules: the player phase in which every seat takes a turn in player order, the end of the player phase, the villain phase, passing the first player marker, and then the next round. That order is the game's, not a platform's, and SHALL hold on every platform.

How each transition is effected SHALL follow the platform, and the orchestrator SHALL NOT assume one mechanism. On a platform that enforces nothing and advances nothing by itself, the orchestrator SHALL perform the villain phase and each phase transition itself through that platform's tools rather than delegating them to a player agent. On a platform that adjudicates the rules and advances the game itself, the orchestrator SHALL NOT issue an advancement at all: it SHALL observe the transition in game state, and the villain phase SHALL be resolved by the engine rather than by the orchestrator. The orchestrator SHALL confirm each transition against game state on both, so a phase is never assumed to have happened because a call returned.

The round number the orchestrator reports SHALL be the neutral `playRound` carried on the game state, and the orchestrator SHALL NOT apply a per-platform correction of its own to it.

#### Scenario: Player phase prompts every seat in player order
- **WHEN** a round's player phase begins
- **THEN** the orchestrator SHALL prompt each seat's player agent in player order starting from the current first player
- **AND** SHALL wait for a seat to report its turn complete before prompting the next seat

#### Scenario: Villain phase is run by the orchestrator on a platform that enforces nothing
- **WHEN** every seat of a DragnCards session has completed its turn and the player phase has ended
- **THEN** the orchestrator SHALL resolve the villain phase through game-service tools, including villain and minion activations against each player and the dealing and revealing of encounter cards

#### Scenario: Villain phase is observed on a platform that resolves it
- **WHEN** every seat of a marvel-lcg session has completed its turn
- **THEN** the orchestrator SHALL observe the villain phase resolving in game state and SHALL issue no activation, encounter-dealing, or phase-advancing call
- **AND** it SHALL wait for the platform to ask a seat again rather than advancing the round

#### Scenario: First player marker passes each round
- **WHEN** the villain phase completes
- **THEN** the orchestrator SHALL pass the first player marker to the next player before beginning the following round on a platform that does not pass it itself, and SHALL observe the pass in game state on a platform that does

#### Scenario: The reported round is the neutral play round
- **WHEN** the orchestrator reports the round it reached
- **THEN** the number SHALL be the `playRound` carried on the neutral game state
- **AND** the orchestrator SHALL NOT add or subtract a platform-specific offset of its own
