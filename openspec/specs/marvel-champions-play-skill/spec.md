# Marvel Champions Play Skill Spec

## Purpose

This spec defines the content contract for `skills/marvel-champions-play/`, the
player-facing Marvel Champions skill loaded by a session agent that controls a single
hero. It covers what the skill must teach about the game-service harness, which tool-call
recipes it must supply, and which operations it must forbid.

Skill discovery, `load_skill`, and `load_skill_reference` mechanics belong in
`agent-orchestrator/spec.md` and `llm-capabilities/spec.md`. Game rules content belongs in
the `marvel-champions-rules-reference` skill, not here.
## Requirements
### Requirement: Player skill exists at a discoverable path
The repository SHALL ship a skill directory `skills/marvel-champions-play/` containing a `SKILL.md` whose frontmatter opens on line 1 with `---`, closes with `---`, and uses only flat `key: value` pairs plus at most one level of two-space nesting, so the agent-orchestrator frontmatter parser can read it. The frontmatter SHALL contain a single-line `description`.

#### Scenario: Skill is discovered from a configured skill root
- **WHEN** the agent-orchestrator scans a configured skill root that contains `marvel-champions-play/SKILL.md`
- **THEN** the skill SHALL be listed with identifier `marvel-champions-play`
- **AND** its summary SHALL be the single-line `description` from the frontmatter

#### Scenario: Skill is distinct from the coordination skill
- **WHEN** the skill catalogue is presented to an agent
- **THEN** `marvel-champions-play` SHALL describe controlling one hero during that hero's turn
- **AND** it SHALL NOT claim responsibility for round flow, phase transitions, or dispatching other players

### Requirement: Reference files are loadable markdown under the skill directory
The skill SHALL provide its detailed content as markdown files under `skills/marvel-champions-play/resources/`, each loadable individually by its path relative to the skill directory. `SKILL.md` SHALL name each reference file and state the condition under which the agent loads it.

#### Scenario: Reference inventory is returned with the skill
- **WHEN** an agent calls `load_skill("marvel-champions-play")`
- **THEN** the returned reference inventory SHALL include every `resources/*.md` file in the skill directory

#### Scenario: SKILL.md routes to references
- **WHEN** an agent reads `SKILL.md`
- **THEN** it SHALL find, for each reference file, the relative path and a stated trigger for loading it

### Requirement: Skill teaches the simplified game state contract
The skill SHALL document that `get_game_state` returns the Marvel Champions simplified projection and SHALL state, for each field an agent needs, how to map it to a game concept. It SHALL state explicitly that `players.<playerN>.hitPoints` is maximum hit points and not remaining hit points, that `players.<playerN>.handSize` is the target hand size for the identity's current form and not the number of cards held, and that `villainHitPoints` is the current villain stage's total hit points and not the villain's remaining hit points.

#### Scenario: Remaining hit points are derived, not read
- **WHEN** the skill explains how to determine a hero's remaining hit points
- **THEN** it SHALL instruct the agent to subtract the `damage` token count on the identity card from `players.<playerN>.hitPoints`

#### Scenario: Remaining villain hit points are derived, not read
- **WHEN** the skill explains how to determine the villain's remaining hit points
- **THEN** it SHALL instruct the agent to subtract the `damage` token count on the card in `sharedVillain` from `villainHitPoints`

#### Scenario: Absent tokens mean zero
- **WHEN** the skill explains the `tokens` object on a state card
- **THEN** it SHALL state that the object is sparse and that a missing token key SHALL be read as zero

#### Scenario: Hidden entries are not addressable
- **WHEN** the skill explains entries whose `name` is `HIDDEN`
- **THEN** it SHALL state that such an entry is a merged placeholder whose `instanceId` is inherited from the first stack in the group
- **AND** it SHALL forbid using that `instanceId` as a target for any action

### Requirement: Skill documents zone semantics for Marvel Champions groups
The skill SHALL provide the Marvel Champions group identifiers a player agent uses and state what each holds. It SHALL cover `playerNHand`, `playerNDeck`, `playerNDiscard`, `playerNPlay1`, `playerNPlay2`, `playerNEngaged`, `playerNEvent`, `sharedVillain`, `sharedMainScheme`, `sharedEncounterDeck`, and `sharedEncounterDiscard`. It SHALL state that moving a card into a deck group turns it facedown and moving it into a hand, discard, or play group turns it faceup.

#### Scenario: Engaged group contents are explained
- **WHEN** the skill describes `playerNEngaged`
- **THEN** it SHALL state that the group holds enemies engaged with that player, side schemes dealt to that player, and facedown boost cards

#### Scenario: Card side changes on move are explained
- **WHEN** the skill describes moving a card to `playerNDeck`
- **THEN** it SHALL state that the card is turned to its back automatically by the plugin

### Requirement: Skill teaches card detail lookup
The skill SHALL state that printed card values — cost, resource icon, attack, thwart, defense, hit points, hand size, recovery, traits, and rules text — are absent from the game state and SHALL instruct the agent to retrieve them with the Marvel Champions card search tool, matching the state card's `id` against the catalog record's `database_id`.

