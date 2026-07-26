## ADDED Requirements

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
