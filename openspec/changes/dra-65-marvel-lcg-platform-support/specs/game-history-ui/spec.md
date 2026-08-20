# Game History UI

## MODIFIED Requirements

### Requirement: Correct round numbering, phase naming, and attribution of a round's closing move

The dashboard SHALL derive each event's round and phase from the semantics of the platform that recorded the event, rather than from the raw state fields, so that the transcript labels match the game as played. The round and phase mapping SHALL be selected by the event's platform in one place, and no consumer downstream of that mapping SHALL re-apply a platform's convention of its own.

For a `dragncards` event the displayed round number SHALL be `roundNumber + 1`, because DragnCards `roundNumber` counts **completed** rounds (it is 0 throughout the first round of play and increments as a round closes). "Setup" SHALL be reserved for the genuine setup band: events for which no game state is yet known, and events whose state has `roundNumber` 0 **and** step id `0.0` (the Beginning step before the first player phase). The first round of play SHALL NOT be labelled "Setup".

For a `dragncards` event a step id SHALL be mapped to its phase through the Marvel Champions step-to-phase table (`0.0` Beginning, `1.1` and `1.2` Player, `2.1` through `2.5` Villain, `0.1` End) and SHALL NOT be bucketed by parsing the step id's leading number. In particular, step `0.1` SHALL be named as the End phase, not Beginning.

For a `marvel-lcg` event the recorded `round_id` is **already the play round** — it is 0 during setup and becomes 1 on the first player turn — so it SHALL be displayed as it stands and SHALL NOT be incremented. Applying DragnCards' `+1` convention to a marvel-lcg event is a defect, not a rounding difference: it would label the first player turn "Round 2". A `marvel-lcg` event SHALL be placed in the Setup band when no state is yet known or when its `round_id` is 0.

For a `marvel-lcg` event the phase SHALL be taken from the platform's own `phase` string, which is human-readable prose such as `Resolve Mulligans` or `Player 1 Turn`, normalised for display by stripping leading whitespace and decorative characters. Its step identifier is a monotonically increasing integer with no relationship to DragnCards' dotted `1.1`/`2.3` ids, so it SHALL NOT be looked up in the Marvel Champions step-to-phase table and SHALL NOT be parsed as a dotted step id. The dashboard SHALL NOT synthesise a DragnCards step id, nor a completed-round counter, for a marvel-lcg event.

Because a `game-service` history event embeds the state **after** its action was applied, each `game-service` event SHALL be attributed to the round and step it acted **from** (the state before that action), with the observed post-action state carried forward to subsequent events. Events from other actors SHALL keep inheriting the latest observed state. Consequently the move that closes a round SHALL fall inside the round it closed, not at the start of the next round. This attribution rule is platform-neutral and SHALL apply to both platforms.

#### Scenario: The first DragnCards round of play is Round 1, not Setup

- **WHEN** the transcript renders `dragncards` events whose state reports `roundNumber` 0 in a player or villain step
- **THEN** those events SHALL be grouped under "Round 1", and only the pre-state events and the `roundNumber` 0 / step `0.0` band SHALL be labelled "Setup"

#### Scenario: End-of-round step is named End

- **WHEN** a `dragncards` event's step id is `0.1`
- **THEN** the dashboard SHALL name its phase "End" rather than "Beginning"

#### Scenario: A marvel-lcg round is not incremented

- **WHEN** the transcript renders a `marvel-lcg` event whose state reports `round_id` 1
- **THEN** the dashboard SHALL group it under "Round 1"
- **AND** it SHALL NOT be labelled "Round 2"

#### Scenario: A marvel-lcg setup event lands in the Setup band

- **WHEN** the transcript renders a `marvel-lcg` event whose state reports `round_id` 0
- **THEN** the dashboard SHALL group it under "Setup"

#### Scenario: A marvel-lcg step id is not mapped through the DragnCards table

- **WHEN** the transcript renders a `marvel-lcg` event whose step identifier is the integer `30` and whose phase is `Player 1 Turn`
- **THEN** the dashboard SHALL name the phase from the platform's own phase string
- **AND** it SHALL NOT look the step identifier up in the Marvel Champions step-to-phase table, and SHALL NOT report a Beginning, Player, Villain, or End phase derived from it

#### Scenario: The move that closes a round stays in that round

- **WHEN** a `game-service` event's action advances the game out of a round (its pre-action state is in round N and its post-action state is in round N+1)
- **THEN** that event SHALL be rendered inside round N, and the next round's start header SHALL be rendered after it rather than above it

#### Scenario: Non-game-service events inherit the latest known state

