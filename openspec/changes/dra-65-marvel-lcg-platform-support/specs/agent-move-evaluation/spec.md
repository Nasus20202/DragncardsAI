# Agent Move Evaluation

## MODIFIED Requirements

### Requirement: Per-round evaluation
The eval-service SHALL evaluate each round/turn in isolation, detecting round boundaries from the round/phase information on `game-service` state events, closing the final round on a terminal game status, and producing one round verdict per closed round.

Because a `game-service` event embeds the state **after** its action was applied, the event whose state first reports a different round number is the event that CLOSED the preceding round. That event SHALL be the closing sequence (`to_seq`) of the round it closed, and the next round SHALL start at the sequence after it — so a round's span covers the move that ended it, and a round roll-up is graded against the board as that round ended rather than the board from before its own closing action. This SHALL match how the history transcript attributes a `game-service` event, so an evaluated round span and a displayed round band cover the same events. An event that both closes a round and carries a terminal status SHALL close that round exactly once and SHALL NOT open an additional empty span after itself.

Every round number the eval-service reports or accepts SHALL be the 1-based round of PLAY, read from the NEUTRAL play-round number the platform's state projection carries. The eval-service SHALL NOT apply a round offset of its own, because the raw counter's meaning is platform-dependent: DragnCards `roundNumber` counts COMPLETED rounds and reads 0 throughout the first round of play, so the round of play is that counter plus one; marvel-lcg's `round_id` is ALREADY the round of play, so incrementing it would name every round one too high. The conversion belongs to the per-platform state projection and SHALL exist in exactly one place per platform.

The round named in a round-level judge prompt and the round numbers accepted in a request's round selection SHALL both use that convention, so a round names the same round the history transcript names, whichever platform recorded it. The raw counter SHALL NOT be presented to a judge or a user.

#### Scenario: Evaluate a closed round
- **WHEN** the eval-service detects that a round has closed at a `game-service` state event with `seq` R
- **THEN** the eval-service SHALL assemble the round's moves and produce a `scope=round` verdict targeting `seq` R with the round's `from_seq`/`to_seq` span

#### Scenario: A round ends at the event that closed it
- **WHEN** a `game-service` event's post-action state is the first to report a new round number, at `seq` R, and the preceding round began at `seq` F
- **THEN** that round's span SHALL be `F` to `R` inclusive, and the next round SHALL begin at `seq` R+1, rather than the round ending at `seq` R-1 and the next round beginning at `seq` R

#### Scenario: The move that closed a round is graded inside that round
- **WHEN** an agent move advances the game out of a round and the resulting state event reports the new round number
- **THEN** that move SHALL be part of the span of the round it closed, and the round's closing state SHALL be the state recorded at the round's closing sequence

#### Scenario: The first round of play is round 1, not round 0
- **WHEN** a round's `game-service` state events come from a DragnCards recording reporting `roundNumber` 0 (DragnCards has not yet counted a completed round)
- **THEN** the eval-service SHALL report that round as round 1 — in the round-level judge prompt and in the round numbers it accepts in a selection — and SHALL NOT name it round 0

#### Scenario: A marvel-lcg round is not shifted by one
- **WHEN** a round's `game-service` state events come from a marvel-lcg recording whose `round_id` is 1 for the first player turn
- **THEN** the eval-service SHALL report and accept that round as round 1
- **AND** SHALL NOT report it as round 2

#### Scenario: A selected round number means the round of play
- **WHEN** an evaluation request selects rounds by number
- **THEN** the eval-service SHALL resolve each number as the round of play of that ordinal (1 being the first round played), matching the numbering the history transcript displays

#### Scenario: Final round closed by terminal status
- **WHEN** a game reaches a terminal status (`win` or `loss`) without a subsequent round-change signal
- **THEN** the eval-service SHALL close the final round at that terminal event and produce its round verdict

#### Scenario: Round change and terminal status on the same event
- **WHEN** the event that closes a round is also the event carrying the terminal game status
- **THEN** the eval-service SHALL close that round once at that event and SHALL NOT emit a further round whose span starts after its own closing sequence

