# game-history-ui Specification

## Purpose
Let a person read a finished or in-flight game the way they would read a transcript — top to bottom,
in one scrollable column, with every recorded event visible in `seq` order under its round heading.
The dashboard surface for `history-event-store`, deliberately mirroring the Play tab's transcript so
that reviewing a past game and watching a live one feel like the same activity. Reconstruction
mechanics (snapshots, cursors, page boundaries) are implementation detail and stay invisible: the
reader sees moves and rounds, never the machinery that fetched them.
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

Each action available on a recorded moment SHALL state what it will do, to which game, **before** it is clicked, and a destructive action SHALL be distinguishable from a read-only one without clicking either. The three per-moment actions differ in exactly the way a user cares about — one changes nothing, one creates a second game, one destroys play from the game in front of them — and they were presented as an undifferentiated list of controls whose labels named mechanisms ("New branchable session", "In-place overwrite") rather than consequences. A user who cannot tell which action overwrites their game is the reported defect, and a read-only action that looks destructive gets reported as data loss.

The read-only action SHALL be offered first, ahead of the actions that change a game: looking at the board is the cheapest and most common thing a user wants from a recorded moment.

A restore's reported outcome SHALL name the thing it produced, in terms the user can act on. For a branch restore that means naming the DragnCards room that was created and offering a way to open it — a new game the user cannot reach is indistinguishable from a restore that did not happen. For an in-place restore it means saying that this game has been rewound.

The dashboard SHALL distinguish a restore that completed without its agent conversation from a restore that failed. When the history-service reports that the game state was restored but the agent context was not, the dashboard SHALL present that as a completed restore carrying an explanatory note, NOT as a failure — the game state really was changed, so calling it a failure describes a state that does not exist and invites the user to retry a destructive action that already succeeded.

A confirmation affordance SHALL name the action until the user asks to perform it, and only then present the confirmation wording. A control that opens already reading "Confirm overwrite" and changes to the action name after the first click shows its most alarming wording at the moment it is least warranted, and gives no indication that a second click is what commits.

#### Scenario: Trigger a restore from the timeline
- **WHEN** a user selects a timeline moment and confirms a restore
- **THEN** the dashboard SHALL request the history-service to restore the game to that moment's `seq` and SHALL show the restore outcome

#### Scenario: Choose the restore target mode
- **WHEN** a user initiates a restore to a selected moment
- **THEN** the dashboard SHALL let the user choose between a new branchable session and an in-place overwrite, defaulting to a new session, and SHALL pass the chosen mode to the history-service

#### Scenario: Each mode's effect is legible before it is chosen
- **WHEN** the per-moment actions are shown for an event
- **THEN** each SHALL carry a label naming its effect and a marker distinguishing read-only from safe-but-creating from destructive, and the read-only action SHALL appear first

#### Scenario: Warn before an in-place overwrite
- **WHEN** a user selects the in-place overwrite mode for a restore
- **THEN** the dashboard SHALL warn that game state after the selected moment will be discarded and SHALL require confirmation before proceeding, with the submit affordance naming the action until the user requests it and only then reading as a confirmation

#### Scenario: A branch restore names and links the game it created
- **WHEN** a restore into a new session completes and the history-service reports the new room
- **THEN** the dashboard SHALL name that room in the outcome and SHALL offer a link that opens it

#### Scenario: A restore without its agent conversation is not a failure
- **WHEN** the history-service reports a completed restore whose agent context was not rebuilt, with a reason
- **THEN** the dashboard SHALL present a completed restore and show the reason as a note, and SHALL NOT present it as a failed restore

#### Scenario: Surface restore failure
- **WHEN** the history-service reports that a restore could not be completed
- **THEN** the dashboard SHALL display the failure to the user without claiming the restore succeeded

### Requirement: Surface evaluator events and scores on the timeline
The dashboard SHALL surface `evaluator` events on the game history timeline, visually distinct from agent and game-service events, anchored to the move or round they grade, and SHALL show the verdict detail when an evaluator event is selected.

A verdict's scope label SHALL name what the verdict graded, and SHALL NOT present sequence numbers as round numbers. A round-scoped verdict SHALL be labelled with the round of play recorded on the verdict, using the same "Round N" wording and the same conversion as the transcript's round bands and navigation tree, so a verdict and the round band it sits inside cannot name the same round differently. The verdict's sequence span SHALL NOT be used to derive that number: the span is a pair of event sequences, and a span read as a round range labels a verdict covering sequences 1 to 63 as "Rounds 1–63".