- **WHEN** an `agent`, `user`, or `evaluator` event appears between two `game-service` events
- **THEN** it SHALL be attributed to the most recently observed round and step

### Requirement: Jump to a round

The dashboard history transcript SHALL provide a control that moves the transcript
directly to a chosen round, because with only a window of the timeline rendered,
scrolling is no longer a way to reach an early round of a long game.

The control SHALL offer the same rounds, in the same order and under the same
labels, as the game → rounds → moves navigation tree — the Setup band, then each
round of play numbered on the recording platform's own round convention, as
established by the round and phase mapping — so the two never disagree about what
a round is called, and neither re-derives a round number of its own. It SHALL
offer no round that has no moves, and SHALL render nothing at all when the game
has no rounds.

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

#### Scenario: The control and the navigation tree agree on a marvel-lcg game's rounds

- **WHEN** the user opens the jump-to-round control on a `marvel-lcg` game
- **THEN** the offered rounds SHALL be exactly the rounds the navigation tree lists, under the same labels
- **AND** neither surface SHALL apply DragnCards' completed-round `+1` convention to that game

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

### Requirement: Reconstructed board at the selected event

The dashboard SHALL let the user open the board reconstructed at the selected event by restoring that event's `seq` into an EPHEMERAL session (a non-emitting session that records no history) and embedding its viewer, allowing interaction, and SHALL dispose that ephemeral reconstruction when the view is closed — on in-app close/navigation and on browser tab close. Because the ephemeral session emits no history, disposal removes the reconstruction session only. Client disposal is best-effort (a server-side TTL reaper reclaims sessions whose client never tore them down). Only one reconstruction is live at a time.

A reconstruction SHALL be built on the platform that recorded the game and on no other. A recorded game belongs to the platform that produced it, so the dashboard SHALL NOT reconstruct a `marvel-lcg` game into a DragnCards room, SHALL NOT reconstruct a `dragncards` game into a marvel-lcg instance, and SHALL NOT offer a reconstruction whose viewer would be a different platform's than the game's. Where the recording platform supports no state import, the dashboard SHALL present the board control as unavailable for that game, stating that the platform cannot be rewound into a throwaway copy, rather than building a room on the platform it can reach.

A live reconstruction SHALL survive the browser tab merely becoming hidden — switching tabs, minimizing, or backgrounding the application is not the end of the view. Disposal is triggered by an in-app close, a change of game, unmounting the view, and page unload (tab close, refresh, navigation), never by the document becoming hidden, so the board the user comes back to is still the board the dashboard claims is open.

When only the selected event changes within the same game, the dashboard SHALL retain the ephemeral session rather than dispose it, and SHALL restore the newly selected event into that retained session instead of building a second viewer. Building a room is several sequential round trips to the platform plus a channel join and a plugin load; re-pointing an open room at another moment is a single state load, measured at ~55 ms against ~728 ms. Retention is what makes viewing a second moment fast, and it is safe because loading a full-state base replaces the room's game document outright.

Retaining the session SHALL NOT mean retaining the rendered board. When the selection moves, the dashboard SHALL clear the displayed reconstruction so that a board is never shown under a header naming a different moment, and the user SHALL re-open deliberately. A retained session SHALL be disposed on in-app close, a change of game, unmount, and page unload, exactly as a displayed one is, so retention never outlives the panel. A change of game SHALL dispose the retained session whether or not the two games share a platform, because a session built for one game cannot be re-pointed at another.

The reconstruction view SHALL state, on the view itself, that it is a temporary copy which does not affect the recorded game and is discarded when closed. This view replaces the whole transcript panel with an unfamiliar game board, and a board that looks exactly like a live game is indistinguishable from one; leaving the user to infer that nothing was overwritten produced a report of data loss against behaviour that provably changes nothing.

The dashboard SHALL explain the wait while a reconstruction is being built, rather than showing an unqualified spinner. Building one creates a real game on the recording platform — several sequential round trips plus a join and a content load, seconds rather than milliseconds — and an unexplained multi-second wait on a button whose effect the user is already unsure of is a substantial part of the surface reading as slow and unclear.

The dashboard SHALL take the reconstruction's viewer target from the restore response when the history-service supplies it, rather than listing every live session and searching it by id. The list read is retained only as a fallback for a service that reports no target. Beyond the wasted round trip, the search races the ephemeral reaper: a session reclaimed between the restore and the list yields no match, and the view then renders its fallback with no error surfaced. When a retained session is reused, the target is already known from the open that created it, so the dashboard SHALL keep using it and SHALL NOT list sessions to rediscover it.

