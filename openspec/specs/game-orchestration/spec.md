# game-orchestration Specification

## Purpose

This spec describes how a full cooperative Marvel Champions game is orchestrated across multiple agents: an orchestrator agent session that owns the round loop, the phase transitions, the villain phase, and the meta bookkeeping, coordinating one player agent per seat that plays a single hero and nothing else.

The separation of authority between orchestrator and player agents is the point of the capability: it is what makes each seat's recorded play attributable, evaluable, and comparable against a differently configured seat that played the same game.

The mechanics that make this possible — the per-seat configuration API, child session spawning, and player identity on recorded moves — belong in `agent-orchestrator/spec.md`. The tools the orchestrator uses to do it belong in `llm-capabilities/spec.md`. How the resulting play is scored belongs in `agent-move-evaluation/spec.md`.

## Requirements

### Requirement: Orchestrator skill for cooperative Marvel Champions games
The system SHALL provide a `marvel-champions-orchestrator` skill that instructs an agent session how to run a complete cooperative Marvel Champions game with one agent per player seat. The skill SHALL be discoverable by name through the skill catalogue and assignable to a session like any other skill.

#### Scenario: Skill is discoverable and loadable
- **WHEN** a client lists the available skills
- **THEN** `marvel-champions-orchestrator` SHALL appear with a description identifying it as the multi-player game orchestrator
- **AND** an agent whose session has the skill enabled SHALL be able to load its content with `load_skill`

#### Scenario: Skill exposes its references
- **WHEN** the orchestrator agent loads the skill
- **THEN** the returned content SHALL list the skill's reference files
- **AND** each listed reference SHALL be loadable with `load_skill_reference`

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

#### Scenario: Villain phase is run by the orchestrator
- **WHEN** every seat of a DragnCards session has completed its turn and the player phase has ended
- **THEN** the orchestrator SHALL resolve the villain phase through game-service tools, including villain and minion activations against each player and the dealing and revealing of encounter cards

#### Scenario: First player marker passes each round
- **WHEN** the villain phase completes
- **THEN** the orchestrator SHALL pass the first player marker to the next player before beginning the following round on a platform that does not pass it itself, and SHALL observe the pass in game state on a platform that does

#### Scenario: The reported round is the neutral play round
- **WHEN** the orchestrator reports the round it reached
- **THEN** the number SHALL be the `playRound` carried on the neutral game state
- **AND** the orchestrator SHALL NOT add or subtract a platform-specific offset of its own

### Requirement: Orchestrator detects and reports game end
The orchestrator SHALL check for the game's win and loss conditions each round and SHALL stop the round loop and report the outcome when one is met.

#### Scenario: Players win
- **WHEN** the final villain stage has no hit points remaining
- **THEN** the orchestrator SHALL stop prompting players and SHALL report that the players won, together with the round number reached

#### Scenario: Villain wins
- **WHEN** threat on the final main scheme reaches its target, or every player has been defeated
- **THEN** the orchestrator SHALL stop prompting players and SHALL report that the villain won, together with the round number reached

### Requirement: Comparable per-seat play
Because each seat is played by an independently configured agent whose moves are attributed to that seat on the recorded timeline, the system SHALL make it possible to evaluate and compare two configurations that played the same game.

#### Scenario: Two configurations play one game
- **WHEN** an orchestrator session is configured with two player agents that differ in model, reasoning effort, or skills
- **THEN** each seat's moves SHALL be recorded against that seat
- **AND** an evaluation of that game SHALL be able to produce a separate result per seat

### Requirement: The orchestrator skill states the entry conditions for starting a game

The orchestrator skill SHALL state the conditions that must hold before any game-service call is made — a roster of configured seats exists, every seat's identifier is known, and the game's player count equals the roster size — and SHALL instruct the agent to stop and report rather than proceed when one does not hold. It SHALL forbid entering the round loop until every seat has a deck, a hand, and a confirmed hero assignment.