A round verdict that carries no recorded round of play — a verdict written before the round of play was recorded, including every verdict from an earlier evaluator version whose spans were derived differently — SHALL be labelled by its scope alone, with no round number. The dashboard SHALL NOT resolve such a verdict's span against boundaries it detects itself, because a span derived under a superseded rule resolves to a round the verdict did not grade, which is indistinguishable from a correct label. The span SHALL remain visible in the verdict detail, presented as the sequences it is.

#### Scenario: Evaluator event anchored to the graded move or round
- **WHEN** the history view renders a game's timeline containing an `evaluator` event
- **THEN** the dashboard SHALL display that evaluator event anchored to the move (`target_seq`) or round (`round_span`) it grades, visually distinct from agent and game-service events

#### Scenario: A round verdict is labelled with its round of play
- **WHEN** the transcript renders a round-scoped verdict that records round of play 1 and a sequence span of 1 to 63
- **THEN** its scope label SHALL read "Round 1" and SHALL NOT read "Rounds 1–63"

#### Scenario: A round verdict with no recorded round is not given a number
- **WHEN** the transcript renders a round-scoped verdict that carries a sequence span but no round of play
- **THEN** its scope label SHALL name the scope without a round number, and SHALL NOT show a number taken from the span

#### Scenario: Show verdict detail for an evaluator event
- **WHEN** a user selects an `evaluator` event in the timeline
- **THEN** the dashboard SHALL display the per-criterion scores, the overall score, the rationale, and any flags from the verdict payload

#### Scenario: Timeline without evaluator events
- **WHEN** a game has no `evaluator` events yet
- **THEN** the dashboard SHALL render the timeline normally without an error and without claiming evaluations exist

### Requirement: Request evaluation of selected moves or rounds
The dashboard SHALL provide a control for the user to select which targets of a game to evaluate — one or more moves, one or more rounds, a range, or the whole game — and to submit that evaluation request to the eval-service, then surface the request's progress and resulting verdicts on the timeline.

Choosing what to evaluate SHALL be ONE question, not two independent ones. The control SHALL offer a single mutually-exclusive choice of what is being graded — moves, rounds, or the whole game — and each choice SHALL own whatever further input it needs. Selecting a round SHALL mean selecting a round: the user SHALL pick rounds from a list of the game's actual rounds and SHALL NOT be required to select a move, a sequence, or a range in order to grade a round. The round list SHALL come from the eval-service's own round detection rather than being re-derived in the dashboard, so a round the user can pick is a round the service can grade, and each round SHALL be labelled with its round of play together with its sequence span and how many moves it contains.

The whole-game choice SHALL require no further input. The moves choice SHALL be the only one that consults the transcript selection or a sequence range. Combinations that carry no meaning SHALL NOT be expressible.

#### Scenario: Select targets and request evaluation
- **WHEN** a user selects one or more moves/rounds (or the whole game) on the history view and confirms an evaluation request
- **THEN** the dashboard SHALL submit an evaluation request for exactly those targets and SHALL show that the request was accepted

#### Scenario: Grading a round needs no move selected
- **WHEN** the user chooses to evaluate rounds with no transcript event selected, picks one or more rounds from the offered list, and submits
- **THEN** the dashboard SHALL submit a round-scope request naming those rounds, SHALL NOT require a move or sequence to be chosen, and SHALL NOT report a missing selection

#### Scenario: Rounds are offered with a readable label
- **WHEN** the user chooses to evaluate rounds for a game whose first recorded round reports a DragnCards round number of 0
- **THEN** that round SHALL be offered as round 1, alongside its sequence span and its number of moves, and submitting it SHALL name the same number the service listed rather than a converted one

#### Scenario: Round list comes from the service
- **WHEN** the dashboard offers the rounds of a game
- **THEN** the offered rounds SHALL be those the eval-service reports for that game

#### Scenario: What-to-evaluate is a single choice
- **WHEN** the user picks the whole game
- **THEN** no further target input SHALL be requested, and the transcript selection and sequence range SHALL have no bearing on what is submitted

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

