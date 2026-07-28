# game-history-ui Specification

## Purpose
TBD - created by archiving change history-event-store. Update Purpose after archive.
## Requirements
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

### Requirement: Restore-to-a-past-moment control
The dashboard SHALL provide a control to trigger a restore of a game to a selected past moment through the history-service, letting the user choose the restore target mode (a new branchable session or an in-place overwrite of the live session).

#### Scenario: Trigger a restore from the timeline
- **WHEN** a user selects a timeline moment and confirms a restore
- **THEN** the dashboard SHALL request the history-service to restore the game to that moment's `seq` and SHALL show the restore outcome

#### Scenario: Choose the restore target mode
- **WHEN** a user initiates a restore to a selected moment
- **THEN** the dashboard SHALL let the user choose between a new branchable session and an in-place overwrite, defaulting to a new session, and SHALL pass the chosen mode to the history-service

#### Scenario: Warn before an in-place overwrite
- **WHEN** a user selects the in-place overwrite mode for a restore
- **THEN** the dashboard SHALL warn that game state after the selected moment will be discarded and SHALL require confirmation before proceeding

#### Scenario: Surface restore failure
- **WHEN** the history-service reports that a restore could not be completed
- **THEN** the dashboard SHALL display the failure to the user without claiming the restore succeeded

### Requirement: Surface evaluator events and scores on the timeline
The dashboard SHALL surface `evaluator` events on the game history timeline, visually distinct from agent and game-service events, anchored to the move or round they grade, and SHALL show the verdict detail when an evaluator event is selected.

#### Scenario: Evaluator event anchored to the graded move or round
- **WHEN** the history view renders a game's timeline containing an `evaluator` event
- **THEN** the dashboard SHALL display that evaluator event anchored to the move (`target_seq`) or round (`round_span`) it grades, visually distinct from agent and game-service events

#### Scenario: Show verdict detail for an evaluator event
- **WHEN** a user selects an `evaluator` event in the timeline
- **THEN** the dashboard SHALL display the per-criterion scores, the overall score, the rationale, and any flags from the verdict payload

#### Scenario: Timeline without evaluator events
- **WHEN** a game has no `evaluator` events yet
- **THEN** the dashboard SHALL render the timeline normally without an error and without claiming evaluations exist

### Requirement: Request evaluation of selected moves or rounds
The dashboard SHALL provide a control for the user to select which targets of a game to evaluate — one or more moves, one or more rounds, a range, or the whole game — and to submit that evaluation request to the eval-service, then surface the request's progress and resulting verdicts on the timeline.

#### Scenario: Select targets and request evaluation
- **WHEN** a user selects one or more moves/rounds (or the whole game) on the history view and confirms an evaluation request
- **THEN** the dashboard SHALL submit an evaluation request for exactly those targets and SHALL show that the request was accepted

#### Scenario: Surface evaluation progress and results
- **WHEN** an evaluation request the user submitted is in progress or completes
- **THEN** the dashboard SHALL reflect the per-target status (pending/completed/failed) and render the resulting verdicts on the timeline as they appear

#### Scenario: No evaluation without a user request
- **WHEN** a user views a game's history without requesting any evaluation
- **THEN** the dashboard SHALL NOT trigger any evaluation automatically

### Requirement: History-driven game picker with delete

The dashboard history view SHALL source its game picker from games-with-recorded-history and SHALL provide a control to delete all history for the selected game, with a confirmation step, refreshing the picker and clearing the selection after a successful deletion.

#### Scenario: Picking a recorded game

- WHEN the user opens the history view
- THEN the game picker lists games that have recorded history and selecting one loads its timeline

#### Scenario: Deleting a game's history

- WHEN the user deletes the selected game's history and confirms
- THEN the dashboard calls the delete endpoint, clears the selection, and refreshes the game list so the deleted game no longer appears

### Requirement: Play-parity judge configuration in the evaluate control

The dashboard Evaluate control SHALL let the user configure the judge per evaluation — provider and model, reasoning effort, a custom prompt/rubric, and selected rules skills — reusing the same provider and skill sources as the Play flow, and SHALL include the chosen configuration in the evaluation request, omitting empty fields.

