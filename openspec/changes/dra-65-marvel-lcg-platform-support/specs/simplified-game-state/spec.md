# Simplified Game State

## MODIFIED Requirements

### Requirement: Simplified Marvel Champions state output
The Game Service SHALL provide a simplified representation of Marvel Champions game state that includes only essential information for LLM decision-making, and the per-card payload SHALL be compact enough that the full state response stays under 256 KB for a 4-player table with a loaded encounter set so the response fits the MCP WebSocket transport limit (1,048,576 bytes).

The representation SHALL be **platform-neutral**: an agent reading it SHALL NOT have to know which platform produced the game. It SHALL be produced by a per-platform state normaliser owned below `GameSession` — one normaliser per supported platform, selected by the session's `platform` — and SHALL NOT be produced by, or branched on inside, an HTTP router. No consumer of the projection SHALL branch on `plugin_name`, a platform-specific group-id vocabulary, or a platform-specific step-id vocabulary to read it.

The projected field set SHALL be the same across platforms: the neutral play-round number, the neutral phase classification, the opaque platform phase label, `mode`, `players`, and `zones`. A field a platform cannot report SHALL be omitted rather than fabricated, and a platform-specific field (such as a DragnCards dotted `stepId` and its `stepDescription`) SHALL be emitted only for the platform that defines it.

#### Scenario: Simplified state filters to essential fields
- **WHEN** a client requests `GET /games/{id}/state` for a Marvel Champions session on any supported platform
- **THEN** the Game Service SHALL return a flattened representation containing `playRound`, `phase`, `phaseLabel`, `mode`, `players` (with hitPoints and handSize), and `zones`
- **AND** SHALL include `villainHitPoints` when the producing platform reports villain hit points

#### Scenario: The same projection shape is served for either platform
- **WHEN** a client requests `GET /games/{id}/state` for a DragnCards session and for a marvel-lcg session
- **THEN** both responses SHALL carry the same neutral field names and the same zone names
- **AND** neither response SHALL require the client to know which platform produced it in order to read the round, the phase, the seats, or the zones

#### Scenario: Normalisation lives below the session, not in the router
- **WHEN** the simplified state is produced for a session
- **THEN** the projection SHALL be produced by the normaliser registered for that session's `platform`, invoked polymorphically below `GameSession`
- **AND** no route handler SHALL compare `plugin_name` against a literal platform or plugin name to decide how to project the state

#### Scenario: Simplified state omits default-valued card fields
- **WHEN** a visible card has `currentSide == "A"`, `exhausted == false`, or all seven token counters at zero
- **THEN** those fields SHALL be omitted from that card's emitted object
- **AND** a card with no meaningful `currentSide`, `exhausted` or `tokens` SHALL be emitted as just `{id, instanceId, name, stackSize}`

#### Scenario: Simplified state emits only non-zero token counters
- **WHEN** a card has any token counters greater than zero
- **THEN** the emitted `tokens` field SHALL contain only the keys whose values are non-zero
- **AND** if no token counter is non-zero, the `tokens` field SHALL be absent

#### Scenario: Simplified state collapses HIDDEN entries
- **WHEN** a zone contains one or more HIDDEN entries (face-down cards, cards not visible to the reading seat, or player/encounter identity cards)
- **THEN** each HIDDEN entry SHALL be emitted as `{name: "HIDDEN", stackSize: N}` and SHALL NOT carry `id`, `instanceId`, `currentSide`, `exhausted`, or `tokens`

#### Scenario: Simplified state payload fits MCP transport
- **WHEN** the simplified state is generated for a 4-player table with a 40-card hero deck per seat, a loaded encounter set, the main scheme, the villain, and standard attachments
- **THEN** the JSON-serialized payload SHALL be under 256 KB
- **AND** SHALL remain under the 1,048,576-byte WebSocket message size limit with substantial headroom

#### Scenario: Simplified state excludes attachment hierarchy
- **WHEN** a card is an attachment tucked under another card
- **THEN** the simplified state SHALL NOT include that attachment as a separate entry in its zone's card list

#### Scenario: Simplified state omits null player aliases
- **WHEN** a player has a null alias in the raw state
- **THEN** that player SHALL be omitted from the simplified state's players object

#### Scenario: Simplified state shows stack size
- **WHEN** multiple cards share the same stackId in a zone
- **THEN** only the top card SHALL appear with `stackSize` indicating the total count

#### Scenario: Simplified state hides facedown cards but not exhausted
- **WHEN** a DragnCards card has `rotation != 0` AND is on Side A (not exhausted)
- **THEN** the card SHALL be hidden as "HIDDEN" with merged stack size
- **BUT WHEN** a card is exhausted (Side B with `exhausted: true`), it SHALL remain visible