Judge model selection SHALL be searchable, using the same shared searchable model picker as the Play settings panel: typing SHALL narrow the offered models from the selected provider's catalog by case-insensitive substring match, and opening the control SHALL offer that provider's whole catalog. Narrowing the list alone SHALL NOT change the drafted model — only choosing an offered model SHALL. A drafted model the selected provider does not offer SHALL remain selectable, and the control SHALL be disabled when no models are available.

Every judge control SHALL be rendered from the same shared field components as the Play settings panel, so the two panels present the same configuration identically. Specifically: the provider SHALL be a labelled select and the model a labelled searchable select; enabling reasoning and selecting a skill SHALL each be a toggle switch row, not a checkbox; reasoning effort SHALL be a labelled select; reasoning max tokens SHALL be a labelled text field; and the prompt/rubric SHALL be a labelled textarea. Skills SHALL be presented as the same bordered toggle list the Play panel renders, and a skill that carries a description or metadata SHALL expose them through the row's info trigger rather than only as a native tooltip on the label. The judge panel SHALL NOT define its own input styling for these controls.

Adopting the shared components SHALL NOT change the judge panel's behavior or its automation surface: changing the provider SHALL still clamp the model to that provider's offerings, an empty provider list SHALL still offer the drafted provider id, the panel SHALL still disable every control while an evaluation is being submitted, and each control SHALL keep the test id and accessible name it already exposed.

#### Scenario: Configuring and submitting a judge

- WHEN the user selects a provider/model, sets reasoning, optionally edits the prompt, picks skills, and submits an evaluation
- THEN the request carries the chosen judge configuration and the resulting verdict reflects the selected model

#### Scenario: Searching for a judge model

- WHEN the user types part of a model name into the judge model control
- THEN only the selected provider's models whose names contain that text are offered, and the drafted judge model is unchanged until one of them is chosen

#### Scenario: Drafted model outside the provider catalog

- WHEN the drafted judge model is not among the selected provider's offered models
- THEN the judge model control SHALL still show and offer that model rather than silently dropping it

#### Scenario: Judge controls match the Play settings controls

- WHEN the user opens the Judge section of the Evaluate panel
- THEN each control SHALL be the same shared field component the Play settings panel uses for that setting, with reasoning and each skill rendered as a toggle switch row rather than a checkbox

#### Scenario: Skill descriptions are reachable in the judge panel

- WHEN a skill offered in the judge panel carries a description or metadata
- THEN its row SHALL expose an info trigger revealing that description and metadata

#### Scenario: Provider change still clamps the judge model

- WHEN the user selects a different judge provider whose catalog does not include the drafted model
- THEN the drafted judge model SHALL be replaced with the first model the newly-selected provider offers

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

A live reconstruction SHALL survive the browser tab merely becoming hidden — switching tabs, minimizing, or backgrounding the application is not the end of the view. Disposal is triggered by an in-app close, a change of selection or game, unmounting the view, and page unload (tab close, refresh, navigation), never by the document becoming hidden, so the board the user comes back to is still the board the dashboard claims is open.

The reconstruction view SHALL state, on the view itself, that it is a temporary copy which does not affect the recorded game and is discarded when closed. This view replaces the whole transcript panel with an unfamiliar DragnCards room, and a board that looks exactly like a live game is indistinguishable from one; leaving the user to infer that nothing was overwritten produced a report of data loss against behaviour that provably changes nothing.

The dashboard SHALL explain the wait while a reconstruction is being built, rather than showing an unqualified spinner. Building one creates a real DragnCards room — several sequential round trips to the DragnCards backend plus a channel join and a plugin load, seconds rather than milliseconds — and an unexplained multi-second wait on a button whose effect the user is already unsure of is a substantial part of the surface reading as slow and unclear.

The dashboard SHALL take the reconstruction's room from the restore response when the history-service supplies it, rather than listing every live session and searching it by id. The list read is retained only as a fallback for a service that reports no room. Beyond the wasted round trip, the search races the ephemeral reaper: a session reclaimed between the restore and the list yields no match, and the view then renders its fallback with no error surfaced.

#### Scenario: Open and click the board at a past moment
- WHEN the user opens the board for a selected event
- THEN the dashboard reconstructs that event's state into a fresh ephemeral session, embeds its DragnCards room, and the user can interact with the board as it was at that moment

#### Scenario: The reconstruction says it is a throwaway copy
- WHEN a reconstructed board is shown
- THEN the view SHALL state that it is a temporary copy, that the recorded game is unaffected by anything done in it, and that it is discarded on close

