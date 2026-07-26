## MODIFIED Requirements

### Requirement: Game history timeline view
The dashboard SHALL present a recorded game's history as a **continuous, vertically-scrolling
transcript** — every event rendered inline as a readable block in one scrollable column in
ascending `seq`, grouped under round headers — mirroring the Play tab's session transcript,
rather than a narrow one-line timeline paired with a separate single-event detail panel. Stored
snapshots remain an internal reconstruction detail and SHALL NOT be surfaced as user-facing
markers.

#### Scenario: Read a whole game as a continuous transcript
- **WHEN** a user opens the history view for a `game_id`
- **THEN** the dashboard SHALL render all of the game's events inline in one scrollable column
  ordered by ascending `seq`, distinguishing `agent` move/decision events, `game-service`
  game-state events, and user-prompt events, so the user can read the whole game without
  selecting events one at a time

#### Scenario: Agent move renders inline with its decision context
- **WHEN** the transcript renders an `agent` move event that carries a conversation context
- **THEN** the dashboard SHALL render the intended action and reasoning inline for that event, and
  SHALL make the readable conversation transcript available collapsed by default behind a per-event
  toggle (so the overall transcript stays scannable), expandable on demand

#### Scenario: Game state renders inline with status
- **WHEN** the transcript renders a `game-service` state event
- **THEN** the dashboard SHALL render a concise summary inline (action label, phase, resulting
  game status) for that event

#### Scenario: Verdicts nest under the graded event
- **WHEN** an event has one or more evaluator verdicts targeting it
- **THEN** the dashboard SHALL show those verdicts as a collapsible sub-tree nested under that
  event in the transcript (not as separate transcript rows)

#### Scenario: Follow a game that is still being played
- **WHEN** new events arrive for the open game while the user is parked at the bottom of the
  transcript
- **THEN** the transcript SHALL auto-follow to the latest event, and SHALL offer a "jump to
  latest" affordance when the user has scrolled away

#### Scenario: Empty history
- **WHEN** a user opens the history view for a `game_id` with no stored events
- **THEN** the dashboard SHALL display an empty-state message rather than an error

## ADDED Requirements

### Requirement: Game selection list
The dashboard SHALL present the recorded games as a **selectable list in a left sidebar**
(mirroring the Play tab's sessions list) rather than a single dropdown control, showing for each
game a human-readable label (the linked agent session name, falling back to the game id), its
event count, and last-activity time, with the active game highlighted. The list SHALL be
collapsible and SHALL refresh on tab focus/visibility so a game recorded elsewhere appears
without a manual reload.

#### Scenario: Pick a game from the sidebar list
- **WHEN** a user clicks a game in the left games list
- **THEN** the dashboard SHALL load and display that game's transcript and mark that row active

#### Scenario: Readable labels in the list
- **WHEN** a recorded game has a linked agent session with a name
- **THEN** the list row SHALL show that name (not the raw game-id UUID); games with no linked
  session still show their id

### Requirement: Per-event inline actions
The dashboard SHALL expose the per-event actions (restore the game to that event; open the
reconstructed board at that event) as inline affordances on the focused transcript event, rather
than in a separate fixed controls column. Game-level evaluation remains a header-opened drawer.

#### Scenario: Restore or open the board from the transcript
- **WHEN** a user focuses an event in the transcript and triggers "restore here" or "open board here"
- **THEN** the dashboard SHALL perform that action for the focused event's `seq` (restore via the
  history-service; board via an ephemeral reconstruction), with no separate controls column required
