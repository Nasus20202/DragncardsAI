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

#### Scenario: Known-broken tool is documented
- **WHEN** the skill describes returning a card to its deck
- **THEN** it SHALL record that the shuffle-into-deck tool currently fails in game with a group-not-found error
- **AND** it SHALL give a move-based workaround

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
