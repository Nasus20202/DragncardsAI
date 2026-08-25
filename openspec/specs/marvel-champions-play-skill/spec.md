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
The skill SHALL document that `get_game_state` returns the platform-neutral simplified projection of a Marvel Champions board and SHALL state, for each field an agent needs, how to map it to a game concept. It SHALL state that the projection has the same shape on every platform, that the fields whose meaning is a property of the harness rather than of the game are documented in the platform harness reference, and that the agent loads that reference before relying on a derived value.

The skill SHALL state that the projection names the platform the state came from, carries the play round directly as `playRound` so no per-platform correction is applied to it, carries a neutral `phase` classification together with the platform's own `phaseLabel`, and carries the platform's step identifier as an opaque value that SHALL NOT be parsed or compared against another platform's vocabulary.

#### Scenario: Remaining hit points are derived, not read
- **WHEN** the skill explains how to determine a hero's remaining hit points
- **THEN** it SHALL instruct the agent to subtract the `damage` token count on the identity card from the projected identity hit points where the platform harness reference states the projected value is a maximum

#### Scenario: Remaining villain hit points are derived, not read
- **WHEN** the skill explains how to determine the villain's remaining hit points
- **THEN** it SHALL instruct the agent to subtract the `damage` token count on the villain card from the projected villain hit points where the platform harness reference states the projected value is a stage total

#### Scenario: The play round is read, not computed
- **WHEN** the skill explains how to determine which round is being played
- **THEN** it SHALL instruct the agent to read `playRound` as the round being played
- **AND** it SHALL forbid adding or subtracting an offset of its own

#### Scenario: The step identifier is not interpreted
- **WHEN** the skill explains the projection's step identifier
- **THEN** it SHALL state that its spelling is the platform's own, that the neutral `phase` classification is what the agent reasons about, and that the identifier SHALL NOT be parsed

#### Scenario: Absent tokens mean zero
- **WHEN** the skill explains the `tokens` object on a state card
- **THEN** it SHALL state that the object is sparse and that a missing token key SHALL be read as zero

#### Scenario: Hidden entries are not addressable
- **WHEN** the skill explains entries whose `name` is `HIDDEN`
- **THEN** it SHALL state that such an entry is a merged placeholder whose `instanceId` is inherited from the first stack in the group
- **AND** it SHALL forbid using that `instanceId` as a target for any action

### Requirement: Skill documents zone semantics for Marvel Champions groups
The skill SHALL provide the neutral zone vocabulary a player agent reasons about and state what each zone holds: the seat's hand, deck, discard pile, cards it controls in play, the enemies engaged with it, the villain, the main scheme, and the shared encounter deck and discard pile. It SHALL state that a zone is identified by its meaning rather than by any platform's name for it, that each seat's own zones are distinguished from shared zones, and that a seat acts on its own zones and on shared zones only.

The platform's own zone names, the identifiers used to address a zone, and the side a card shows when it is moved SHALL be stated in the platform harness reference rather than in the skill body, because those are properties of the harness and differ entirely between platforms: one addresses zones by group identifier and turns a card facedown on a move into a deck, the other exposes no zone identifier at all and never lets a client move a card directly.

#### Scenario: Engaged zone contents are explained
- **WHEN** the skill describes the zone holding a seat's engaged enemies
- **THEN** it SHALL state that the zone holds enemies engaged with that seat, side schemes dealt to that seat, and any facedown cards the platform places there

#### Scenario: Engaged group contents are explained
- **WHEN** the skill describes the zone holding a seat's engaged enemies
- **THEN** it SHALL state that the neutral zone holds enemies engaged with that seat, side schemes dealt to that seat, and any facedown cards the platform places there

#### Scenario: Zone naming is deferred to the platform reference
- **WHEN** the skill describes addressing a zone in a tool call
- **THEN** it SHALL direct the agent to the platform harness reference for the identifiers that platform uses
- **AND** the skill body SHALL name no platform's zone identifier