#### Scenario: Cost is looked up before a card is played
- **WHEN** the skill describes deciding whether a card in hand is affordable
- **THEN** it SHALL instruct the agent to search the card catalog for the card and read its `cost` and `resource` attributes

#### Scenario: Unavailable values are called out
- **WHEN** the skill describes reading the main scheme
- **THEN** it SHALL state that the target threat is not exposed by the game state and may be absent from the card catalog, and SHALL give the agent a fallback

### Requirement: Skill provides executable play recipes
The skill SHALL provide ordered tool-call sequences, with concrete argument names, for at minimum: paying a card's cost and playing an ally, upgrade, or support; playing an event; a basic attack; a basic thwart; defending against an attack; taking damage; recovering in alter-ego form; and changing form. Each recipe SHALL name the tool, the arguments, and the order of calls.

#### Scenario: Cost payment is an explicit step
- **WHEN** the skill describes playing a card with a printed cost
- **THEN** it SHALL instruct the agent to move one card per resource generated from `playerNHand` to `playerNDiscard` before moving the played card into play
- **AND** it SHALL state that the harness does not validate that the cost was paid

#### Scenario: Attack is an exhaust plus a token change
- **WHEN** the skill describes a basic attack
- **THEN** it SHALL instruct the agent to exhaust the attacking card and then add `damage` tokens equal to the attack value to the target card

#### Scenario: Thwart removes threat tokens
- **WHEN** the skill describes a basic thwart
- **THEN** it SHALL instruct the agent to exhaust the thwarting card and then apply a negative `threat` token change to the scheme card

### Requirement: Skill enumerates operations the player agent must not perform
The skill SHALL contain an explicit prohibition list naming the tools a single-hero player agent must never call, and SHALL state why. The list SHALL include the round and phase automation tools, the encounter and boost dealing tools, the deck and card loading tools, the session lifecycle tools, and the raw DragnLang escape hatch.

#### Scenario: Phase automation is prohibited
- **WHEN** the skill describes `player_end_phase`
- **THEN** it SHALL state that the tool readies and redraws for every player and advances the round, and SHALL forbid a player agent from calling it

#### Scenario: Other players' cards are off limits
- **WHEN** the skill describes targeting
- **THEN** it SHALL forbid moving, exhausting, readying, or modifying tokens on cards in another player's groups

### Requirement: Skill teaches the action result contract and recovery
The skill SHALL state that an action response always reports `success: true` and that the only failure signal is a non-null `error` string, and SHALL instruct the agent to read `error` after every mutating call. It SHALL state that the previous-step tool moves only the step marker and performs no undo, and SHALL describe correcting a mistake by issuing inverse actions.

#### Scenario: Error field is checked after every action
- **WHEN** the skill describes executing any mutating tool
- **THEN** it SHALL instruct the agent to treat a non-null `error` as a failed action regardless of the `success` value

#### Scenario: Previous-step is not an undo
- **WHEN** the skill describes recovering from a mistake
- **THEN** it SHALL state that the previous-step tool does not revert card moves, token changes, or exhaustion
- **AND** it SHALL give inverse-action sequences for the reversible mistakes

#### Scenario: Returning a card to a deck distinguishes shuffling from placing
- **WHEN** the skill describes returning a card to its deck
- **THEN** it SHALL direct the agent to the shuffle-into-deck tool for effects that say to shuffle the card in
- **AND** it SHALL direct the agent to the move tool with a top-of-deck destination for effects that say to place the card on top without shuffling
- **AND** it SHALL state that the shuffle-into-deck tool derives its destination from the card's own deck group and cannot be redirected

### Requirement: Skill provides an observable-driven turn procedure
The skill SHALL define a repeatable turn procedure that begins by reading state, decides between hero and alter-ego form, sequences plays and basic powers, and ends by reporting rather than by advancing the phase. It SHALL provide prioritisation heuristics expressed in terms of values the agent can actually observe.

#### Scenario: Turn begins with a state read
- **WHEN** the skill describes starting a turn
- **THEN** the first step SHALL be reading the game state and identifying the agent's own player identifier and zones

#### Scenario: Turn ends without phase advancement
- **WHEN** the skill describes finishing a turn
- **THEN** it SHALL instruct the agent to report that its turn is complete and to leave phase advancement to the coordinating agent or human

#### Scenario: Threat pressure is computed from observables
- **WHEN** the skill describes choosing between thwarting and attacking
- **THEN** the heuristic SHALL be expressed using the main scheme's `threat` token count, the per-round threat gain, and the villain's remaining hit points

### Requirement: The turn procedure states its entry conditions and refuses to guess them

The skill SHALL name the inputs a turn cannot start without — the seat identifier, the game-service session identifier, and which hero the seat controls — and SHALL instruct the agent to report the missing input and stop rather than infer it from the board. These entry conditions SHALL appear before the first ordered step of the procedure.

A player agent is prompted with no memory of previous turns, so every fact it needs arrives in the prompt or not at all. Inferring a seat is the specific failure this forbids: a board read shows every seat's zones, so a missing seat identifier looks answerable and is not.