Judge model selection SHALL be searchable, using the same shared searchable model picker as the Play settings panel: typing SHALL narrow the offered models from the selected provider's catalog by case-insensitive substring match, and opening the control SHALL offer that provider's whole catalog. Narrowing the list alone SHALL NOT change the drafted model — only choosing an offered model SHALL. A drafted model the selected provider does not offer SHALL remain selectable, and the control SHALL be disabled when no models are available. Provider selection, the reasoning controls, the prompt/rubric field, and the skills selection are unaffected.

#### Scenario: Configuring and submitting a judge

- WHEN the user selects a provider/model, sets reasoning, optionally edits the prompt, picks skills, and submits an evaluation
- THEN the request carries the chosen judge configuration and the resulting verdict reflects the selected model

#### Scenario: Searching for a judge model

- WHEN the user types part of a model name into the judge model control
- THEN only the selected provider's models whose names contain that text are offered, and the drafted judge model is unchanged until one of them is chosen

#### Scenario: Drafted model outside the provider catalog

- WHEN the drafted judge model is not among the selected provider's offered models
- THEN the judge model control SHALL still show and offer that model rather than silently dropping it

### Requirement: Live evaluation status with cancel

The dashboard Evaluate control SHALL display live per-target evaluation status and incremental judge output via the eval-service stream, SHALL provide a Cancel control while the request is in flight, and SHALL refresh the timeline when the request completes so new evaluator events appear.

#### Scenario: Watching and cancelling an evaluation

- WHEN an evaluation is running
- THEN the control shows live per-target status and streamed judge output, offers a Cancel control that stops the in-flight evaluation, and on completion refreshes the timeline to show the new evaluator events

### Requirement: Readable conversation rendering

The dashboard history transcript SHALL render an agent move's captured conversation context — user/assistant/system messages, reasoning, and tool calls with their results — inline in the transcript event (not via a separate detail component), using the same transcript presentation as the Play tab, rather than raw JSON. The collapsible detail card used for this presentation SHALL be a single shared component reused by both the Play tab and the History transcript, with no change to its rendered output or `data-testid` values.

#### Scenario: Agent move shows a readable transcript

