## ADDED Requirements

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

## MODIFIED Requirements

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