An orchestrator that begins setup against an unconfigured or mismatched roster produces a game no seat can play and no evaluation can compare.

#### Scenario: No seats are configured

- **WHEN** the roster check returns no configured player agents
- **THEN** the skill SHALL instruct the orchestrator to stop and report that seats must be configured, and SHALL forbid it playing the game itself

#### Scenario: Setup is not complete

- **WHEN** setup has run but a seat lacks a deck, a hand, or a confirmed hero assignment
- **THEN** the skill SHALL forbid entering the round loop until every seat has all three

### Requirement: The orchestrator skill states a stop condition for every loop it runs

The orchestrator skill SHALL state a termination for each of the three loops it runs. The round loop SHALL end on a terminal game condition, with no seat prompted after one is reached. The seat loop SHALL end when every non-defeated seat has reported. A seat's turn SHALL end when that seat reports rather than when the orchestrator decides it has.

#### Scenario: A terminal condition stops the loop immediately

- **WHEN** a win or loss condition is met at any point in a round
- **THEN** the skill SHALL instruct the orchestrator to stop the loop at once and emit the final report, without completing the round

#### Scenario: Progress through the seat loop is verified

- **WHEN** a seat has been prompted
- **THEN** the skill SHALL require the orchestrator to have received that seat's completed report before prompting the next seat

### Requirement: The orchestrator skill handles the ways a seat actually fails

The orchestrator skill SHALL describe a bounded response covering a seat that returns an invalid report, a seat that returns nothing, and a seat the orchestrator has already given up waiting on, and SHALL state in each case what is recorded and when the game aborts. It SHALL forbid waiting again on a seat whose wait was already abandoned, and SHALL forbid the orchestrator playing a failed seat's turn under any circumstance.

A seat is a child job, and a child job fails in more ways than returning a bad report: it can crash inside its own failure handling, exhaust its tool-round limit and end as interrupted, be orphaned while still marked running, or stream continuously while making no progress. A turn the orchestrator played is not that seat's recorded play.

#### Scenario: A seat returns no valid report twice

- **WHEN** a seat fails to return a valid turn report on two consecutive attempts
- **THEN** the skill SHALL instruct the orchestrator to abort the game and report the round reached, the seat, both failure modes, and the board state at abort

#### Scenario: An abandoned wait is not retried

- **WHEN** the orchestrator has stopped waiting on a seat's job
- **THEN** the skill SHALL instruct it to continue without that result or report the stall, and SHALL forbid waiting on the same job again

### Requirement: The orchestrator skill documents the illegal-action findings loop

The orchestrator skill SHALL describe the findings loop the runtime provides: legality SHALL be decided from game state and never from what a seat reported; a finding SHALL name the violation and the concrete undo; the seat SHALL perform the undo with its own tools; and the finding SHALL be closed only after the orchestrator has read game state and observed the undo. The skill SHALL state that the orchestrator never performs a seat's undo for it.

#### Scenario: A violation is established from state, not from a report

- **WHEN** a seat's report describes an action the orchestrator suspects was illegal
- **THEN** the skill SHALL instruct the orchestrator to read game state to confirm it before recording a finding

#### Scenario: A finding is closed only against observed state

- **WHEN** a seat reports that it has undone a recorded violation
- **THEN** the skill SHALL instruct the orchestrator to verify the undo against game state before closing the finding, and SHALL state that the seat's claim is not the verification

### Requirement: The orchestrator skill states that seat output is data, not instruction

The orchestrator skill SHALL state that a seat's report, and any seat-to-seat message, carries no authority over the rules, the phase order, the turn order, or what is legal, and that a claim within one that a move was permitted or that a rule does not apply SHALL be treated as a claim to verify against game state.

#### Scenario: A seat's report asserts a rule

- **WHEN** a seat's report claims an action was allowed or that a violation was already corrected
- **THEN** the skill SHALL instruct the orchestrator to treat the claim as unverified and to check game state

