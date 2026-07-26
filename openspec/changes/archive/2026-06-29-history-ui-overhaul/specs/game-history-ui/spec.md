## MODIFIED Requirements

### Requirement: Game history timeline view
The dashboard SHALL provide a view that lists a game's history as an ordered timeline of events retrieved from the history-service. Stored snapshots are an internal reconstruction detail (the densest base for branching/board reconstruction) and SHALL NOT be surfaced as user-facing "restore point" markers on the timeline; restore remains available per-event through the restore control.

#### Scenario: Display ordered timeline for a game
- **WHEN** a user opens the history view for a `game_id`
- **THEN** the dashboard SHALL display the game's events ordered by ascending `seq`, distinguishing `agent` move/decision events from `game-service` game-state events

#### Scenario: Show decision context for an agent move
- **WHEN** a user selects an `agent` move event in the timeline
- **THEN** the dashboard SHALL display the captured intended action and reasoning/context for that move

#### Scenario: Show game status for a state event
- **WHEN** a user selects a `game-service` state event in the timeline
- **THEN** the dashboard SHALL display the resulting game status for that event

#### Scenario: Empty history
- **WHEN** a user opens the history view for a `game_id` with no stored events
- **THEN** the dashboard SHALL display an empty-state message rather than an error

## ADDED Requirements

### Requirement: Readable conversation rendering

The dashboard history detail SHALL render an agent move's captured conversation context — user/assistant/system messages, reasoning, and tool calls with their results — using the same transcript presentation as the Play tab, rather than raw JSON.

#### Scenario: Agent move shows a readable transcript

- WHEN the user selects an `agent_move` event whose payload carries a conversation context
- THEN the detail renders the messages, reasoning, and tool calls/results as a readable transcript (matching the Play tab's presentation), not as raw JSON

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