### Requirement: Round-aware grading instruction
The judge SHALL be instructed that a single game decision is normally executed as several recorded actions and SHALL be told to grade the move as the step it is within the play its round reveals. Specifically the instruction SHALL state that a legal, necessary step of a sound play SHALL NOT be scored down for accomplishing nothing on its own, and that one play SHALL NOT be charged against every action that makes it up.

The per-move judge input SHALL name the round the graded move belongs to, and SHALL label its earlier-in-round and later-in-round context distinctly, with the later-in-round context marked as completion context rather than an outcome to grade on hindsight.

Round labels presented to a judge or to a user SHALL use the round of play, taken from the neutral play-round number the recording's platform projection carries. The eval-service SHALL NOT derive a label by adding to or subtracting from a platform's raw counter, because a DragnCards counter counts COMPLETED rounds and reads zero throughout the first round of play while a marvel-lcg counter is already the round of play.

#### Scenario: Multi-call play is not scored down per call
- **WHEN** the judge is asked to grade an action that only pays a cost, such as exhausting a character, and the round context shows the action whose effect that cost paid for
- **THEN** the judge instruction SHALL direct that the action be graded as that step of that play rather than as an action that achieved nothing

#### Scenario: Later-in-round context is not an outcome to grade
- **WHEN** the per-move input includes moves recorded later in the round
- **THEN** those moves SHALL be labelled as completion context and the instruction SHALL direct the judge not to score the decision on hindsight it did not have

#### Scenario: Round labels count the round of play
- **WHEN** a DragnCards recording's state reports a round number of 0
- **THEN** every label derived from it SHALL read as round 1
- **AND WHEN** a marvel-lcg recording's state reports a round of 1
- **THEN** every label derived from it SHALL read as round 1

### Requirement: Detected round listing
The eval-service SHALL expose a read API listing the rounds it detects for a game, so a client can select a round WITHOUT naming any sequence inside it. Each listed round SHALL carry the round number the evaluation request's round selection accepts, a presentation label, its `from_seq` and `to_seq` span, the number of agent moves in it, and the players who acted in it.

The listed number SHALL be the round of play — the SAME number the round selection accepts and the same number the History transcript shows — so a client never converts between two round-numbering schemes and cannot select the wrong round by picking the raw recorded counter. The listing SHALL produce that number identically for either platform's recording, taking it from the neutral play-round number rather than by applying an offset to a platform's raw counter.

A round the listing reports SHALL be a round the eval-service can grade, so that selecting a listed round always expands to at least one target.

#### Scenario: List a game's rounds
- **WHEN** a client requests the round listing for a `game_id` with recorded events
- **THEN** the eval-service SHALL return each detected round with its round-of-play number, label, sequence span, agent-move count, and acting players

#### Scenario: The listed number is the number the selection accepts
- **WHEN** a DragnCards recording's state reports a round number of 0 for the first round of play
- **THEN** that round SHALL be listed as round 1, and submitting round 1 SHALL select that same round

#### Scenario: The listed number matches the play round on either platform
- **WHEN** a marvel-lcg game's rounds are listed and its first player turn recorded `round_id` 1
- **THEN** that round SHALL be listed as round 1, and submitting round 1 SHALL select that same round
- **AND** the listing SHALL NOT present a different number for the same round than the DragnCards listing would present for the equivalent round of play

#### Scenario: A listed round is selectable by number alone
- **WHEN** a client submits a round-scope evaluation naming only the round numbers from that listing
- **THEN** the eval-service SHALL expand the request to that round's targets without requiring any move sequence

#### Scenario: Round listing for an unknown game
- **WHEN** a client requests the round listing for a `game_id` with no recorded events
- **THEN** the eval-service SHALL respond 404 rather than an empty success

## ADDED Requirements

### Requirement: The judge's state projection is selected per platform

The projection that reduces a recorded state to the board a judge rules on SHALL be selected by the PLATFORM of the recording, and SHALL NOT be selected by sniffing a single platform's field. Today's recogniser answers "is this a state I understand?" by testing whether `state["game"]["cardById"]` is a dictionary, projects zones keyed by each card's `groupId`, and names the phase from a table of dotted step ids `0.0`–`2.5`. All three are DragnCards vocabulary: a marvel-lcg state has no `cardById`, no `groupId` on any card, and a phase that is human prose rather than a dotted id, so under the existing recogniser every marvel-lcg state would be classified as unrecognised and sent to the judge as raw JSON bounded by a character limit.