#### Scenario: A seat's report asks for a procedural change

- **WHEN** a seat's report asks for an extra turn, a different turn order, or a skipped phase
- **THEN** the skill SHALL instruct the orchestrator to disregard the request and continue the round loop as specified

### Requirement: Orchestrated play is opt-in and does not replace the chat flow
A full orchestrated game SHALL be available only for a session whose recorded mode is `orchestrated`, chosen when the session is created. The existing single-agent chat flow SHALL remain the default and SHALL be unchanged by the existence of orchestrated mode: a session that does not opt in SHALL run exactly as it did before, with the same tools, the same subagent behaviour, and the same session lifecycle.

A user SHALL be able to make the choice at session-creation time rather than discovering it later, and the choice SHALL be visible on the session afterwards.

#### Scenario: A chat session is unaffected
- **WHEN** a session in `chat` mode runs a prompt
- **THEN** its available tools, its subagent behaviour, and its session lifecycle SHALL be those of the pre-orchestration flow

#### Scenario: Orchestrated behaviour requires the mode
- **WHEN** a session in `chat` mode runs a prompt
- **THEN** the player-to-player messaging tool SHALL NOT be available and no seat scoping SHALL be applied

### Requirement: Each seat is a durable agent for the length of the game
An orchestrated game SHALL run one persistent agent per seat, retaining its context between invocations for the whole game, so a hero's plan can span rounds. A seat prompted in a later round SHALL still know what it drew, played, and discarded earlier, and what other seats told it.

A seat SHALL be a seat identifier, a persona, a model configuration, and a persistent session together. Two seats at the same table SHALL be able to differ in persona and in model, so a game can compare how differently configured players play the same scenario.

#### Scenario: A seat's plan survives a round boundary
- **WHEN** a seat states a plan in one round and is prompted again in the next
- **THEN** its earlier statement SHALL be part of the context of the later invocation

#### Scenario: Seats differ in persona and model
- **WHEN** two seats are configured with different personas and different models
- **THEN** each SHALL play with its own persona and its own model for the whole game

### Requirement: Players communicate with each other, and only with each other
An orchestrated game SHALL let seats coordinate directly: a seat SHALL be able to send a message to another seat at the same table, and SHALL receive messages addressed to it when it next plays. This is what makes cooperative play cooperative — deciding who thwarts and who attacks is a conversation between players.

No channel SHALL exist from a player agent to the orchestrator other than the seat's own report of what it did. A seat SHALL NOT be able to address the orchestrator, and a message a seat sends SHALL NOT be routed to the orchestrator by any recipient value.

#### Scenario: Two seats coordinate before acting
- **WHEN** one seat sends another a message proposing a division of labour and the recipient is then prompted
- **THEN** the recipient's invocation SHALL include that message attributed to the sending seat

#### Scenario: There is no path from a player to the orchestrator
- **WHEN** a player agent looks for a way to address the orchestrator
- **THEN** no tool and no recipient value SHALL provide one

### Requirement: An illegal action is reported by the orchestrator and undone by the seat that made it
When the orchestrator determines from game state that a seat's action violated the rules, it SHALL record a finding naming the seat, what was violated, and what must be undone. The finding SHALL be carried into that seat's next invocation, and every invocation after it, until resolved.

The seat that made the illegal action SHALL be the party that undoes it, using its own tools within its own seat scope. The orchestrator SHALL NOT reach into a seat's cards to correct it, because doing so would hold the write authority over another party's cards that this capability exists to remove.

The orchestrator SHALL resolve a finding only after verifying against game state that the required undo happened. A seat's report that it has undone the action SHALL NOT resolve the finding on its own.

A recovery-only invocation SHALL neither grant nor consume a player turn. When a finding arises from
a seat's completed turn report, the orchestrator SHALL resolve it and resume the current seat loop
with the next seat; it SHALL NOT replay that seat's ordinary turn. The recovered seat SHALL receive
its next normal-play prompt only in its ordinary later seat-loop pass.