#### Scenario: Card side changes on move are explained where they exist
- **WHEN** the platform harness reference describes moving a card into a deck zone on a platform that permits it
- **THEN** it SHALL state which side the card shows afterwards and whether the platform does it automatically

#### Scenario: Card side changes on move are explained
- **WHEN** the platform harness reference describes moving a card into a deck zone on a platform that permits it
- **THEN** it SHALL state which side the card shows afterwards and whether the platform does it automatically

### Requirement: Skill teaches card detail lookup
The skill SHALL state that printed card values — cost, resource icon, attack, thwart, defense, hit points, hand size, recovery, traits, and rules text — are absent from the game state and SHALL instruct the agent to retrieve them with the Marvel Champions card search tool, matching the state card's `id` against the catalog record's `database_id`.

#### Scenario: Cost is looked up before a card is played
- **WHEN** the skill describes deciding whether a card in hand is affordable
- **THEN** it SHALL instruct the agent to search the card catalog for the card and read its `cost` and `resource` attributes

#### Scenario: Unavailable values are called out
- **WHEN** the skill describes reading the main scheme
- **THEN** it SHALL state that the target threat is not exposed by the game state and may be absent from the card catalog, and SHALL give the agent a fallback

### Requirement: Skill provides executable play recipes
The skill SHALL provide, for each of the plays a hero makes — paying a card's cost and playing an ally, upgrade, or support; playing an event; a basic attack; a basic thwart; defending against an attack; taking damage; recovering in alter-ego form; and changing form — what the play means in game terms and what the board looks like afterwards. It SHALL then state that the ordered calls that perform each play belong to the platform harness reference, and SHALL provide the ordered calls, with concrete argument names, once per platform in that reference.

The two platforms do not share a move surface and SHALL NOT be given a shared recipe. On a platform that validates nothing, a recipe SHALL be an ordered sequence of composed calls that together produce the board a legal play would produce, including the cost payment as an explicit step the harness does not check. On a platform that enumerates legal moves, a recipe SHALL instead be the observation that names the option to choose and the targets to select within the option's range, because the engine performs the play and no sequence of board mutations is composed at all.

#### Scenario: Cost payment is an explicit step where nothing checks it
- **WHEN** the DragnCards harness reference describes playing a card with a printed cost
- **THEN** it SHALL instruct the agent to discard one card per resource generated from its own hand before moving the played card into play
- **AND** it SHALL state that the harness does not validate that the cost was paid

#### Scenario: Cost payment is an explicit step
- **WHEN** the skill describes playing a card with a printed cost on a platform that does not validate payment
- **THEN** it SHALL direct the agent to the platform reference, where payment is an explicit discard step before the card is moved into play
- **AND** it SHALL state that the harness does not validate that the cost was paid

#### Scenario: Cost payment is part of the option where the engine checks it
- **WHEN** the marvel-lcg harness reference describes playing a card with a printed cost
- **THEN** it SHALL state that the payment is part of the option the engine offers, that an option offered is an option affordable, and that no separate discard is composed

#### Scenario: A neutral recipe states the outcome, not the calls
- **WHEN** an agent reads a play in the skill body
- **THEN** it SHALL find what the play means and what the board shows afterwards, and SHALL be directed to its platform's reference for the calls

#### Scenario: Attack is described per platform
- **WHEN** each harness reference describes a basic attack
- **THEN** the DragnCards reference SHALL give the exhaust and the damage-token change as ordered calls
- **AND** the marvel-lcg reference SHALL give the attack as an enumerated option chosen with its target selected within the option's range

#### Scenario: Attack is an exhaust plus a token change
- **WHEN** the DragnCards harness reference describes a basic attack
- **THEN** it SHALL give the exhaust and the damage-token change as ordered calls

#### Scenario: Thwart removes threat tokens
- **WHEN** the DragnCards harness reference describes a basic thwart
- **THEN** it SHALL give the exhaust and the negative threat-token change as ordered calls

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
The skill SHALL state which guardrails hold, and SHALL distinguish three kinds: the seat-scope refusals the orchestrator applies before a tool runs, which hold on every platform; the rules of play, whose enforcement is a property of the platform; and the turn authority, which is a property of the platform. It SHALL state that the agent reads its platform harness reference to learn which rules of play are enforced, and SHALL forbid assuming either answer.