#### Scenario: Simplified state shows exhausted cards
- **WHEN** a card is on Side B (exhausted)
- **THEN** the card SHALL be visible with its name and details intact
- **AND** the `exhausted` field SHALL be present and true

#### Scenario: Simplified state does not hide exhausted cards
- **WHEN** a DragnCards card has `rotation != 0` but is on Side B (exhausted)
- **THEN** the card SHALL remain visible (not hidden)
- **AND** the `exhausted` field SHALL be present and true
- **AND** the `currentSide` SHALL be present and equal to "B"

#### Scenario: Simplified state hides player/encounter cards
- **WHEN** a DragnCards card's name is "player" or "encounter"
- **THEN** the card SHALL be hidden as "HIDDEN" with merged stack size

#### Scenario: Simplified state merges hidden cards
- **WHEN** multiple hidden cards (facedown, not visible to the reading seat, or player/encounter) exist in the same zone
- **THEN** they SHALL be merged into a single "HIDDEN" entry with combined `stackSize`

## ADDED Requirements

### Requirement: The projection carries a neutral play-round number

The simplified game state SHALL carry `playRound`, a 1-based integer naming the round of PLAY, and SHALL NOT carry any platform-raw round counter. Every consumer — skill, orchestrator, evaluator, or dashboard — SHALL read `playRound` as the round of play with no further arithmetic.

Each platform's normaliser SHALL be the single place where that platform's raw counter becomes `playRound`:

- On DragnCards, `roundNumber` counts COMPLETED rounds and reads 0 throughout the first round of play, so `playRound` SHALL be `roundNumber + 1`.
- On marvel-lcg, `round_id` is ALREADY the play round (0 during setup, 1 on the first player turn), so `playRound` SHALL be `round_id` unchanged and SHALL NOT be incremented.

The conversion SHALL exist in exactly one place per platform. No consumer of the projection SHALL add, subtract, or otherwise re-derive a round offset, and the projection SHALL NOT expose the raw counter that would let it, because a second copy of the `+1` convention is a second place to get it wrong and would be silently wrong for a platform that does not need it.

Before the first round of play has begun, `playRound` SHALL be reported as `0` on every platform, so setup is distinguishable from round 1 without inspecting a phase label.

#### Scenario: A DragnCards first round of play reads as round 1

- **WHEN** a DragnCards session's raw state reports `roundNumber` 0 during the first round of play
- **THEN** the simplified state SHALL report `playRound` 1
- **AND** SHALL NOT emit `roundNumber`

#### Scenario: A marvel-lcg round is not incremented

- **WHEN** a marvel-lcg world payload reports `round_id` 1 on the first player turn
- **THEN** the simplified state SHALL report `playRound` 1
- **AND** SHALL NOT report `playRound` 2

#### Scenario: marvel-lcg setup is round 0

- **WHEN** a marvel-lcg world payload reports `round_id` 0 during setup
- **THEN** the simplified state SHALL report `playRound` 0

#### Scenario: The conversion is not re-encoded downstream

- **WHEN** the repository is inspected for the completed-round-to-play-round conversion
- **THEN** the `+1` SHALL appear only inside the DragnCards normaliser
- **AND** no consumer of the simplified state SHALL apply an offset of its own to `playRound`

### Requirement: The projection carries an opaque platform phase label and a neutral phase classification

The simplified game state SHALL carry two phase fields with different contracts:

- `phaseLabel` — the producing platform's own phase text, carried through as an OPAQUE string for a human or an LLM to read. It SHALL NOT be parsed, pattern-matched, compared against a literal, or used to drive control flow by any consumer, because the two platforms' vocabularies are unrelated: DragnCards names a dotted step id such as `"1.1"` or `"2.3"`, while marvel-lcg reports human prose such as `"Player 1 Turn"` or `"Resolve Mulligans"`, and marvel-lcg's `current_step_id` is a monotonically increasing integer with no correspondence to a DragnCards step id.
- `phase` — a neutral classification drawn from a closed set (`setup`, `player`, `villain`, `passive`, `unknown`) that every consumer needing phase logic SHALL use instead of `phaseLabel`.

Each platform's normaliser SHALL be the single place that derives `phase` from that platform's own vocabulary, and SHALL classify as `unknown` rather than guessing when the platform's phase is one it does not recognise. A platform's raw step identity SHALL NOT be reported under a neutral name: the DragnCards normaliser SHALL continue to emit its dotted `stepId` and `stepDescription` as DragnCards-specific fields, and marvel-lcg SHALL NOT emit a synthesised dotted step id, a fabricated `stepId`, or its `current_step_id` under that name.

The classification SHALL preserve the existing DragnCards phase semantics exactly, so that no DragnCards session changes behaviour because this projection became neutral. The DragnCards normaliser SHALL classify steps `1.1` and `1.2` as `player`, steps `2.1` through `2.5` as `villain`, and steps `0.0` and `0.1` as `passive` — the same classification the runtime seat and turn guard applies to those two steps today. `setup` SHALL be reserved for a platform that reports a distinct pre-first-round setup phase, which DragnCards does not, so a DragnCards session SHALL never report `setup`.