#### Scenario: Open and click the board at a past moment
- **WHEN** the user opens the board for a selected event
- **THEN** the dashboard SHALL reconstruct that event's state into an ephemeral session on the recording platform, embed that platform's viewer, and the user SHALL be able to interact with the board as it was at that moment

#### Scenario: A recorded game is never reconstructed on another platform
- **WHEN** the user opens the board for an event of a `marvel-lcg` game
- **THEN** the dashboard SHALL NOT create a DragnCards room and SHALL NOT embed a DragnCards viewer for it

#### Scenario: A platform that cannot be rewound says so
- **WHEN** the selected game's platform supports no state import for a throwaway copy
- **THEN** the board control SHALL be presented as unavailable for that game with a stated reason, and no reconstruction SHALL be created on any platform

#### Scenario: A second moment of the same game reuses the open session
- **WHEN** the user has a reconstruction open, selects a different event of the same game, and opens the board again
- **THEN** the dashboard SHALL restore into the session it already holds, SHALL embed the same viewer, and SHALL NOT create a second game

#### Scenario: A reused board shows the newly selected moment
- **WHEN** a retained session is re-pointed at a different event
- **THEN** the embedded board SHALL show the state at the newly selected event, carrying nothing over from the moment it previously showed

#### Scenario: Moving the selection clears the board but keeps the session
- **WHEN** the user changes the selected event while a reconstruction is displayed
- **THEN** the dashboard SHALL stop displaying the board so that no board is shown under a header naming another moment, and SHALL keep the session so that re-opening reuses it

#### Scenario: Switching game disposes the retained session
- **WHEN** the user selects a different game while a reconstruction session is retained, whether displayed or not, and whether or not the two games share a platform
- **THEN** the dashboard SHALL dispose that session, because a session built for one game cannot be re-pointed at another

#### Scenario: The reconstruction says it is a throwaway copy
- **WHEN** a reconstructed board is shown
- **THEN** the view SHALL state that it is a temporary copy, that the recorded game is unaffected by anything done in it, and that it is discarded on close

#### Scenario: The wait while a board is built is explained
- **WHEN** a reconstruction is being created
- **THEN** the dashboard SHALL say that a temporary game is being created on the recording platform and that it takes a few seconds, rather than showing only a spinner

#### Scenario: The viewer target comes from the restore response
- **WHEN** a restore for a reconstruction reports the new session's viewer target
- **THEN** the dashboard SHALL embed that target without listing the live sessions, falling back to the session list only when no target is reported

#### Scenario: A reused session does not re-resolve its target
- **WHEN** a restore reuses a retained session and therefore reports no newly created target
- **THEN** the dashboard SHALL embed the target it already recorded for that session and SHALL NOT list the live sessions

#### Scenario: Disposal on close
- **WHEN** the user closes the reconstructed board view, navigates away, or closes the tab
- **THEN** the dashboard SHALL delete the reconstruction session, leaving no orphaned session; because the ephemeral session is non-emitting, no extra game SHALL appear in the history list

#### Scenario: A hidden tab does not end the view
- **WHEN** the browser tab holding a live reconstruction becomes hidden
- **THEN** the dashboard SHALL keep that reconstruction session alive, and returning to the tab SHALL show the same live board rather than a board whose session has been deleted underneath it

### Requirement: Restore-to-a-past-moment control

The dashboard SHALL provide a control to trigger a restore of a game to a selected past moment through the history-service, letting the user choose the restore target mode (a new branchable session or an in-place overwrite of the live session).

A restore SHALL target the platform that recorded the game. The dashboard SHALL NOT offer, and SHALL NOT request, a restore of a recorded game onto a platform other than its own, in either target mode. Where the recording platform supports no state import, both restore modes SHALL be presented as unavailable for that game with a stated reason, rather than offered and then failing at the service.

Each action available on a recorded moment SHALL state what it will do, to which game, **before** it is clicked, and a destructive action SHALL be distinguishable from a read-only one without clicking either. The three per-moment actions differ in exactly the way a user cares about — one changes nothing, one creates a second game, one destroys play from the game in front of them — and they were presented as an undifferentiated list of controls whose labels named mechanisms ("New branchable session", "In-place overwrite") rather than consequences. A user who cannot tell which action overwrites their game is the reported defect, and a read-only action that looks destructive gets reported as data loss.

The read-only action SHALL be offered first, ahead of the actions that change a game: looking at the board is the cheapest and most common thing a user wants from a recorded moment.

A restore's reported outcome SHALL name the thing it produced, in terms the user can act on. For a branch restore that means naming what was created on the recording platform — the DragnCards room for a `dragncards` game, the platform's own game identifier for a platform without rooms — and offering a way to open it, because a new game the user cannot reach is indistinguishable from a restore that did not happen. For an in-place restore it means saying that this game has been rewound.