It SHALL state that a call naming another seat's identifier, another seat's zone, or a player-identifying argument carrying another seat's value is refused before dispatch and recorded against the job, and that a refusal is corrected by reissuing the call within the agent's own seat rather than by explanation or a claim of permission.

It SHALL state, for a platform that validates nothing, that turn order, phase authority, resource cost payment, the once-per-turn form change, and the hand limit are enforced nowhere and that a missed cost is cheating rather than an error. It SHALL state, for a platform that adjudicates the rules, that those same rules are enforced, that the only moves offered are legal ones, and that the failure mode is inverted: an illegal submission is not refused with an error but discarded in silence and asked again, so the agent confirms a move by the prompt changing rather than by a success field.

An agent that believes every rule is enforced treats a silent success as permission; an agent that believes none are enforced composes board mutations a rules engine will discard.

#### Scenario: A refusal is described as correctable

- **WHEN** the skill describes a seat-scope refusal
- **THEN** it SHALL state that the refusal names the offending argument and that the agent reissues the call with its own seat's identifiers

#### Scenario: Unenforced rules are named as the agent's own responsibility

- **WHEN** the DragnCards harness reference describes paying a card's cost or advancing a phase
- **THEN** it SHALL state that nothing in the harness validates it and that a missed cost is cheating rather than an error

#### Scenario: Enforced rules are named as the platform's responsibility

- **WHEN** the marvel-lcg harness reference describes paying a card's cost or ending a turn
- **THEN** it SHALL state that the engine enforces it and that the agent chooses among the legal options the engine offers rather than composing the play

#### Scenario: The agent does not assume which kind of platform it is on

- **WHEN** an agent reads the skill body
- **THEN** it SHALL be instructed to load its platform's harness reference before relying on any rule being enforced or unenforced

### Requirement: The skill documents the seat's view of illegal-action findings

The skill SHALL describe the illegal-action findings loop from the seat's side: that a finding recorded against the seat is presented at the start of every turn until it is closed, that the seat can list the open findings against it, that the seat performs the stated undo with its own tools before taking new actions, and that only the coordinating agent closes a finding.

#### Scenario: A seat carrying an open finding acts on it first

- **WHEN** the skill describes starting a turn while a finding is open against the agent's seat
- **THEN** it SHALL instruct the agent to perform the stated undo before taking new actions and to report that it did

#### Scenario: A seat cannot resolve its own finding

- **WHEN** the skill describes closing a finding
- **THEN** it SHALL state that only the coordinating agent resolves one, after verifying the undo against game state

### Requirement: The player skill quarantines active findings from normal play

The player skill SHALL instruct a seat that receives an active illegal-action finding to identify
the finding, perform its concrete undo with its own tools, confirm the undo from game state, and
report the recovery. It SHALL forbid ordinary card plays, basic powers, and further turn planning
in that invocation after the recovery; the seat SHALL wait for a later normal-play prompt that no
longer carries the finding. The skill SHALL state that only the coordinating agent resolves the
finding. A recovery-only invocation SHALL neither grant nor consume a player turn; when it follows
the seat's completed report, the seat's later normal-play prompt occurs only in its ordinary next
seat-loop pass.

#### Scenario: A seat receives an active finding
- **WHEN** a player-turn prompt carries an active finding for the seat
- **THEN** the skill SHALL instruct the seat to perform and confirm the stated undo, report the
  recovery, and take no ordinary turn actions

#### Scenario: A finding remains listed after recovery
- **WHEN** a seat re-reads its findings after performing the undo and the same finding remains open
- **THEN** the skill SHALL instruct the seat to report its identifier and observed state without
  repeating the undo or taking ordinary actions

### Requirement: The player skill reports unreliable state instead of guessing