- WHEN the user selects an `agent_move` event whose payload carries a conversation context
- THEN the detail renders the messages, reasoning, and tool calls/results as a readable transcript (matching the Play tab's presentation), not as raw JSON

#### Scenario: Tool-call card expands to reveal its body

- WHEN the user clicks a collapsed tool-call or system-prompt card in the transcript
- THEN the card expands to show its body, using the same shared collapsible card the Play tab renders

### Requirement: Reconstructed board at the selected event

The dashboard SHALL let the user open the DragnCards board reconstructed at the selected event by restoring that event's `seq` into a fresh EPHEMERAL session (a non-emitting session that records no history) and embedding its room, allowing interaction, and SHALL dispose that ephemeral reconstruction when the view is closed — on in-app close/navigation and on browser tab close. Because the ephemeral session emits no history, disposal removes the reconstruction session only. Client disposal is best-effort (a server-side TTL reaper reclaims sessions whose client never tore them down). Only one reconstruction is live at a time.

#### Scenario: Open and click the board at a past moment

- WHEN the user opens the board for a selected event
- THEN the dashboard reconstructs that event's state into a fresh ephemeral session, embeds its DragnCards room, and the user can interact with the board as it was at that moment

#### Scenario: Reconstruction is disposed on close

- WHEN the user closes the reconstructed board view, navigates away, or closes the tab
- THEN the dashboard deletes the reconstruction session, leaving no orphaned session; because the ephemeral session is non-emitting, no extra game appears in the history list

### Requirement: Game-level evaluation entry point

Because an evaluation can target the whole game (a move, a round, a seq range, or the entire game), the dashboard SHALL present evaluation as a game-level action — opened from the history header and shown in its own panel — distinct from the per-move controls (restore, board). Per-move verdicts SHALL appear on the timeline as soon as each one lands, not only when the whole request finishes.

#### Scenario: Evaluation is opened as a game-level action

- WHEN the user opens evaluation for the selected game
- THEN it is presented from the header in its own panel (not nested under the per-move controls), supporting move / round / seq-range / whole-game targets

#### Scenario: Verdicts surface incrementally

- WHEN a whole-game (or multi-target) evaluation is running
- THEN each move's score appears on the timeline as that move's verdict is produced, before the whole request completes

### Requirement: Readable game labels

The dashboard history game picker SHALL show a human-readable label for each recorded game when one is available (the agent session name linked by `game_id`), falling back to the game id when no name is known.

#### Scenario: Picker shows a session name

- WHEN a recorded game has a linked agent session with a name
- THEN the picker shows that name (not the raw game-id UUID); games with no linked session still show their id

### Requirement: Responsive history layout

The dashboard history page SHALL use a responsive layout (timeline, detail/board, and controls) that remains usable without clipping or horizontal overflow across window sizes, including when the judge configuration panel is expanded.

#### Scenario: Layout holds on resize

- WHEN the history page is resized to a smaller or larger window
- THEN the timeline, detail/board, and controls remain reachable and scrollable without horizontal overflow or clipped content

### Requirement: Persistent evaluations queue
The dashboard SHALL provide a persistent evaluations queue in the History tab that is
accessible at all times (independent of the selected game and of the per-game Evaluate
drawer), showing the in-progress and recent evaluations across all games. Each queue entry
SHALL show the game (by its friendly name when known), a scope label distinguishing the
evaluation's scope (move / round / range / whole game), and the current status/progress, and
SHALL offer a Cancel action while the request is non-terminal. The queue SHALL reflect status
changes over time (by polling the eval-service listing) and SHALL surface an active-count
indicator so the user can tell, without opening it, that evaluations are running.

#### Scenario: See in-progress evaluations across games
- **WHEN** the user opens the evaluations queue while evaluations are running for one or more games
- **THEN** the dashboard SHALL list those evaluations with their game, scope label, and live
  status, and SHALL keep the list updated as their status changes

#### Scenario: Cancel from the queue
- **WHEN** the user activates Cancel on a non-terminal evaluation in the queue
- **THEN** the dashboard SHALL request cancellation of that evaluation and reflect the resulting
  cancelled status in the queue

#### Scenario: Active-count indicator
- **WHEN** one or more evaluations are in progress
- **THEN** the dashboard SHALL show an active-count indicator on the queue control even while the
  queue panel is closed

### Requirement: Enqueue-and-watch evaluation submission
The dashboard Evaluate control SHALL act as a configure-and-submit step: the user selects the
scope and judge configuration and submits, which enqueues the evaluation request; the request
SHALL then appear in the persistent queue, and the user SHALL be able to close the Evaluate
control immediately without interrupting or losing visibility of the running evaluation. Live
progress, judge output, and cancellation for a submitted evaluation SHALL be observed in the
queue rather than requiring the Evaluate control to remain open.

#### Scenario: Submitting drops the evaluation into the queue
- **WHEN** the user submits an evaluation from the Evaluate control
- **THEN** the dashboard SHALL enqueue the request and show it in the persistent queue, and the
  Evaluate control MAY be closed without affecting the running evaluation

#### Scenario: Closing the Evaluate control does not lose the evaluation
- **WHEN** the user closes the Evaluate control while a submitted evaluation is still running
- **THEN** the evaluation SHALL continue and remain visible and cancelable in the persistent queue

### Requirement: Clearing evaluations from the queue
The dashboard SHALL let the user clear terminal evaluations from the persistent queue, both one at
a time and all at once. A Clear action SHALL be offered ONLY for a request that is fully terminal
(no target still in progress); a non-terminal request SHALL continue to offer Cancel instead of
Clear, so a running evaluation can never be cleared from the UI. A "Clear all" action SHALL clear
every terminal request and SHALL be disabled when there are no terminal requests. Clearing SHALL
remove entries from the queue view only and SHALL NOT affect verdicts already recorded in history.

#### Scenario: Clear a single terminal evaluation
- **WHEN** the user activates Clear on a terminal evaluation in the queue
- **THEN** the dashboard SHALL request its deletion and the entry SHALL no longer appear in the
  queue after the listing refreshes

#### Scenario: Clear is not offered for running evaluations
- **WHEN** an evaluation in the queue is still non-terminal
- **THEN** the dashboard SHALL offer Cancel for it and SHALL NOT offer Clear

#### Scenario: Clear all terminal evaluations
- **WHEN** the user activates Clear all while one or more terminal evaluations are present
- **THEN** the dashboard SHALL clear all terminal evaluations and leave any non-terminal
  evaluations in the queue

#### Scenario: Clear all disabled when nothing is clearable
- **WHEN** the queue has no terminal evaluations
- **THEN** the dashboard SHALL disable the Clear all action

### Requirement: Collapsible event bodies with global expand/collapse

The dashboard history transcript SHALL collapse each event's detail body by default, showing only its summary line (sequence number, actor, phase, score indicator, action label, the per-event Actions control, and timestamp), and SHALL keep the short user prompt bubble always visible. Each event SHALL provide a per-event toggle to open or close its own body, and the transcript SHALL provide a single Expand all / Collapse all control that opens or closes every event body at once. A global expand/collapse action SHALL override the current per-event states, after which per-event toggles continue to work independently.

#### Scenario: Bodies are collapsed by default

- WHEN the user opens a game's transcript
- THEN every event renders its summary line only, with its detail body collapsed

#### Scenario: A per-event toggle opens one body

- WHEN the user toggles a single event's body open
- THEN that event's detail body is shown while other events stay collapsed

#### Scenario: Expand all opens every body

- WHEN the user activates Expand all
- THEN every event's detail body is shown

#### Scenario: Collapse all closes every body

- WHEN the user activates Collapse all
- THEN every event's detail body is hidden

### Requirement: Transcript search

The dashboard history transcript SHALL provide a search input that filters the visible events by a case-insensitive match across each event's action label, actor, and payload text (including intended action, reasoning, prompt, and stringified arguments/state). Round headers SHALL remain only for rounds that still have at least one matching event, and the transcript SHALL show a no-matches empty state when no event matches. Searching SHALL NOT disturb the auto-follow scroll behavior.

#### Scenario: Typing filters the events

- WHEN the user types a query that matches some events
- THEN only the matching events (and the round headers that still contain a match) are shown

#### Scenario: Clearing the query restores all events

- WHEN the user clears the search query
- THEN all events are shown again

#### Scenario: No matches shows an empty state

- WHEN the user types a query that matches no event
- THEN the transcript shows a no-matches empty state

### Requirement: Round start and end boundaries

The dashboard history transcript SHALL mark both the start and the end of each round. The start of a round SHALL be shown with a "Round N — start" header, and the end of a round SHALL be shown with a "Round N — end" marker rendered after the last event of that round. The leading Setup band (events before any round) SHALL NOT produce a spurious end marker.

#### Scenario: Each round has a start and end marker

- WHEN the transcript renders a game spanning multiple rounds
- THEN each round shows a start header before its first event and an end marker after its last event, in order

#### Scenario: Setup band has no end marker

- WHEN the transcript renders leading events that belong to no round (Setup)
- THEN no end-of-round marker is rendered for the Setup band

### Requirement: Game → rounds → moves navigation tree

The dashboard history sidebar SHALL render a collapsible navigation tree of the selected game's structure: game → rounds → moves, where each round node lists its moves (agent moves and notable events) with a short label combining the action label and the event sequence number. Selecting a move node SHALL select that event and scroll it into view in the transcript, without fighting the transcript's auto-follow scroll-lock (an explicit selection scroll-into-view happens only on a selection change).

#### Scenario: Tree lists rounds and their moves

- WHEN a game is selected
- THEN the sidebar shows a navigation tree with a node per round and, under each round, a node per move

#### Scenario: Selecting a move node selects and reveals the event

- WHEN the user clicks a move node in the navigation tree
- THEN the corresponding event is selected and scrolled into view in the transcript

### Requirement: Per-player evaluation display
The dashboard SHALL display evaluation results per player at each level (move, round, game),
labelling each verdict with the player it pertains to, and SHALL present a per-player game
scorecard that shows each player's move/round/game scores side by side so players can be
compared. Move/round/game verdicts SHALL be visually distinguishable by both their level and
their player.

#### Scenario: Verdicts show their player
- **WHEN** the dashboard renders an evaluation verdict in the transcript
- **THEN** it SHALL show which player the verdict pertains to (alongside its scope/level), and
  per-player round/game verdicts SHALL be distinguishable from move verdicts

#### Scenario: Per-player game scorecard
- **WHEN** a game has per-player evaluations
- **THEN** the dashboard SHALL present a scorecard comparing each player's move/round/game scores

### Requirement: Request a cascade evaluation
The dashboard SHALL let the user request a higher-level (round or whole-game) evaluation that
auto-grades the components beneath it, and the persistent evaluations queue SHALL reflect the
resulting fan-out of sub-evaluations as they progress.

#### Scenario: Whole-game cascade from the UI
- **WHEN** the user requests a whole-game evaluation
- **THEN** the dashboard SHALL submit the cascade and the queue SHALL show the moves, rounds, and
  game sub-evaluations progressing to completion

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

