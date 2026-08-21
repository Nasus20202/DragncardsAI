# Marvel Champions Play Skill

## ADDED Requirements

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

## MODIFIED Requirements

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