The dashboard SHALL distinguish a restore that completed without its agent conversation from a restore that failed. When the history-service reports that the game state was restored but the agent context was not, the dashboard SHALL present that as a completed restore carrying an explanatory note, NOT as a failure — the game state really was changed, so calling it a failure describes a state that does not exist and invites the user to retry a destructive action that already succeeded.

A confirmation affordance SHALL name the action until the user asks to perform it, and only then present the confirmation wording. A control that opens already reading "Confirm overwrite" and changes to the action name after the first click shows its most alarming wording at the moment it is least warranted, and gives no indication that a second click is what commits.

#### Scenario: Trigger a restore from the timeline
- **WHEN** a user selects a timeline moment and confirms a restore
- **THEN** the dashboard SHALL request the history-service to restore the game to that moment's `seq` and SHALL show the restore outcome

#### Scenario: Choose the restore target mode
- **WHEN** a user initiates a restore to a selected moment
- **THEN** the dashboard SHALL let the user choose between a new branchable session and an in-place overwrite, defaulting to a new session, and SHALL pass the chosen mode to the history-service

#### Scenario: A restore never crosses platforms
- **WHEN** a user restores a moment of a `marvel-lcg` game
- **THEN** the request SHALL name that game's own platform, and the dashboard SHALL NOT offer or request a restore into a DragnCards session

#### Scenario: A platform that cannot be restored offers neither mode
- **WHEN** the selected game's platform supports no state import
- **THEN** both restore modes SHALL be presented as unavailable with a stated reason, and no restore request SHALL be sent

#### Scenario: Each mode's effect is legible before it is chosen
- **WHEN** the per-moment actions are shown for an event
- **THEN** each SHALL carry a label naming its effect and a marker distinguishing read-only from safe-but-creating from destructive, and the read-only action SHALL appear first

#### Scenario: Warn before an in-place overwrite
- **WHEN** a user selects the in-place overwrite mode for a restore
- **THEN** the dashboard SHALL warn that game state after the selected moment will be discarded and SHALL require confirmation before proceeding, with the submit affordance naming the action until the user requests it and only then reading as a confirmation

#### Scenario: A branch restore names and links the game it created
- **WHEN** a restore into a new session completes and the history-service reports what it created
- **THEN** the dashboard SHALL name it in the outcome using the recording platform's own vocabulary and SHALL offer a link that opens it

#### Scenario: A restore without its agent conversation is not a failure
- **WHEN** the history-service reports a completed restore whose agent context was not rebuilt, with a reason
- **THEN** the dashboard SHALL present a completed restore and show the reason as a note, and SHALL NOT present it as a failed restore

#### Scenario: Surface restore failure
- **WHEN** the history-service reports that a restore could not be completed
- **THEN** the dashboard SHALL display the failure to the user without claiming the restore succeeded

## ADDED Requirements

### Requirement: A transcript phase label is written in the recording platform's own vocabulary

The phase shown on an event's summary line SHALL be the phase name that the event's platform actually uses, produced by the same per-platform mapping the round bands are produced by, so the chip and the round header never describe an event with two different platforms' vocabularies.

A `dragncards` event's chip SHALL read as the Marvel Champions phase its step id maps to. A `marvel-lcg` event's chip SHALL read as that platform's normalised phase prose. The chip SHALL NOT display a dotted DragnCards step id for a `marvel-lcg` event, and SHALL NOT display a marvel-lcg integer step identifier as if it were a step id.

An event for which the recording platform reports no phase SHALL render no phase chip. A blank or fabricated chip is worse than none, because a reader takes a chip as evidence the phase is known.

#### Scenario: A DragnCards event's chip names its mapped phase

- **WHEN** the transcript renders a `dragncards` event whose step id is `2.3`
- **THEN** its summary line SHALL show the Villain phase name from the step-to-phase table

#### Scenario: A marvel-lcg event's chip shows its own phase prose

- **WHEN** the transcript renders a `marvel-lcg` event whose recorded phase is `"\n--- Player 1 Turn ---"`
- **THEN** its summary line SHALL show `Player 1 Turn`, with the leading newline and decorative dashes stripped

#### Scenario: A marvel-lcg event's chip is not a step id

- **WHEN** the transcript renders a `marvel-lcg` event whose step identifier is the integer `30`
- **THEN** its summary line SHALL NOT show `30` as a phase, and SHALL NOT show a dotted step id

#### Scenario: An event with no known phase shows no chip

- **WHEN** the transcript renders an event whose platform reports no phase for it
- **THEN** no phase chip SHALL be rendered for that event