#### Scenario: DragnCards round-boundary steps stay passive rather than becoming setup

- **WHEN** a DragnCards session is in step `0.0` at the beginning of a round, and later in step `0.1` at the end of a round
- **THEN** the simplified state SHALL report `phase` as `passive` for both steps
- **AND** the runtime seat and turn guard SHALL reach the same conclusion for those steps that it reaches today
- **AND** neither step SHALL be reported as `setup`

#### Scenario: A marvel-lcg pre-first-round prompt classifies as setup

- **WHEN** a marvel-lcg world payload reports `phase` as `"Resolve Mulligans"` with `round_id` `0`
- **THEN** the simplified state SHALL report `phase` as `setup`, `phaseLabel` as `"Resolve Mulligans"`, and `playRound` as `0`

#### Scenario: A DragnCards step id classifies without being parsed downstream

- **WHEN** a DragnCards session is in step `2.3`
- **THEN** the simplified state SHALL report `phase` as `villain` and `phaseLabel` as that platform's own step text
- **AND** a consumer deciding whether the villain phase is resolving SHALL read `phase` rather than parsing `phaseLabel`

#### Scenario: marvel-lcg prose is carried, not translated into a step id

- **WHEN** a marvel-lcg world payload reports `phase` as `"Player 1 Turn"` and `current_step_id` as `47`
- **THEN** the simplified state SHALL carry `"Player 1 Turn"` verbatim as `phaseLabel` and SHALL report `phase` as `player`
- **AND** SHALL NOT emit a dotted step id, and SHALL NOT emit `47` as a `stepId`

#### Scenario: An unrecognised phase is classified as unknown, not guessed

- **WHEN** a platform reports a phase its normaliser does not recognise
- **THEN** the simplified state SHALL report `phase` as `unknown` and SHALL still carry the platform's text as `phaseLabel`

### Requirement: Zones are mapped by meaning, not by platform name

Each platform's normaliser SHALL map that platform's areas onto the SAME neutral zone names by what a zone MEANS in play, so a skill written against the projection reads one vocabulary. Specifically, marvel-lcg's `hand_cards`, `player_deck`, `area_hero`, `engaged_enemies`, `area_villain` and `area_schemes_main` SHALL project onto the same neutral zones that DragnCards' `playerNHand`, `playerNDeck`, `playerNPlay1`, `playerNEngaged`, `sharedVillain` and `sharedMainScheme` project onto, per seat where the zone is per seat and shared where it is shared.

A platform area with no neutral counterpart SHALL be either omitted or carried under a name that is clearly platform-scoped; it SHALL NOT be squeezed into a neutral zone whose meaning it does not share. A neutral zone the platform does not have SHALL be omitted rather than emitted empty, so an absent zone is distinguishable from an empty one.

marvel-lcg reports no `groupId` on any card, so zone membership SHALL be derived from the area a card is reported in rather than from a group identifier, and no consumer SHALL require a `groupId` to know which zone a card is in.

#### Scenario: A marvel-lcg hand projects onto the neutral hand zone

- **WHEN** a marvel-lcg world payload reports cards in seat 0's `hand_cards` and `player_deck`, and cards in `area_villain` and `area_schemes_main`
- **THEN** the simplified state SHALL report them in the same neutral zones a DragnCards session's `player1Hand`, `player1Deck`, `sharedVillain` and `sharedMainScheme` project onto

#### Scenario: An engaged enemy is a per-seat zone on both platforms

- **WHEN** a marvel-lcg world payload reports a minion in seat 2's `engaged_enemies`
- **THEN** the simplified state SHALL report it in the neutral engaged zone for `player2`, the same zone DragnCards' `player2Engaged` projects onto

#### Scenario: A platform area with no neutral counterpart is not forced into one

- **WHEN** a marvel-lcg world payload reports an area that has no neutral counterpart
- **THEN** that area SHALL be omitted or carried under a clearly platform-scoped name, and SHALL NOT be merged into an unrelated neutral zone

#### Scenario: Zone membership needs no group identifier

- **WHEN** a marvel-lcg card is projected
- **THEN** its zone SHALL be determined by the area it was reported in
- **AND** the projection SHALL NOT require, and SHALL NOT synthesise, a `groupId` for it

### Requirement: Per-seat hidden information is honoured per platform and collapses to the existing HIDDEN form

The projection SHALL be produced for a READING SEAT, and SHALL contain exactly the information that seat's human player would see. A card the reading seat cannot see SHALL be reported only as a count under the existing `HIDDEN` form and SHALL NOT be reported by name, identifier, type, or any other attribute.