#### Scenario: The wait while a board is built is explained
- WHEN a reconstruction is being created
- THEN the dashboard SHALL say that a temporary DragnCards room is being created and that it takes a few seconds, rather than showing only a spinner

#### Scenario: The room comes from the restore response
- WHEN a restore for a reconstruction reports the new session's room
- THEN the dashboard SHALL embed that room without listing the live sessions, falling back to the session list only when no room is reported

#### Scenario: Disposal on close
- WHEN the user closes the reconstructed board view, navigates away, or closes the tab
- THEN the dashboard deletes the reconstruction session, leaving no orphaned session; because the ephemeral session is non-emitting, no extra game appears in the history list

#### Scenario: A hidden tab does not end the view
- WHEN the browser tab holding a live reconstruction becomes hidden
- THEN the dashboard keeps that reconstruction session alive, and returning to the tab shows the same live board rather than a board whose session has been deleted underneath it

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

The sidebar's content SHALL fit inside the sidebar box, so the region that holds the sidebar and the main panel is never scrollable. That region does not scroll by design; if the sidebar's stacked sections (the games list and the navigation tree) overflow it, anything that scrolls an element into view — focusing a control, the transcript's auto-follow scroll — scrolls the region instead and displaces the whole main panel, pushing the reconstructed board's header and Close control off screen.

#### Scenario: Layout holds on resize

- WHEN the history page is resized to a smaller or larger window
- THEN the timeline, detail/board, and controls remain reachable and scrollable without horizontal overflow or clipped content

#### Scenario: Opening the board does not displace the main panel

- WHEN the user selects a game, opens an event's actions, and opens the reconstructed board
- THEN the sidebar+main region's scroll offset stays at its origin and the board renders fully inside the main panel, with its header and Close control on screen

### Requirement: Persistent evaluations queue
The dashboard SHALL provide a persistent evaluations queue in the History tab that is
accessible at all times (independent of the selected game and of the per-game Evaluate
drawer), showing the in-progress and recent evaluations across all games. Each queue entry
SHALL show the game (by its friendly name when known), a scope label distinguishing the
evaluation's scope (move / round / range / whole game), and the current status/progress, and
SHALL offer a Cancel action while the request is non-terminal. The queue SHALL reflect status
changes over time (by polling the eval-service listing) and SHALL surface an active-count
indicator so the user can tell, without opening it, that evaluations are running.

A queue entry identifies its targets by sequence, because that is what a queued target is keyed
by before it has been graded. Its scope labels SHALL therefore present sequences in a sequence
notation, and a round target's sequence span SHALL NOT be rendered as a range of round numbers.

A queue entry SHALL also show the failure detail of every target of that request that has one,
identified by the target it happened on, so a user can tell WHY an evaluation failed and not
merely that it did. This detail SHALL appear while the request is still running — the
eval-service records a failed judge attempt on the target as it happens — so a failure is
reported during the evaluation rather than only in its final status. The entry MAY cap how many
individual failures it lists provided it states how many more there are. A deliberately skipped
non-strategic target's reason SHALL NOT be presented as a failure, and neither SHALL the
bookkeeping reason of a cancelled target.

The queue SHALL obtain this detail from the evaluation listing it already polls; it SHALL NOT
open a second live connection for it.

#### Scenario: See in-progress evaluations across games
- **WHEN** the user opens the evaluations queue while evaluations are running for one or more games
- **THEN** the dashboard SHALL list those evaluations with their game, scope label, and live
  status, and SHALL keep the list updated as their status changes

#### Scenario: A round target is identified by its sequence span
- **WHEN** a queue entry labels a round target whose sequence span runs from 64 to 103
- **THEN** the label SHALL present that span in the entry's sequence notation and SHALL NOT read
  "Rounds 64–103"

#### Scenario: A failure is reported while the evaluation is still running
- **WHEN** a target of a queued evaluation has recorded a failure and the request has not yet
  reached a terminal status
- **THEN** the queue entry SHALL show that failure's detail alongside the target it happened on,
  on the queue's normal refresh, without waiting for the request to finish

#### Scenario: A terminal failure states its reason
- **WHEN** a queued evaluation ends with one or more failed targets
- **THEN** the queue entry SHALL show each failed target's reason, and SHALL NOT show only the
  request's overall status