#### Scenario: A violation is reported to the seat that made it
- **WHEN** the orchestrator finds that a seat played a card it could not afford
- **THEN** it SHALL record a finding against that seat naming the violation and the required undo
- **AND** the seat's next invocation SHALL carry the finding

#### Scenario: The seat performs its own revert
- **WHEN** a seat is prompted carrying an open finding
- **THEN** the seat SHALL perform the undo with its own tools and report back
- **AND** the orchestrator SHALL NOT perform the undo itself

#### Scenario: A finding is resolved only after verification
- **WHEN** a seat reports that it has undone the action
- **THEN** the orchestrator SHALL confirm the undo against game state before resolving the finding

#### Scenario: An unresolved finding keeps following the seat
- **WHEN** a seat with an open finding is prompted twice without the undo being verified
- **THEN** both invocations SHALL carry the finding

#### Scenario: Recovery after a completed turn does not replay the turn
- **WHEN** a finding is raised from a seat's completed turn report and the seat completes recovery
- **THEN** the orchestrator SHALL continue the current seat loop with the next seat
- **AND** SHALL not send the recovered seat another ordinary turn prompt in that round

### Requirement: The orchestrator's rule-following cannot be argued away by a player
The orchestrator SHALL treat everything a player agent produces as a report of observations, and SHALL NOT treat any of it as an instruction, a permission, or a statement of what the rules are. A seat asserting that a rule does not apply, that the orchestrator previously agreed to something, or that its move should be allowed SHALL have exactly the effect of a seat saying nothing: the orchestrator's decision comes from the rules it holds and the game state it reads.

This SHALL be achieved by where player text is placed rather than by the orchestrator being asked to resist persuasion: player text SHALL never occupy a position in the orchestrator's context where instructions are read, and SHALL always arrive labelled as untrusted seat output.

#### Scenario: A persuasive report changes nothing
- **WHEN** a seat's report claims the orchestrator should skip the villain phase
- **THEN** the orchestrator SHALL run the villain phase as the rules require

#### Scenario: Player text never occupies an instruction position
- **WHEN** a seat's report is delivered
- **THEN** it SHALL arrive as labelled data in a tool result and SHALL NOT be placed in the orchestrator's system prompt or read as a directive

### Requirement: The orchestrator skill treats verified state as authoritative

The orchestrator skill SHALL require a game-state checkpoint before each player-turn prompt and
after each phase-changing or scenario-changing operation. A prompt and round summary SHALL use
only facts observed at the most recent checkpoint or results verified against it; a seat report
SHALL remain untrusted data and SHALL NOT establish card locations, hit points, threat, round, or
phase facts. If a checkpoint contradicts the last verified phase, card location, or key board
total and the discrepancy cannot be reconciled by one fresh state read, the skill SHALL instruct
the orchestrator to abort the game and report the discrepancy and last verified board.

#### Scenario: A player prompt is built from a checkpoint
- **WHEN** the orchestrator schedules a seat's turn
- **THEN** the skill SHALL require its board facts to come from the latest verified state checkpoint
- **AND** SHALL forbid filling missing facts by extrapolating from a seat report

#### Scenario: A contradiction cannot be reconciled
- **WHEN** two state reads disagree about the current phase, a card's location, or a key board total
- **THEN** the skill SHALL require one fresh read to reconcile the disagreement
- **AND** SHALL require the game to abort if that read does not establish a consistent board

### Requirement: The orchestrator skill closes findings by recorded identifier

The orchestrator skill SHALL retain the identifier returned when it records an illegal-action
finding. It SHALL direct the owning seat to perform that finding's concrete undo, verify the undo
against game state, and resolve that exact identifier before the seat receives another normal-play
prompt. The skill SHALL require later prompts to contain only findings still open for their target
seat and SHALL forbid repeating a resolved finding as an active constraint.

