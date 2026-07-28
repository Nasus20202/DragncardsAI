## ADDED Requirements

### Requirement: Complete event timeline loaded via cursor pagination

The dashboard SHALL load a recorded game's **complete** event timeline rather than a single page of it, by following the history-service's existing `after_seq` / `next_after_seq` cursor: it SHALL request pages at the server's per-request maximum (`limit` 1000) and SHALL keep requesting until the cursor is exhausted, concatenating the pages in ascending `seq`. The dashboard SHALL NOT require any change to the history-service read API, its `limit` ceiling, or its transport.

A client-side page bound SHALL remain (at most 20 pages, i.e. 20,000 events) so a pathological game cannot hang the browser. Because that bound exists, truncation SHALL be disclosed and SHALL NOT be silent: when the loaded timeline is shorter than the game's known total event count, the dashboard SHALL state how many events it is showing out of that total. When the whole timeline is loaded, the dashboard SHALL NOT claim any truncation.

#### Scenario: A game with more events than one page shows all of them

- **WHEN** a user opens the history view for a game whose recorded event count exceeds one page
- **THEN** the dashboard SHALL follow the `next_after_seq` cursor until it is exhausted and SHALL render every recorded event in ascending `seq`, including the events beyond the first page

#### Scenario: A single page ends the pagination

- **WHEN** the first page's response carries no further cursor
- **THEN** the dashboard SHALL issue no further requests and SHALL render exactly the events it received

#### Scenario: Truncation at the client bound is disclosed

- **WHEN** the client page bound is reached before the game's timeline is exhausted
- **THEN** the dashboard SHALL show how many events it is displaying out of the game's total event count, rather than presenting the partial timeline as complete

#### Scenario: A fully loaded timeline claims no truncation

- **WHEN** the loaded timeline covers the game's whole recorded event count
- **THEN** the dashboard SHALL NOT display a truncation notice

### Requirement: Correct round numbering, phase naming, and attribution of a round's closing move

The dashboard SHALL derive each event's round and phase from the DragnCards state semantics rather than from the raw state fields, so that the transcript labels match the game as played.

The displayed round number SHALL be `roundNumber + 1`, because DragnCards `roundNumber` counts **completed** rounds (it is 0 throughout the first round of play and increments as a round closes). "Setup" SHALL be reserved for the genuine setup band: events for which no game state is yet known, and events whose state has `roundNumber` 0 **and** step id `0.0` (the Beginning step before the first player phase). The first round of play SHALL NOT be labelled "Setup".

A step id SHALL be mapped to its phase through the Marvel Champions step-to-phase table (`0.0` Beginning, `1.1` and `1.2` Player, `2.1` through `2.5` Villain, `0.1` End) and SHALL NOT be bucketed by parsing the step id's leading number. In particular, step `0.1` SHALL be named as the End phase, not Beginning.

Because a `game-service` history event embeds the state **after** its action was applied, each `game-service` event SHALL be attributed to the round and step it acted **from** (the state before that action), with the observed post-action state carried forward to subsequent events. Events from other actors SHALL keep inheriting the latest observed state. Consequently the move that closes a round SHALL fall inside the round it closed, not at the start of the next round.

#### Scenario: The first round of play is Round 1, not Setup

- **WHEN** the transcript renders events whose state reports `roundNumber` 0 in a player or villain step
- **THEN** those events SHALL be grouped under "Round 1", and only the pre-state events and the `roundNumber` 0 / step `0.0` band SHALL be labelled "Setup"

#### Scenario: End-of-round step is named End

- **WHEN** an event's step id is `0.1`
- **THEN** the dashboard SHALL name its phase "End" rather than "Beginning"

#### Scenario: The move that closes a round stays in that round

- **WHEN** a `game-service` event's action advances the game out of a round (its pre-action state is in round N and its post-action state is in round N+1)
- **THEN** that event SHALL be rendered inside round N, and the next round's start header SHALL be rendered after it rather than above it

#### Scenario: Non-game-service events inherit the latest known state

- **WHEN** an `agent`, `user`, or `evaluator` event appears between two `game-service` events
- **THEN** it SHALL be attributed to the most recently observed round and step

## MODIFIED Requirements

### Requirement: Round start and end boundaries

The dashboard history transcript SHALL mark both the start and the end of each round. The start of a round SHALL be shown with a "Round N — start" header, and the end of a round SHALL be shown with a "Round N — end" marker rendered after the last event of that round. The leading Setup band (events before any round) SHALL NOT produce a spurious end marker.

An end marker SHALL be emitted only where the timeline actually crosses into a different round. The dashboard SHALL NOT emit an end marker for the last round present in the loaded timeline, because that round may still be in play or may merely have been cut short by the loaded range — an in-progress game SHALL NOT be shown as having ended its current round, and a truncated timeline SHALL NOT fabricate a round end at the point where the events stop.

#### Scenario: Each round has a start and end marker

- WHEN the transcript renders a game spanning multiple rounds
- THEN each round that the timeline leaves shows a start header before its first event and an end marker after its last event, in order

#### Scenario: Setup band has no end marker

- WHEN the transcript renders leading events that belong to no round (Setup)
- THEN no end-of-round marker is rendered for the Setup band

#### Scenario: The final round in view gets no end marker

- WHEN the loaded timeline's last events all belong to the same round (the game is still in that round, or the loaded range stops inside it)
- THEN no "Round N — end" marker is rendered after those events