#### Scenario: Many failures are summarized rather than dropped
- **WHEN** a queued evaluation has more failed targets than the entry lists individually
- **THEN** the entry SHALL show the listed failures and SHALL state how many further failures
  there are, so none of them is silently hidden

#### Scenario: A deliberate skip is not presented as a failure
- **WHEN** a queued evaluation contains a target skipped as a non-strategic action, carrying the
  reason for that skip
- **THEN** the queue entry SHALL NOT present that reason as a failure

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

The dashboard history transcript SHALL provide a search input that filters the visible events by a case-insensitive match across each event's action label, actor, and the payload text the listing carries — the intended action, the reasoning, the prompt, and the stringified arguments. Round headers SHALL remain only for rounds that still have at least one matching event, and the transcript SHALL show a no-matches empty state when no event matches. Searching SHALL NOT disturb the auto-follow scroll behavior.

Search SHALL NOT be expected to match text inside the raw DragnCards room state. That state is not carried by the listing, and searching it was never useful: on a 122-event game it made the search haystack 25 MiB of card definitions, plugin configuration and undo-log entries, costing 86 ms to rebuild on every keystroke, none of which is text a reviewer is looking for.

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

The scorecard SHALL NOT average verdicts produced by different evaluator versions into one
figure, because a change to what the judge is shown or asked moves the scale. It SHALL aggregate
the newest evaluator version present for the game and SHALL disclose how many older-version
verdicts it excluded, so an out-of-date verdict is visible rather than silently folded in.

#### Scenario: Verdicts show their player
- **WHEN** the dashboard renders an evaluation verdict in the transcript
- **THEN** it SHALL show which player the verdict pertains to (alongside its scope/level), and
  per-player round/game verdicts SHALL be distinguishable from move verdicts

#### Scenario: Per-player game scorecard
- **WHEN** a game has per-player evaluations
- **THEN** the dashboard SHALL present a scorecard comparing each player's move/round/game scores

#### Scenario: Scorecard excludes stale evaluator versions
- **WHEN** a game holds verdicts from an older evaluator version alongside verdicts from the newest one
- **THEN** the scorecard SHALL average only the newest version's verdicts and SHALL state how many older-version verdicts it left out

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

### Requirement: Complete event timeline loaded via cursor pagination

The dashboard SHALL load a recorded game's **complete** event timeline rather than a single page of it, by following the history-service's `after_seq` / `next_after_seq` cursor: it SHALL keep requesting until the cursor is exhausted, concatenating the pages in ascending `seq`.

It SHALL load that timeline from the history-service's **timeline** read, not its events read. The events read carries every payload in full, and a recorded DragnCards state is ~450-470 KB, so walking it costs tens of megabytes and seconds of server time for a few hundred events — measured at 2.3 s and 86 MiB for a 400-event game, against 0.57 s and 262 KiB for the same walk over timeline entries. The dashboard SHALL request pages at the timeline read's per-request maximum. It SHALL NOT require any change to the events read, its `limit` ceiling, or its transport.

Because the log is append-only, a refresh of an already-loaded game SHALL resume from the highest `seq` already held and append what is new, rather than re-reading the whole timeline. This applies to the periodic poll, the refresh on window focus or visibility change, and the refresh that follows an evaluation settling. A refresh SHALL NOT disturb the current selection.

A client-side page bound SHALL remain (at most 20,000 events) so a pathological game cannot hang the browser. Because that bound exists, truncation SHALL be disclosed and SHALL NOT be silent: when the loaded timeline is shorter than the game's known total event count, the dashboard SHALL state how many events it is showing out of that total. When the whole timeline is loaded, the dashboard SHALL NOT claim any truncation.

#### Scenario: A game with more events than one page shows all of them

- **WHEN** a user opens the history view for a game whose recorded event count exceeds one page
- **THEN** the dashboard SHALL follow the `next_after_seq` cursor until it is exhausted and SHALL hold every recorded event in ascending `seq`, including the events beyond the first page

#### Scenario: A single page ends the pagination

- **WHEN** the first page's response carries no further cursor
- **THEN** the dashboard SHALL issue no further requests and SHALL hold exactly the events it received

#### Scenario: A refresh reads only what is new

- **WHEN** the history view refreshes a game whose timeline is already loaded
- **THEN** the dashboard SHALL request only the events recorded after the highest `seq` it already holds, and SHALL append them to the loaded timeline

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

### Requirement: Export and import controls in the history header