The player skill SHALL instruct a seat to stop and report a discrepancy when its current state read
contradicts the prompt's claimed phase, card location, or key board total, or when it cannot
identify a required card or value from the board. It SHALL forbid treating hidden entries, stale
prompt text, or a previous report as authoritative evidence for an action.

#### Scenario: A prompt and board disagree
- **WHEN** a seat's state read disagrees with the prompt about its phase, a relevant card location,
  or a key board total
- **THEN** the skill SHALL instruct the seat to take no mutating action and report the discrepancy

#### Scenario: Required board information is unavailable
- **WHEN** a seat cannot identify information required to execute an action from the current state
- **THEN** the skill SHALL instruct the seat to report the missing information and refrain from
  guessing or choosing a conservative action solely because of that uncertainty

### Requirement: A DragnCards harness reference carries that platform's group catalogue and quirks

The skill SHALL ship a DragnCards harness reference that holds every DragnCards-specific fact the play skill teaches today, and the skill body SHALL NOT hold any of them. The reference SHALL provide the group-identifier catalogue a player agent uses — `playerNHand`, `playerNDeck`, `playerNDiscard`, `playerNPlay1`, `playerNPlay2`, `playerNEngaged`, `playerNEvent`, `sharedVillain`, `sharedMainScheme`, `sharedEncounterDeck`, and `sharedEncounterDiscard` — and state what each holds, that `playerNEngaged` holds enemies engaged with that player together with side schemes dealt to that player and facedown boost cards, and that moving a card into a deck group turns it facedown while moving it into a hand, discard, or play group turns it faceup.

The reference SHALL state the harness quirks of that platform's projection: that `players.<playerN>.hitPoints` is maximum and not remaining hit points, that `players.<playerN>.handSize` is the target hand size for the identity's current form and not the number of cards held, that `villainHitPoints` is the current villain stage's total and not the villain's remaining hit points, and that remaining values are therefore derived by subtracting the `damage` token count on the relevant card. It SHALL state that the platform's dotted step identifiers name its phases and that the step identifier is meaningful only on that platform.

The reference SHALL state that this platform validates nothing: turn order, phase authority, resource cost payment, the once-per-turn form change, and the hand limit are enforced nowhere, an action response always reports success and the only failure signal is a non-null error, and a missed cost is cheating rather than an error.

#### Scenario: The group catalogue is found in the platform reference

- **WHEN** an agent playing on DragnCards loads the platform's harness reference
- **THEN** it SHALL find every group identifier the seat uses, what each holds, and the facedown-on-move behaviour

#### Scenario: The derived-value quirks are found in the platform reference

- **WHEN** an agent needs a hero's or the villain's remaining hit points on DragnCards
- **THEN** the reference SHALL state that the projected value is a maximum or a stage total and SHALL give the subtraction that derives the remaining value

#### Scenario: The group catalogue is absent from the skill body

- **WHEN** the skill body is inspected
- **THEN** it SHALL contain no DragnCards group identifier, no dotted step identifier, and no `villainHitPoints`, `hitPoints`, or `handSize` quirk

### Requirement: A marvel-lcg harness reference documents the enumerated-option surface

The skill SHALL ship a marvel-lcg harness reference that teaches acting through engine-enumerated legal options rather than through composed actions. It SHALL state that the platform adjudicates the rules, that the only moves offered are moves the engine has already ruled legal, and that the agent's task is therefore choosing among them rather than checking whether a move is allowed.

The reference SHALL state that an option is chosen by its option identifier and never by its name, because option names are not unique — a single prompt offers several options named `Play` that differ only by identifier — and SHALL instruct the agent to read the option's resolved target card names and types to tell two same-named options apart. It SHALL state that the option's target-count range is authoritative: the agent selects a number of targets within that range, a range whose maximum is zero means the option takes no targets and the offered target list is to be ignored entirely, and a range whose minimum is zero means selecting no target is a legal answer.