On marvel-lcg the visibility decision SHALL be taken from the platform's own per-seat model rather than from a card-back heuristic: a card SHALL be treated as hidden from the reading seat when the reading seat is not listed in that card's `visible_for_players`, when `is_face_up` is false, or when the card is one of another card's `down_card_ids`. The normaliser SHALL NOT widen visibility because the world payload happens to contain a card — marvel-lcg filters by card, not by the requesting seat, so the payload the reading seat's projection is built from can contain a card only another seat can see.

On DragnCards the existing face-down and player/encounter-identity rules SHALL continue to decide visibility.

#### Scenario: A card another seat holds is a count, not a name

- **WHEN** a marvel-lcg world payload contains a card whose `visible_for_players` does not include the reading seat
- **THEN** that card SHALL appear in its zone only as part of a `HIDDEN` entry with a stack size
- **AND** its name and card identifier SHALL NOT appear anywhere in the projection

#### Scenario: A face-down card is hidden even from the seat that owns the zone

- **WHEN** a marvel-lcg card in the reading seat's own zone reports `is_face_up` false
- **THEN** it SHALL be projected as `HIDDEN`

#### Scenario: Cards tucked under another card are hidden

- **WHEN** a marvel-lcg card lists other cards in its `down_card_ids`
- **THEN** those cards SHALL be projected as `HIDDEN` and SHALL NOT be emitted as separate named entries

#### Scenario: Hidden cards of one zone merge into one entry

- **WHEN** several cards in one marvel-lcg zone are hidden from the reading seat
- **THEN** they SHALL be merged into a single `HIDDEN` entry whose `stackSize` is their total count, exactly as DragnCards hidden cards are merged

### Requirement: A platform's per-seat resource form is normalised, not passed through

marvel-lcg reports `players[].resources` as a STRING, not a count. The marvel-lcg normaliser SHALL convert that value into the projection's declared per-seat resource form and SHALL NOT emit a string where the projection declares a number; where the string cannot be interpreted as the declared form, the normaliser SHALL omit the field rather than emit an uninterpretable value or a fabricated zero.

No consumer of the projection SHALL have to accept two types for one field, because a field whose type depends on the producing platform is a field every reader has to branch on.

#### Scenario: A marvel-lcg resource string is normalised

- **WHEN** a marvel-lcg world payload reports a seat's `resources` as a string
- **THEN** the projection SHALL report that seat's resources in the projection's declared form
- **AND** SHALL NOT carry the platform's raw string under the neutral field name

#### Scenario: An uninterpretable resource value is omitted rather than faked

- **WHEN** a marvel-lcg seat's `resources` string cannot be interpreted as the declared form
- **THEN** the field SHALL be omitted for that seat
- **AND** the projection SHALL NOT report a zero that the platform did not state

### Requirement: The projection carries the pending-prompt set on a platform that names one

Where the producing platform names the seats whose decision it is currently waiting on, the simplified game state SHALL carry that set as a neutral field `pendingSeats`, holding neutral seat ids (`player1`..`player4`) translated from the platform's own seat addressing. It is the single field on which the runtime seat and turn guard, and the orchestrator's round loop, depend for turn authority on such a platform.

The field SHALL distinguish three cases without ambiguity, because they mean different things:

- On a platform that names pending seats and is currently waiting on one or more of them, `pendingSeats` SHALL list exactly those seats.
- On a platform that names pending seats but is waiting on none of them — the engine is still resolving — `pendingSeats` SHALL be present and empty. An empty set SHALL NOT be read as "any seat may act".
- On a platform that has no notion of a pending prompt, `pendingSeats` SHALL be omitted entirely rather than reported as empty, so a consumer can tell "no seat is being asked" from "this platform never asks". DragnCards SHALL omit it.

A consumer SHALL NOT infer turn authority from `pendingSeats` on a platform that omits it, and SHALL fall back to that platform's own turn model.

#### Scenario: marvel-lcg reports the asked seat as a neutral seat id

- **WHEN** a marvel-lcg render frame reports `ask_players` as `[1]`
- **THEN** the simplified state SHALL report `pendingSeats` as `["player2"]`
- **AND** SHALL NOT report the platform's zero-based seat index

#### Scenario: An engine still resolving reports an empty set, not an absent one

- **WHEN** a marvel-lcg render frame reports `ask_players` as `[]` while the engine resolves
- **THEN** the simplified state SHALL report `pendingSeats` as an empty list
- **AND** a consumer SHALL treat that as no seat being permitted to act, not as every seat being permitted

#### Scenario: DragnCards omits the field rather than reporting it empty

- **WHEN** the simplified state is generated for a DragnCards session
- **THEN** `pendingSeats` SHALL be absent from the projection
- **AND** a consumer SHALL determine turn authority from the DragnCards phase and its own tracked turn order, exactly as it does today