The dashboard history view SHALL offer an export control and an import control in its header action bar, styled as the header's existing actions are.

The export control SHALL be offered only while a game is selected, and SHALL download that game's history bundle by navigating to the history-service export endpoint rather than fetching and buffering it, so that a bundle running to tens of megabytes is streamed to disk by the browser instead of held in the tab.

The import control SHALL be offered whether or not a game is selected, because an import creates a game rather than modifying the selected one. It SHALL open a file picker restricted to bundle files, SHALL send the picked file as the import request body, and SHALL indicate that an import is in progress.

The outcome of an import SHALL be reported inline in the history view — in the dashboard's existing notice style, since the dashboard has no toast layer — and never silently. A successful import SHALL state how many events and snapshots were written and under which game, and SHALL select that game so its timeline is immediately visible. A rejected import SHALL surface the history-service's own message, including the line of the file at fault, as an alert, and SHALL NOT change the selected game.

#### Scenario: Export the selected game

- **WHEN** a game is selected and the user activates the export control
- **THEN** the dashboard SHALL start a download from that game's export endpoint, and SHALL leave no download element behind in the document

#### Scenario: Export is not offered without a selection

- **WHEN** no game is selected
- **THEN** the dashboard SHALL NOT offer the export control, and SHALL still offer the import control

#### Scenario: A successful import is reported and opened

- **WHEN** the user picks a bundle file and the history-service accepts it
- **THEN** the dashboard SHALL show a status notice stating the number of events and snapshots written and the game they were written to, and SHALL select that game

#### Scenario: A rejected import is reported as an alert

- **WHEN** the user picks a bundle file and the history-service rejects it
- **THEN** the dashboard SHALL show the service's message — including the offending line — as an alert, and SHALL NOT change the selected game

### Requirement: Full event payloads fetched on demand

The dashboard SHALL fetch an event's complete payload from the history-service's
events read at the moment something needs it, and SHALL NOT present a reduced
payload as if it were the whole recording. This is necessary because the dashboard
lists a game from the timeline read, whose entries omit the raw DragnCards `state`
and an agent move's `conversation_context`.

The moment that needs it is an event's detail body, which is where those two
fields are shown. The dashboard SHALL therefore fetch the complete event when a
body is first opened, SHALL fetch it at most once per event (a recorded event never
changes, the log being append-only), and SHALL NOT fetch it for an event whose
payload is already complete.

While the fetch is in flight the dashboard SHALL show that the event is loading;
if it fails the dashboard SHALL say so rather than render an empty body.

#### Scenario: Opening a body fetches the event

- **WHEN** the user expands the body of an event whose listed payload is reduced
- **THEN** the dashboard SHALL fetch that event's complete payload and render the body from it

#### Scenario: A collapsed transcript fetches nothing

- **WHEN** the transcript is rendered and no event body has been opened
- **THEN** the dashboard SHALL NOT request any event's complete payload

#### Scenario: An already-complete payload is not re-fetched

- **WHEN** the user expands the body of an event whose payload is already complete
- **THEN** the dashboard SHALL render the body directly and SHALL NOT request the event again

#### Scenario: A failed detail fetch is reported

- **WHEN** fetching an event's complete payload fails
- **THEN** the dashboard SHALL show an error on that event rather than an empty body

### Requirement: Endless scroll over the loaded timeline

The dashboard history transcript SHALL render a contiguous window of the loaded
timeline rather than all of it, and SHALL grow that window as the reader reaches
its edges, so that the cost of rendering a game does not scale with the length of
the game.

The window SHALL open at the **newest** end of the timeline, because the last
thing that happened is what a reader wants first. Reaching the top of the rendered
window SHALL extend it towards older events; reaching the bottom SHALL extend it
towards newer ones. Extension SHALL also be reachable without scroll detection, so
the transcript remains usable where an intersection observer is unavailable.

The window SHALL stop offering to extend in a direction once it reaches that end
of the loaded timeline, and a timeline short enough to fit in one window SHALL be
rendered whole with no extension affordance at all.

When the length of the list beneath the window changes — a search query narrowing
it, or live play appending to it — the window SHALL be re-fitted rather than
reset: a window that was following the newest end SHALL keep following it, and a
window parked mid-game SHALL stay where the reader left it. A window emptied by a
query that matched nothing SHALL return to a full window when the query is
cleared, not to a single row.