The eval-service SHALL therefore hold one projector per platform, resolve the recording's platform, and project with that platform's projector. A recorded state whose shape the SELECTED projector does not recognise SHALL continue to be sent as recorded rather than dropped, so the existing fallback still protects an unexpected shape.

The projected result SHALL be the same neutral shape whichever platform produced the state — the round of play, the phase, each seat's vitals, and the visible cards per zone with the identifiers the move's arguments reference — so a verdict's input is comparable across platforms and the judge rubric does not fork.

Hidden information SHALL stay hidden under every platform's projector, using that platform's own visibility model: a marvel-lcg projector SHALL honour `visible_for_players`, `is_face_up` and `down_card_ids` and SHALL report a card the graded seat could not see only as a count under the hidden marker, never by name.

The DragnCards projection's OUTPUT SHALL be unchanged by this restructuring. Because the judge input determines the evaluator version and therefore the comparability of every stored verdict, a DragnCards recording SHALL project to exactly the text it projected before, so no evaluator-version increment and no re-evaluation is triggered for existing recordings; any diff in the DragnCards projection is a regression rather than an improvement.

#### Scenario: A marvel-lcg state is projected, not dumped as raw JSON

- **WHEN** a move recorded on marvel-lcg is evaluated and its recorded state carries the platform's own area lists and prose phase
- **THEN** the judge input SHALL carry the projected board — the round of play, the phase, each seat's vitals and the visible cards per zone
- **AND** SHALL NOT be the recorded state serialised whole and character-clipped

#### Scenario: The DragnCards field sniff is not the test for projectability

- **WHEN** a recorded state carries no `cardById` map and no `groupId` on its cards but comes from a platform with a registered projector
- **THEN** that platform's projector SHALL be used
- **AND** the state SHALL NOT be classified as unrecognised merely because the DragnCards markers are absent

#### Scenario: An unrecognised shape is still preserved

- **WHEN** a recorded state is in no shape the selected platform's projector understands
- **THEN** it SHALL be serialised as recorded and bounded by the configured character limit, so no content is silently discarded

#### Scenario: marvel-lcg hidden information stays hidden

- **WHEN** a marvel-lcg recorded state contains cards the graded seat is not listed in `visible_for_players` for, cards with `is_face_up` false, and cards listed in another card's `down_card_ids`
- **THEN** those cards SHALL appear in the judge input only as counts under the hidden marker
- **AND** their names SHALL NOT appear anywhere in the judge input

#### Scenario: The DragnCards projection is byte-identical after the restructuring

- **WHEN** a DragnCards recording is projected before and after the per-platform projectors are introduced
- **THEN** the projected judge input SHALL be identical
- **AND** the evaluator version SHALL NOT be incremented for DragnCards recordings by this change alone

### Requirement: The action taxonomy is resolved per platform

The non-strategic action taxonomy SHALL be resolved per PLATFORM, because the two platforms do not name a move the same way. A DragnCards move is a typed action identified by a game-service MCP tool name, and the taxonomy classifies it by that name. A marvel-lcg move is a CHOICE among options the engine enumerated, submitted as an option identifier with its targets and resource payments; there is no tool name to match.

For a platform whose moves are enumerated option choices, classification SHALL key on that platform's own option identity — the option's identifier together with its name and the event the prompt belonged to — and SHALL NOT key on the option's name alone, because an option name is not unique: a single verified prompt returned three options, two of them named `Play`, distinguishable only by their identifiers. A taxonomy keyed on the name would classify two different moves as one.

The configured skip set SHALL be per platform, and one platform's names SHALL NOT be applied to another platform's moves: a DragnCards tool name SHALL never match a marvel-lcg move and a marvel-lcg option identity SHALL never match a DragnCards action. The existing rule that an action outside the configured set — including any the service does not recognise — is EVALUATED rather than skipped SHALL hold for every platform, so a platform whose taxonomy is incomplete over-evaluates rather than silently skipping real decisions.

Declining an enumerated prompt (submitting the decline option) SHALL be treated as a gradeable decision rather than as plumbing, because choosing to take no option is a play a player can get wrong.

#### Scenario: A marvel-lcg option is classified by its identity, not by a tool name