#### Scenario: A turn prompt omits the seat

- **WHEN** the skill describes beginning a turn without a stated seat identifier
- **THEN** it SHALL instruct the agent to ask for the seat and take no mutating action
- **AND** it SHALL state that reading the board does not establish which seat the agent plays

#### Scenario: Entry conditions are listed before the first step

- **WHEN** an agent reads the turn procedure
- **THEN** the required inputs SHALL be stated before the first ordered step

### Requirement: Each step of the turn procedure states what confirms it

For each ordered step of the turn procedure the skill SHALL state the observation that confirms the step happened, SHALL state that the `error` field is read after every mutating call regardless of the reported `success` value, and SHALL instruct the agent to stop and diagnose when an observation does not match the step's intent.

A tool call that reports `success: true` may still have done nothing, so a procedure without an observation after each step cannot tell a completed step from a silently failed one.

#### Scenario: A step names its confirming observation

- **WHEN** the skill describes an ordered step that mutates the board
- **THEN** it SHALL state what the agent reads back to confirm that step took effect

#### Scenario: An unconfirmed step halts the sequence

- **WHEN** the observation after a step does not match what the step intended
- **THEN** the skill SHALL instruct the agent to stop and diagnose before issuing further actions

### Requirement: The turn procedure states its stop conditions

The skill SHALL enumerate the conditions under which a turn ends — the agent has nothing further it can pay for or usefully do, its hero is defeated, the villain stage or the main scheme reached a terminal value, or an unrecoverable error occurred — and SHALL state that in every case the turn ends by reporting and never by advancing a phase or refilling a hand. It SHALL provide a completion check answerable from the board rather than from the agent's intent.

An agent that does not know when its turn is over either keeps acting or advances the phase, and phase advancement by a seat mutates every player's board.

#### Scenario: A terminal board state ends the turn

- **WHEN** the skill describes reducing the villain stage to zero hit points or the agent's own hero being defeated
- **THEN** it SHALL instruct the agent to stop acting and report immediately, leaving stage advancement and elimination handling to the coordinator

#### Scenario: Done is defined

- **WHEN** an agent asks whether its turn is finished
- **THEN** the skill SHALL provide a stated completion check that is answerable from the board

### Requirement: The skill states what to do when a step fails and when to ask rather than guess

The skill SHALL provide an ordered failure response covering a non-null `error`, a board that does not match the agent's intent, a mistake that cannot be reversed with the agent's own tools, and the point at which the agent stops acting and reports. It SHALL also name the facts an agent must ask for rather than assume, including the main scheme's target threat, which the game state does not expose and which may be absent from the card catalogue.

#### Scenario: A failed action does not become a retry loop

- **WHEN** a mutating call returns a non-null `error`
- **THEN** the skill SHALL instruct the agent to re-read state before acting again rather than reissuing the same call

#### Scenario: An unfixable board is reported, not improvised around

- **WHEN** a mistake cannot be reversed with the tools a seat holds
- **THEN** the skill SHALL instruct the agent to state what happened, what the board shows, and what the correct board would be, and to stop

#### Scenario: An unknown value is asked for once

- **WHEN** a decision needs a value the state does not expose
- **THEN** the skill SHALL instruct the agent to ask for it and remember it rather than estimate it

### Requirement: The skill states which guardrails are enforced by the server and which are not

The skill SHALL distinguish the seat-scope refusals the server applies before a tool runs from the rules of play that nothing checks. It SHALL state that a call naming another seat's identifier, another seat's `playerN`-prefixed group, or a player-identifying argument carrying another seat's value is refused before dispatch and recorded against the job, and that a refusal is corrected by reissuing the call within the agent's own seat rather than by explanation or a claim of permission. It SHALL state that turn order, phase authority, resource cost payment, the once-per-turn form change, and the hand limit are enforced nowhere.

An agent that believes every rule is enforced treats a silent success as permission.

#### Scenario: A refusal is described as correctable

- **WHEN** the skill describes a seat-scope refusal
- **THEN** it SHALL state that the refusal names the offending argument and that the agent reissues the call with its own seat's identifiers

#### Scenario: Unenforced rules are named as the agent's own responsibility

- **WHEN** the skill describes paying a card's cost or advancing a phase
- **THEN** it SHALL state that nothing in the harness validates it and that a missed cost is cheating rather than an error

### Requirement: The skill documents the seat's view of illegal-action findings

The skill SHALL describe the illegal-action findings loop from the seat's side: that a finding recorded against the seat is presented at the start of every turn until it is closed, that the seat can list the open findings against it, that the seat performs the stated undo with its own tools before taking new actions, and that only the coordinating agent closes a finding.

#### Scenario: A seat carrying an open finding acts on it first

- **WHEN** the skill describes starting a turn while a finding is open against the agent's seat
- **THEN** it SHALL instruct the agent to perform the stated undo before taking new actions and to report that it did

#### Scenario: A seat cannot resolve its own finding

- **WHEN** the skill describes closing a finding
- **THEN** it SHALL state that only the coordinating agent resolves one, after verifying the undo against game state