The reference SHALL state how a submission is confirmed and how a failure appears: the submission is acknowledged without reporting validity, an input the engine rejects is discarded silently and the same decision is asked again, and the confirmation an agent reads is therefore the prompt changing rather than any success field. It SHALL state that a repeated identical prompt after a submission means the submission was rejected, and SHALL forbid resubmitting the same choice in response.

The reference SHALL state that the platform enforces the rules the other platform does not — turn order, phase and turn advancement, cost payment, and the once-per-turn form change — that the seat acts only while the platform is asking that seat, and that ending the turn is one of the enumerated options rather than a separate call.

#### Scenario: Two same-named options are distinguished by identifier

- **WHEN** a prompt offers more than one option named `Play`
- **THEN** the reference SHALL instruct the agent to choose by option identifier and to read each option's resolved target names to decide between them
- **AND** it SHALL forbid choosing an option by name

#### Scenario: An option that takes no targets is submitted with none

- **WHEN** an option's target-count range has a maximum of zero
- **THEN** the reference SHALL state that no target is submitted and that the offered target list is ignored

#### Scenario: Selecting no target is a legal answer

- **WHEN** an option's target-count range has a minimum of zero
- **THEN** the reference SHALL state that submitting an empty target selection is a legal answer to that prompt

#### Scenario: A repeated prompt means the submission was rejected

- **WHEN** the same decision is asked again with the same options after a submission
- **THEN** the reference SHALL instruct the agent to treat the submission as rejected, to choose differently or report, and SHALL forbid resubmitting the identical choice

#### Scenario: The turn ends as an option, not as a call

- **WHEN** the reference describes finishing a turn on this platform
- **THEN** it SHALL state that ending the turn is one of the enumerated options and that no separate phase or turn advancement exists

### Requirement: The Marvel harness reference uses the actual option argument names

When the session platform is `marvel-lcg`, the player skill's harness reference SHALL instruct the
agent to call `list_game_options(session_id, player_n)` and
`choose_game_option(session_id, player_n, option_id, targets, resources, prompt_id,
prompt_version)`. It SHALL name `player_n` as the neutral seat argument, require the prompt
identity returned by the preceding list call, state that option names are not identities, and direct
the agent to read the current option list before choosing. It SHALL not use the stale `player`
argument name.

#### Scenario: A Marvel player lists options for its own seat

- **WHEN** a player agent reads the Marvel harness recipe
- **THEN** the recipe SHALL show `list_game_options` with `session_id` and `player_n`
- **AND** it SHALL pass the agent's assigned neutral seat in `player_n`

#### Scenario: A Marvel player submits a selected option

- **WHEN** a player agent submits a legal choice
- **THEN** the recipe SHALL show `choose_game_option` with `player_n`, `option_id`, `targets`,
  `resources`, `prompt_id`, and `prompt_version`
- **AND** it SHALL not tell the agent to submit `player`

#### Scenario: A stale argument cannot be taught by the skill

- **WHEN** the generated option tool schema is compared with the Marvel harness reference
- **THEN** both SHALL use `player_n`
- **AND** a reference containing only `player` SHALL fail the skill/tool contract check

### Requirement: The player skill routes setup selection to the neutral catalog

The player-facing skill SHALL not promise a fixed Marvel hero or scenario. When a player agent is
given setup responsibility, it SHALL direct setup discovery to `list_game_setup_catalog` and SHALL
use the caller-provided typed scenario and hero-deck ids. It SHALL report missing setup data rather
than selecting the first catalog entry or relying on a hardcoded hero.

#### Scenario: A player follows a caller-selected hero

- **WHEN** a player prompt identifies a neutral seat and a selected hero-deck id
- **THEN** the skill SHALL preserve that selection when describing setup verification
- **AND** it SHALL instruct the agent to confirm the resulting state rather than assume a default

#### Scenario: The skill does not invent setup

- **WHEN** a player prompt omits its scenario or hero-deck selection
- **THEN** the skill SHALL instruct the agent to report the missing input
- **AND** it SHALL not instruct the agent to choose a fixed or first-listed hero