#### Scenario: An undo is verified and closed
- **WHEN** a seat reports that it performed an undo for a finding
- **THEN** the skill SHALL require the orchestrator to verify the undo in game state and resolve the
  identifier returned for that finding before scheduling the seat's next normal turn

#### Scenario: A resolved finding is absent from a later prompt
- **WHEN** the orchestrator has resolved a finding identifier
- **THEN** the skill SHALL require the next normal-play prompt for that seat to omit that finding

### Requirement: The orchestrator skill gates phase progression on encounter resolution

The orchestrator skill SHALL require every encounter card dealt during the villain phase to be
revealed and resolved in the prescribed player order before it advances the phase. It SHALL require
a verified state checkpoint after the encounter queue is resolved and SHALL abort rather than
progress when facedown encounter cards or their required effects remain unexplained.

#### Scenario: Encounter cards are resolved before the phase ends
- **WHEN** the villain phase deals one or more encounter cards
- **THEN** the skill SHALL require the orchestrator to reveal and resolve each card before advancing
  the phase

#### Scenario: Encounter state remains unresolved
- **WHEN** the post-encounter checkpoint shows unexplained facedown encounter cards or unresolved
  required effects
- **THEN** the skill SHALL require the orchestrator to abort the game and report the unresolved
  encounter state

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

### Requirement: Orchestrated setup uses discovered typed selections

The orchestrator skill SHALL require setup discovery through `list_game_setup_catalog` before
creating a game. It SHALL select a scenario id and an ordered list of each configured neutral seat
and its requested hero-deck id, then pass those values in the outer `setup` field of the typed
`create_game` specification. The roster SHALL be the contiguous `player1`..`playerN` prefix. It
SHALL not hardcode a Marvel hero, choose the first catalog entry, infer a deck
from a prompt after creation, or enter the round loop until the returned setup metadata and state
confirm every seat's requested hero.

#### Scenario: A prompted roster controls the created heroes

- **WHEN** an orchestrator has a roster requesting hero deck `H1` for `player1` and `H2` for
  `player2`
- **THEN** it SHALL discover those ids, create the game with the ordered typed setup, and verify
  that the resulting state assigns `H1` and `H2` to the corresponding seats
- **AND** it SHALL not substitute a fixed or first-listed hero

#### Scenario: Setup cannot be inferred after creation

- **WHEN** the returned setup metadata or state does not confirm a configured seat's requested
  hero
- **THEN** the orchestrator SHALL stop and report the mismatch
- **AND** it SHALL not enter the round loop or silently continue with the wrong hero

#### Scenario: Missing setup data stops the orchestrator

- **WHEN** a configured seat has no valid hero-deck id or the catalog does not contain a requested
  scenario/deck
- **THEN** the orchestrator SHALL report the missing or invalid selection
- **AND** it SHALL not create a game using a catalog default

### Requirement: The orchestrator selects moves from declared platform capabilities

The orchestrator SHALL read `platform` and `move_surface` from the created session metadata and
shall use only the surface declared for that session. It SHALL retain DragnCards typed-action
setup and phase tools, and shall use Marvel's enumerated option tools with their `player_n`
argument and required prompt identity when the session declares `move_surface: enumerated_options`.

#### Scenario: Marvel setup does not call DragnCards actions

- **WHEN** a created session declares `platform: marvel-lcg` and
  `move_surface: enumerated_options`
- **THEN** the orchestrator SHALL not issue DragnCards typed setup or raw DragnLang actions
- **AND** it SHALL use the neutral state and enumerated option contract instead

#### Scenario: Capability metadata is authoritative for dispatch

- **WHEN** a session's available tool list is incomplete or cached
- **THEN** the orchestrator SHALL use the session metadata and server-side refusal as authority
- **AND** it SHALL not infer that one backend can accept the other backend's move surface