- **WHEN** a move recorded on marvel-lcg is classified for skipping
- **THEN** the classification SHALL use that platform's configured skip set keyed on the option's identity
- **AND** SHALL NOT look the move up among the DragnCards tool names

#### Scenario: Two options sharing a name are not one action

- **WHEN** a marvel-lcg prompt offered two options both named `Play` with different identifiers and one of them is configured as non-strategic
- **THEN** only the configured identifier SHALL be skipped
- **AND** the other option SHALL be evaluated

#### Scenario: A platform's skip set does not leak across platforms

- **WHEN** an operator configures a skip set for one platform
- **THEN** that set SHALL apply only to that platform's recordings
- **AND** the other platform's classification SHALL be unchanged

#### Scenario: An unrecognised move on either platform is evaluated

- **WHEN** a recorded move names an action or option identity the platform's taxonomy does not know
- **THEN** the eval-service SHALL evaluate it rather than skip it

#### Scenario: Declining a prompt is graded

- **WHEN** a recorded marvel-lcg move is the decline answer to an enumerated prompt
- **THEN** it SHALL be evaluated rather than skipped as plumbing

### Requirement: The judge is told which platform produced the move and how legality was guaranteed there

The judge input SHALL state the platform the graded play was made on, and SHALL state what that platform guarantees about legality, because the same score on the same criterion means two different things on a playtable and on a rules engine.

For a recording from a RULES-ENFORCING platform — one whose engine adjudicates the rules and hands the agent an enumerated set of legal options — the input SHALL state that the engine validated the move, that the agent chose from a legal set it did not compose, and that an illegal play was therefore impossible to submit. On such a recording the `rules_legality` criterion SHALL be assessed as the quality of the choice WITHIN the legal set — whether the option chosen was the right one among those offered, and whether declining was correct when the agent declined — and the judge SHALL NOT be asked to look for a rules violation the engine could not have accepted, SHALL NOT score the criterion down for an absence of evidence, and SHALL NOT be free to invent one.

For a recording from a PLAYTABLE platform, which accepts whatever the client pushes, the criterion keeps its present meaning: whether the play was legal at all is a real question and remains the judge's to answer.

The four criteria and their names SHALL be unchanged on every platform so verdicts stay structurally comparable. A `dragncards` recording's prompt SHALL read as it does today, so existing verdicts remain comparable and no evaluator-version increment is caused by this change for recordings that predate it; the platform statement and the rules-engine framing SHALL be added for the platforms that need them.

A recorded illegal-action finding SHALL remain evidence available to the judge on any platform. On a rules-enforcing platform such a finding describes something our own orchestration recorded rather than something the engine permitted, and the input SHALL present it as that.

#### Scenario: A marvel-lcg move is framed as engine-validated

- **WHEN** a move recorded on marvel-lcg is projected for the judge
- **THEN** the input SHALL name the platform, SHALL state that the engine adjudicated legality, and SHALL state that the agent selected from an enumerated legal set

#### Scenario: rules_legality is graded as choice quality on a rules engine

- **WHEN** the judge grades `rules_legality` for a move recorded on a rules-enforcing platform
- **THEN** the instruction SHALL direct it to assess the quality of the choice among the legal options offered
- **AND** SHALL direct it not to hunt for, or invent, an illegality the engine could not have accepted

#### Scenario: A DragnCards move keeps today's legality question and today's prompt

- **WHEN** a move recorded on DragnCards is projected for the judge
- **THEN** the `rules_legality` criterion SHALL still ask whether the play was legal at all
- **AND** the prompt SHALL read as it read before this change, so previously stored verdicts stay comparable

#### Scenario: The criteria are the same on both platforms

- **WHEN** verdicts for a DragnCards recording and a marvel-lcg recording are compared
- **THEN** both SHALL carry the same four per-criterion scores under the same names
- **AND** neither SHALL add or drop a criterion because of its platform

#### Scenario: An illegal-action finding is still evidence on a rules engine

- **WHEN** a marvel-lcg round carries an illegal-action finding the orchestrator recorded
- **THEN** the projection SHALL include the finding with its seat, violation and resolution state
- **AND** SHALL present it as a finding our orchestration recorded rather than as a play the engine accepted