The existing auto-follow and scroll-lock behaviour SHALL continue to hold, and the
"jump to latest" affordance SHALL move the window as well as the scroll position,
so that it returns to the newest events from anywhere. It SHALL be offered
whenever the window stops short of the newest loaded event, not only when the
scroll position is away from the bottom.

#### Scenario: A long timeline renders only a window, anchored at the newest events

- **WHEN** the user opens the history view for a game with several hundred recorded events
- **THEN** the transcript SHALL render the most recent events and SHALL NOT render the whole timeline at once

#### Scenario: Reaching the top loads earlier events

- **WHEN** the reader scrolls to the top of the rendered window and older events remain
- **THEN** the transcript SHALL extend the window towards those older events while keeping the newest events rendered

#### Scenario: Scrolling far enough reaches the first event

- **WHEN** the reader keeps extending the window towards older events
- **THEN** the transcript SHALL eventually render the first recorded event and SHALL stop offering to load earlier ones

#### Scenario: A short timeline is rendered whole

- **WHEN** the loaded timeline is shorter than one window
- **THEN** the transcript SHALL render every event and SHALL offer no scroll-extension affordance

#### Scenario: Clearing a no-match search restores a full window

- **WHEN** the reader clears a search query that had matched no events
- **THEN** the transcript SHALL render a full window of events again

### Requirement: Jump to a round

The dashboard history transcript SHALL provide a control that moves the transcript
directly to a chosen round, because with only a window of the timeline rendered,
scrolling is no longer a way to reach an early round of a long game.

The control SHALL offer the same rounds, in the same order and under the same
labels, as the game → rounds → moves navigation tree — the Setup band, then each
round of play numbered on DragnCards' completed-round convention — so the two
never disagree about what a round is called. It SHALL offer no round that has no
moves, and SHALL render nothing at all when the game has no rounds.

Choosing a round SHALL move the transcript to that round's first move and select
it. It SHALL be repeatable: choosing the round the transcript is already showing
SHALL jump again rather than do nothing.

A selection that falls outside the rendered window SHALL bring the window with it,
so that jumping to a round — from this control or from the navigation tree —
renders that round. A jump far from the current window SHALL rebuild the window
around the target rather than render everything in between.

#### Scenario: The control lists the game's rounds

- **WHEN** the user opens the jump-to-round control on a game spanning setup and two rounds of play
- **THEN** it SHALL offer "Setup", "Round 1" and "Round 2", and SHALL NOT label the first round of play as "Setup"

#### Scenario: Choosing a round moves the transcript to it

- **WHEN** the user chooses a round from the control
- **THEN** the transcript SHALL select that round's first move and SHALL render it

#### Scenario: Jumping to a distant round does not render the events in between

- **WHEN** the user jumps from the newest events to an early round of a long game
- **THEN** the transcript SHALL render a window around that round and SHALL NOT render the events between it and the end of the timeline

#### Scenario: Returning to the newest events after a jump

- **WHEN** the transcript is showing an early round after a jump
- **THEN** the "jump to latest" affordance SHALL be offered and SHALL return the transcript to the newest events

#### Scenario: A game with no rounds offers no control

- **WHEN** the selected game has no recorded rounds
- **THEN** the jump-to-round control SHALL NOT be rendered

### Requirement: Hero UI controls in the evaluate panel
Every interactive control in the dashboard's evaluate panel SHALL be a Hero UI component or one of the dashboard's shared field wrappers built from them, and SHALL NOT be a hand-rolled native form element. Specifically the what-to-evaluate choice SHALL be a radio group, the round picker SHALL be a checkbox group, the sequence range bounds SHALL be labelled text fields of the same shared kind the judge panel uses, re-evaluate SHALL be a toggle switch row rather than a native checkbox, and the error and confirmation states SHALL be Hero UI alerts.

Adopting these components SHALL NOT change the panel's behavior or remove its automation surface: submission SHALL stay disabled while a request is in flight or no game is selected, and each control SHALL expose an accessible name and a stable test id.

#### Scenario: Controls are Hero UI components
- **WHEN** the user opens the evaluate panel
- **THEN** each control SHALL be a Hero UI component or a shared field wrapper built from one, and the panel SHALL NOT render a bare native radio, number, or checkbox input

#### Scenario: Behaviour is unchanged by the components
- **WHEN** a game is not selected, or an evaluation request is being submitted
- **THEN** the panel's controls and its submit action SHALL be disabled, exactly as before

